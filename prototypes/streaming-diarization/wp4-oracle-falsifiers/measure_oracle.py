"""PROTOTYPE: reference words + observed segments, no acoustic ground truth.
Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> prototypes/streaming-diarization/wp4-oracle-falsifiers/measure_oracle.py
Hypothesis: lexical ownership detects omissions, cross-lane attribution and playback copies.
Falsifier: a correct overlapping reference triggers duplication, or corrupt input passes.
"""
import json
from moss_transcribe_diarize.lane_word_oracle import score_lanes as score

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
    for row in payload['scenarios']: row.pop('operator_phrase', None)
    accepted = True
    try: g7.validate_attended_g7(payload, candidate=_candidate())
    except g7.AttendedCanaryError: accepted = False
    print(json.dumps(dict(case='production_counts_only_validator', accepted=accepted, scenarios=len(payload['scenarios']), transcript_words_supplied=0)))

if __name__ == '__main__': main()
