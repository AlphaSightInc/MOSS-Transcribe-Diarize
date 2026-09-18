"""Offline evidence consistency; not a new live acceptance run."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
read=lambda p:json.loads((ROOT/p).read_text())
assert read('source-window.json')==dict(compared_samples=400000,source_offset_seconds=115,exact_pcm_equal=True)
for case,system_edits in [('alternation',9),('overlap',13)]:
 before,after=read(f'before-{case}.json'),read(f'after-{case}.json')
 assert not after['passed']  # Residual quality failures must remain visible.
 for surface in ('final','reopened'):
  b,a=before['surfaces'][surface],after['surfaces'][surface]
  assert (b['lanes']['microphone']['reference_words'],b['lanes']['microphone']['additions'])==(48,10)
  assert (a['lanes']['microphone']['reference_words'],a['lanes']['microphone']['additions'])==(53,5)
  assert a['attribution_errors']==a['duplication_count']==a['speaker_lane_conflicts']==0
  assert sum(a['lanes']['system'][k] for k in ('substitutions','omissions','additions'))==system_edits
  assert a['lanes']['system']['reference_words']==106
before=read('recognition-before/stress-results.json')
assert next(r for r in before if r['case']=='recognition')['recognition_seconds'] is None
recognized=[r for r in read('recognition-after/stress-results.json') if r['case'].startswith('recognize-')]
assert len(recognized)==4
assert all(0<r['recognition_seconds']<=4 and r['status']=='completed' and r['saved_speakers']==['WP17 Adam'] for r in recognized)
durations=read('durations/stress-results.json')
assert len(durations)==12
assert all(r['status']=='completed' and r['failure'] is None and r['finalization']=='final' for r in durations)
diffs=read('duration-diffs.json')
assert len(diffs)==8 and all(r['producers'] for r in diffs)
requests=(ROOT/'decoder-requests.jsonl').read_text().splitlines()
standalone=(ROOT/'alone-requests.jsonl').read_text().splitlines()
assert len(requests)+len(standalone)<=600
print(json.dumps(dict(evidence_consistency='PASS',product_acceptance='FAIL: residual quality',
    recognition_routes=len(recognized),recognition_max_seconds=max(r['recognition_seconds'] for r in recognized),
    duration_cases=len(durations),lane_differentials=len(diffs),decoder_requests=len(requests)+len(standalone)),indent=2))
