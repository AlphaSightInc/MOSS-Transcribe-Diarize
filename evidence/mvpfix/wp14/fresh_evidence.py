"""Offline VERIFY.md evidence consistency check; no service or decoder requests.
Run from WP14: source evidence/mvpfix/wp14/environment.sh
"$WP14_PY" evidence/mvpfix/wp14/fresh_evidence.py
Missing or inconsistent retained records fail assertions; no acceptance upgrade.
"""
import json
from collections import Counter
from pathlib import Path

root = Path(__file__).parent

def read(name):
    return json.loads((root / name).read_text())

rows = read('workspace-final/results.json')['rows']
assert set(rows) == {str(n) for n in range(1, 15)}
counts = dict(Counter(row['status'] for row in rows.values()))
assert counts == {'PASS': 11, 'FAIL': 2, 'SKIP': 1}
assert {k for k, v in rows.items() if v['status'] == 'FAIL'} == {'4', '10'}
for n, row in rows.items():
    assert row == read(f'workspace-final/row-{int(n):02}.json'), n
for n in ('2', '3'):
    assert (rows[n]['edits'], rows[n]['reference_words']) == (10, 115)
    assert rows[n]['wer'] == 10 / 115
assert abs(rows['4']['first_visible_seconds'] - 3.323115) < .000001
assert abs(rows['4']['stop_to_terminal_seconds'] - 8.094547) < .000001
formats = rows['6']['formats']
assert set(formats) == {'md', 'txt', 'json', 'srt', 'vtt'}
assert all(v['ok'] and v['expected_turns'] == v['downloaded_turns'] == 6
           and all(v[k] for k in ('words', 'labels', 'timing', 'identity')) for v in formats.values())
assert formats['json']['lane'] is True
assert rows['9']['reason_code'] == 'no_configured_relay_models'
cycles = rows['14']['cycles']
assert len(cycles) == 3 and len({v['meeting'] for v in cycles}) == 3
assert rows['14']['same_document'] and rows['14']['all_in_history']
assert all(v['ok'] and v['status_received'] == 'completed' and v['first_frame_sequence'] == 0 for v in cycles)
assert [v['outage_seconds'] for v in rows['13']['variants']] == [3, 20]
assert all(v['ok'] and all(v['sequence_continuity'].values()) and v['audio_preserved']
           and v['status_received'] == 'completed' for v in rows['13']['variants'])
initial = read('lanes-initial.json')
final = rows['4']['controlled_lane_cases']
assert len(initial) == len(final) == 2
assert [v['case'] for v in initial] == ['alternation', 'overlap']
assert initial[1]['expected_failure'] is True
lane_summary = []
for i, (old, new) in enumerate(zip(initial, final)):
    assert not old['passed'] and not new['passed'] and not new['expected_failure']
    for surface in ('pre_terminal', 'final', 'reopened'):
        a, b = old['surfaces'][surface], new['surfaces'][surface]
        assert a['lanes'] == b['lanes'] and not a['passed'] and not b['passed']
        assert b['speaker_lane_conflicts'] == 0 and b['attribution_errors'] == 2
        assert b['duplication_count'] == (2 if i == 0 else 1)
        for lane, metric in b['lanes'].items():
            edits = sum(metric[k] for k in ('substitutions', 'omissions', 'additions'))
            assert metric['wer'] == edits / metric['reference_words']
            if surface != 'pre_terminal':
                assert b['max_wer'] == .095074
                assert (edits, metric['reference_words']) == ((9 if i == 0 else 13, 106) if lane == 'system' else (10, 48))
                if lane == 'microphone':
                    assert (metric['substitutions'], metric['omissions'], metric['additions']) == (0, 0, 10)
            else:
                assert b['max_wer'] == .166655
    lane_summary.append({'case': old['case'], 'final': new['surfaces']['final']['lanes']})
assert 'original expected-failure comparator rejected' in (root / 'overlap-falsifier.txt').read_text()
voice = read('voiceprint-finding.json')
assert rows['10']['bank_contains_name'] and rows['10']['recognition_seconds'] is None
assert rows['10']['bound_seconds'] == 4 and rows['10']['meeting'] == voice['meeting']
assert voice['durable_speaker_links'] == 0 and voice['visible_name_within_30_seconds'] is False
hidden = read('browser-corrected/campaign-results.json')['15']
assert [v['method'] for v in hidden['attempts']] == ['minimize', 'second-tab-front']
assert all(v['hidden'] is False for v in hidden['attempts']) and not hidden['ok']
lease25 = read('browser-lease-rerun/campaign-results.json')['16']['variants'][0]
assert lease25['seconds'] == 25 and lease25['ok'] and all(lease25['resumed_frames'].values())
assert lease25['acknowledged_commits_before'] == 3 and lease25['acknowledged_commits_preserved']
assert (lease25['published_words_before'], lease25['ordered_words_retained'], lease25['words_removed_or_revised']) == (27, 26, 1)
assert abs(lease25['stop_seconds'] - 76.9516) < .0001
lease35 = read('browser-ui-final/campaign-results.json')['16']['variants'][0]
assert lease35['seconds'] == 35 and lease35['ok'] and lease35['terminal'] == 'interrupted'
assert 'Recording interrupted' in lease35['ui_status'] and 'Reset capture' in lease35['ui_status']
assert lease35['acknowledged_commits_before'] == 3 and lease35['acknowledged_commits_preserved']
assert lease35['published_words_before'] == lease35['ordered_words_retained'] == 30
assert lease35['accepted_samples_before'] == lease35['accepted_samples_after']
assert lease35['new_capture_status'] == 'completed' and not any(lease35['resumed_frames'].values())
assert '7/7 lifecycle checks passed' in (root / 'lifecycle.txt').read_text()
assert '3/6 reshare checks passed' in (root / 'reshare.txt').read_text()
ledger = [json.loads(line) for line in (root / 'decoder-requests.jsonl').read_text().splitlines()]
assert len(ledger) == 400 and [v['request'] for v in ledger] == list(range(1, 401))
gpu = list(root.glob('gpu-*.txt'))
waiting = [line for p in gpu for line in p.read_text().splitlines() if line.startswith('vllm:num_requests_waiting{')]
assert len(waiting) == len(gpu) == 10 and all(float(line.rsplit(' ', 1)[1]) == 0 for line in waiting)
verdict = read('verdict.json')
assert verdict['counts'] == counts and verdict['rows'] == {k: v['status'] for k, v in rows.items()}
assert verdict['reshare']['verdict'] == 'BUDGET_BLOCKED'
print(json.dumps({'evidence_consistency': 'PASS', 'acceptance': 'FAIL / INCOMPLETE',
    'rows': {k: rows[k]['status'] for k in sorted(rows, key=int)}, 'counts': counts,
    'lane_quality': lane_summary, 'voiceprint': voice, 'hidden': 'UNMEASURED',
    'lease_25': lease25, 'lease_35': lease35, 'lifecycle': '7/7',
    'reshare': '3/6; BUDGET_BLOCKED; cause not independently adjudicated',
    'decoder_starts': len(ledger), 'additional_requests': 0,
    'gpu_waiting_samples': len(waiting), 'all_sampled_waiting_zero': True}, indent=2))
