"""Reference-based lane acceptance measurements; no decoder or identity policy."""
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


def score_lanes(segments, references, *, max_wer=0.0):
    """Score known speech; legacy lane ownership is inferred, never acoustic proof."""
    segments = [normalize_segment(s) for s in segments]
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
            duplicate += sum(n for w, n in (Counter(ws) & nearby).items() if w in exclusive['system'])
    lanes = {lane: {**distance(refs[lane], ws), 'unique_reference_words': len(set(refs[lane])),
                    'unique_retained': len(set(refs[lane]) & set(ws)),
                    'unique_retention': len(set(refs[lane]) & set(ws))/len(set(refs[lane])) if refs[lane] else None} for lane, ws in observed.items()}
    speaker_conflicts = sum(len({s.get('source_lane') for s in segments if s['speaker'] == speaker and s.get('source_lane')}) > 1 for speaker in votes)
    return dict(lanes=lanes, attribution_errors=attribution, speaker_lane_conflicts=speaker_conflicts,
                max_wer=max_wer, ownership='explicit' if all(s.get('source_lane') for s in segments) else 'lexically_inferred', duplication_count=duplicate,
                unresolved_words=unresolved, passed=bool(segments) and not (attribution or duplicate or unresolved or speaker_conflicts)
                and all(v['reference_words'] > 0 and v['wer'] <= max_wer for v in lanes.values()))



def normalize_segment(segment):
    return dict(segment, speaker=segment.get('speaker_entity_id') or segment.get('canonical_speaker') or segment.get('speaker') or '',
                start=float(segment['start_sample'])/16000 if 'start_sample' in segment else float(segment.get('start', 0)),
                end=float(segment['end_sample'])/16000 if 'end_sample' in segment else float(segment.get('end', 0)))
