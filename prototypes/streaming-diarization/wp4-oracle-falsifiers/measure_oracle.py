"""PROTOTYPE: reference words + observed segments, no acoustic ground truth.
Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> prototypes/streaming-diarization/wp4-oracle-falsifiers/measure_oracle.py
Hypothesis: lexical ownership detects omissions, cross-lane attribution and playback copies.
Falsifier: a correct overlapping reference triggers duplication, or corrupt input passes.
"""
import json
import re
from collections import Counter, defaultdict


def words(text):
    return re.findall(r"\w+(?:['’]\w+)*", text.lower().replace('’', "'"))


def distance(reference, hypothesis):
    # (total, substitutions, omissions, additions); exact Levenshtein alignment.
    previous = [(i, 0, 0, i) for i in range(len(hypothesis) + 1)]
    for i, a in enumerate(reference, 1):
        current = [(i, 0, i, 0)]
        for j, b in enumerate(hypothesis, 1):
            if a == b:
                current.append(previous[j - 1])
            else:
                candidates = []
                for cell, operation in ((previous[j-1], 1), (previous[j], 2), (current[j-1], 3)):
                    value = list(cell); value[0] += 1; value[operation] += 1
                    candidates.append(tuple(value))
                current.append(min(candidates))
        previous = current
    n, s, d, a = previous[-1]
    return dict(reference_words=len(reference), observed_words=len(hypothesis), substitutions=s,
                omissions=d, additions=a, wer=n/len(reference) if reference else None)


def score(segments, references):
    refs = {lane: words(text) for lane, text in references.items()}
    exclusive = {lane: set(ws) - set(w for other, other_ws in refs.items() if other != lane for w in other_ws)
                 for lane, ws in refs.items()}
    votes = defaultdict(Counter)
    for s in segments:
        for lane in refs:
            votes[s['speaker']][lane] += sum(w in exclusive[lane] for w in words(s['text']))
    owners = {speaker: v.most_common(1)[0][0] for speaker, v in votes.items() if v.total() and len([n for n in v.values() if n == max(v.values())]) == 1}
    observed = {lane: [] for lane in refs}
    attribution = 0; duplicate = 0; unresolved = 0
    for s in sorted(segments, key=lambda s: s['start']):
        lane = s.get('source_lane') or owners.get(s['speaker'])
        ws = words(s['text'])
        if lane not in refs:
            unresolved += len(ws); continue
        observed[lane].extend(ws)
        attribution += sum(w in exclusive[other] for other in refs if other != lane for w in ws)
        if lane == 'microphone':
            nearby = Counter(w for t in segments if (t.get('source_lane') or owners.get(t['speaker'])) == 'system'
                             and abs(t['start']-s['start']) <= 2 for w in words(t['text']))
            duplicate += sum((Counter(ws) & nearby).values())
    lanes = {lane: {**distance(refs[lane], ws), 'unique_reference_words': len(set(refs[lane])),
                    'unique_retained': len(set(refs[lane]) & set(ws))} for lane, ws in observed.items()}
    return dict(lanes=lanes, attribution_errors=attribution, duplication_count=duplicate,
                unresolved_words=unresolved, passed=bool(segments) and not (attribution or duplicate or unresolved)
                and all(v['wer'] == 0 for v in lanes.values()))


def segment(lane, text, start=0):
    return dict(source_lane=lane, speaker=lane+'-speaker', start=start, end=start+1, text=text)


def main():
    refs = dict(system='Copper planets orbit distant stars', microphone='Violet gardens grow beside rivers')
    good = [segment(k, v) for k, v in refs.items()]
    controls = {
        'valid_tagged': good,
        'valid_legacy': [{k:v for k,v in s.items() if k != 'source_lane'} for s in good],
        'counts_only': [],
        'zero_mic': good[:1],
        'swapped': [{**s, 'source_lane': 'microphone' if s['source_lane']=='system' else 'system'} for s in good],
        'duplicated_playback': good + [segment('microphone', refs['system'])],
    }
    for name, segments in controls.items():
        print(json.dumps(dict(case=name, **score(segments, refs)), sort_keys=True))
    # Real reference texts from the documented public corpus; overlapping correctly tagged
    # segments. Ordinary shared words are independent occurrences, not playback leakage.
    from pathlib import Path
    root = Path('evidence/live-policy-sweep-20260825/corpus')
    rows = {lane: json.loads((root / corpus / 'reference.jsonl').read_text().splitlines()[0])
              for lane, corpus in [('system','interview_bill_ackman_60s'),('microphone','interview_keyu_jin_60s')]}
    actual = {lane: row['text'] for lane, row in rows.items()}
    observed = [{**segment(lane, row['text'], row['start']), 'end': row['end']} for lane, row in rows.items()]
    print(json.dumps(dict(case='valid_public_corpus_overlap', **score(observed, actual)), sort_keys=True))
    # Production validator control: counts-only shape from its existing fixtures.
    from tests.phase2.test_attended_g7_canary import _scenario, _candidate
    from moss_transcribe_diarize import phase2_g7_canary as g7
    payload = dict(schema=g7.G7_EVIDENCE_SCHEMA, source=g7.G7_EVIDENCE_SOURCE, production_origin=True,
                   operator_attended=True, admitted=False, origin=g7.G7_PRODUCTION_ORIGIN,
                   candidate=_candidate(), chrome_version='fixture',
                   scenarios=[_scenario(name, surface) for name, surface in g7.G7_SCENARIOS.items()])
    g7.validate_attended_g7(payload, candidate=_candidate())
    print(json.dumps(dict(case='production_counts_only_validator', accepted=True, scenarios=len(payload['scenarios']), transcript_words_supplied=0)))

if __name__ == '__main__': main()
