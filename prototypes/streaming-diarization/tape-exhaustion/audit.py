"""Read-only check of WP29 retained measurements; no model or network calls."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[3]
evidence = root/'evidence/mvpfix/wp29'
cases = json.loads((evidence/'fixed.json').read_text())
results = [r for c in cases for r in c['results']]
assert len(cases) == 8 and len(results) == 9
for r in results:
    interrupted = r['case'] == 'lease_expiry'
    assert r['saved_status'] == ('interrupted' if interrupted else 'completed')
    assert r['reopened_status'] == r['saved_status']
    assert r['prefix_preserved'] and r['saved_equal'] and r['reopened_document_equal']
    assert r['notice'] == r['reopened_notice']
    assert r['audio']['state'] == 'partial'
    assert r['audio']['duration_ms'] == 60000
    assert float(r['mp3']['format']['duration']) == 60
    assert not r['state']['lease_armed'] and r['state']['queue'] == 0
    assert all(t['released'] and t['retained_bytes'] == 0 for t in r['state']['tapes'].values())
    if not interrupted:
        assert r['terminal_failure'] is None
        assert r['state']['accepted'] == r['state']['accounted'] == 1440000
        assert r['finalization'] == ('final' if r['case'].endswith('_only') else 'unavailable')
        assert r['events'][-1]['payload']['tape_gaps'] == (
            0 if r['case'] == 'mixed_only' else 1 if r['case'].endswith('_only') else 2)
rows = [json.loads(line) for line in (evidence/'repeat-rss.jsonl').read_text().splitlines()]
ends = [r for r in rows if r['phase'] == 'after_terminal']
assert len(ends) == 2
for i, r in enumerate(ends, 1):
    assert r['meeting'] == r['session_count'] == i
    assert r['accepted'] == r['committed'] == 9600000
    assert r['status'] == 'closed' and r['finalization'] == 'final'
    assert all(v['count'] == 0 for name, v in r['structures'].items()
               if name.startswith(('tape_', 'pending_pcm_')))
print(json.dumps(dict(
    exhaustion_sessions_passed=9, exhaustion_sessions_total=9,
    rss_sessions_finalized=2, rss_sessions_measured=2,
    rss_bytes_baseline=rows[0]['rss_bytes'],
    rss_bytes_after_first=ends[0]['rss_bytes'],
    rss_bytes_after_second=ends[1]['rss_bytes'],
    rss_bytes_second_minus_first=ends[1]['rss_bytes']-ends[0]['rss_bytes'],
), indent=2))
