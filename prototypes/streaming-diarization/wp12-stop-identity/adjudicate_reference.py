"""WP12 retained 180 s reference adjudication; offline, no transcript output.

Reference timestamps are coarse. The explicit row associations below were
reviewed against the saved segment words, including boundary-spanning turns and
the two 60 s loop seams. This is evidence annotation, not a production matcher.
"""
import json
import re
from collections import Counter
from pathlib import Path

root = Path.cwd()
out = root / 'evidence/mvpfix/wp12'
reference_path = root.parent / 'MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/interview_bill_ackman_60s/reference.jsonl'
reference = [json.loads(line) for line in reference_path.read_text().splitlines()]
assert [r['speaker'] for r in reference] == ['Bill Ackman', 'Lex Fridman', 'Bill Ackman', 'Lex Fridman', 'Bill Ackman']
run = next(r for r in json.loads((out/'overlap-comparison.json').read_text()) if r['seconds'] == 180)
lane = next(r for r in run['lanes'] if r['lane'] == 'system')
differences = {r['index']: r for r in lane['differences']}
surface = json.loads((root/'.wp12/overlap-shadow-p180-clean-parity-180-surface.json').read_text())
surface = [r for r in surface if r['source_lane'] == 'system']
assert len(surface) == 56 and len(differences) == 54

# Each pair is (zero-based loop, one-based reference row).
reviewed = {}
for first, last, loop, row in (
    (0, 8, 0, 1), (9, 9, 0, 2), (10, 11, 0, 3), (12, 12, 0, 4), (13, 16, 0, 5),
    (18, 27, 1, 1), (28, 28, 1, 2), (29, 30, 1, 3), (31, 31, 1, 4), (32, 35, 1, 5),
    (37, 46, 2, 1), (47, 47, 2, 2), (48, 49, 2, 3), (50, 50, 2, 4), (51, 55, 2, 5),
):
    for index in range(first, last+1):
        reviewed[index] = [(loop, row)]
reviewed[17] = [(0, 5), (1, 1)]
reviewed[36] = [(1, 5), (2, 1)]
assert set(reviewed) == set(range(56))

records = []
for index, segment in enumerate(surface):
    assert segment['canonical_speaker'] is None
    start, end = (segment[k]/16000 for k in ('start_sample', 'end_sample'))
    overlaps = []
    for loop in range(3):
        for row, ref in enumerate(reference, 1):
            a, b = max(start, loop*60+ref['start']), min(end, loop*60+ref['end'])
            if a < b:
                overlaps.append(dict(loop=loop, reference_row=row, label=ref['speaker'], overlap_seconds=round(b-a, 6)))
    labels = sorted({reference[row-1]['speaker'] for _, row in reviewed[index]})
    diff = differences.get(index)
    if diff:
        assert diff['words_equal'] and diff['acoustic']['speaker'] is None
        assert diff['acoustic']['start'] == segment['start_sample']
        assert diff['acoustic']['end'] == segment['end_sample']
    canonical = diff['overlap']['speaker'] if diff else None
    if canonical:
        assert labels == [{'speaker-0001': 'Bill Ackman', 'speaker-0004': 'Lex Fridman'}[canonical]]
    records.append(dict(system_segment_index=index, start_seconds=start, end_seconds=end,
        changed=index in differences, words=len(re.findall(r'[a-z0-9]+', segment['text'].lower())),
        acoustic_speaker=None, overlap_speaker=canonical, reference_time_overlaps=overlaps,
        reviewed_reference_rows=[dict(loop=loop, reference_row=row) for loop, row in reviewed[index]],
        reviewed_reference_labels=labels,
        reference_agrees_with_overlap=None if canonical is None else True))

changed = [r for r in records if r['changed']]
assert Counter(r['overlap_speaker'] for r in changed) == {'speaker-0001': 50, 'speaker-0004': 4}
assert sum(r['words'] for r in changed) == 575
print(json.dumps(dict(verdict='REFERENCE_CONFIRMED_ACCEPTED_BY_LEAD',
    reference=str(reference_path), source_arm=run['arm'], source_lane='system',
    method='Manual word-to-reference-row adjudication; raw time overlaps retained separately. No audio re-listening or word-level reference timestamps claimed.',
    conclusion='All 54 restored assignments agree with reference voices: 50 Bill Ackman, 4 Lex Fridman. speaker-0004 is legitimate. Lead accepted this improvement after the initial second-voice stop; two later Lex turns remain unassigned as a known limitation.',
    changed_segments=len(changed), changed_words=sum(r['words'] for r in changed),
    changed_reference_labels=dict(Counter(r['reviewed_reference_labels'][0] for r in changed)),
    unchanged_unassigned_words=sum(r['words'] for r in records if not r['changed']),
    segments=records), indent=2))
