"""Offline audit of retained request accounting and final/saved lane surfaces."""
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence/mvpfix/wp1'
SCRATCH = Path(__file__).resolve().parent / 'scratch'
requests = [json.loads(line) for line in (OUT/'requests.jsonl').read_text().splitlines()]
assert sorted(row['request'] for row in requests) == list(range(1, 647))
assert len(requests) <= 650
active = peak = 0
for _, delta in sorted([(row['start'], 1) for row in requests] +
                       [(row['start'] + row['seconds'], -1) for row in requests]):
    active += delta
    peak = max(peak, active)
assert peak == 1
scores = json.loads((OUT/'scores.json').read_text())
assert len(scores['cases']) == 26 and scores['request_case_count_agrees']
matched = falsifiers = 0
for row in scores['cases']:
    run = row['run_id']
    raw = json.loads((SCRATCH/f'{run}-surfaces.json').read_text())
    saved = raw['meeting']['transcript']['segments']
    final = raw['final']['effective_transcript']
    assert [(s['text'],s.get('speaker_entity_id')) for s in saved] == [(s['text'],s.get('canonical_speaker')) for s in final]
    matched += 1
    meta = json.loads((OUT/f'{run}.json').read_text())
    if run.startswith(('resume-', 'fixed-')):
        assert meta['falsifiers_failed'] == []
        assert raw['final']['finalization_status'] == 'final'
        falsifiers += 1
    for lane, counts in row['lanes'].items():
        lane_words = sum(len(re.findall(r'[a-z0-9]+', s['text'].lower())) for s, f in zip(saved, final, strict=True) if f.get('source_lane') == lane)
        assert lane_words == counts['saved_words_via_exact_surface_correspondence']
    if run.startswith('fixed-') and row['case'] == 'same':
        speakers = {lane:{s.get('canonical_speaker') for s in final if s.get('source_lane')==lane and s.get('canonical_speaker')} for lane in ('system','microphone')}
        assert len(speakers['system']) == len(speakers['microphone']) == 1
        assert not speakers['system'] & speakers['microphone']
    if run.startswith('fixed-') and row['case'] == 'zero':
        assert not [s for s in final if s.get('source_lane') == 'microphone']
assert matched == 26 and falsifiers == 17
for row in scores['e2e_request_counts']:
    assert row['exit_code'] == 0
spans = [json.loads(line) for line in (OUT/'spans.jsonl').read_text().splitlines()]
fixed = []
for path in sorted(OUT.glob('fixed-v1-*.json')):
    meta = json.loads(path.read_text())
    selected = [s for s in spans if s['samples']==40000 and meta['capture_start_monotonic'] <= s['start'] <= meta['capture_stop_monotonic']+meta['stop_to_final_seconds']]
    fixed.extend(selected)
assert len(fixed) == 99
fault = json.loads((OUT/'failure-state.json').read_text())['verdict']
assert fault['system_original_preserved'] and fault['mic_revised_windows'] == 2 and fault['passed']
summary = {'requests':len(requests),'saved_final_matches':matched,'resumed_and_fixed_falsifier_passes':falsifiers,
           'fixed_cases':6,'e2e_scripts_passed':3,'max_requests_in_flight':peak,
           'fixed_individual_2_5s_decodes':len(fixed),
           'fixed_individual_2_5s_median_seconds':statistics.median(s['seconds'] for s in fixed),
           'fixed_individual_2_5s_max_seconds':max(s['seconds'] for s in fixed)}
print(json.dumps(summary,indent=2))
