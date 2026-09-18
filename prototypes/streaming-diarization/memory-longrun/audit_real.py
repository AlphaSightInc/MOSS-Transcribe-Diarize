"""WP22 retained-run audit. Read completed evidence plus checkout-local SQLite/audio.
Usage: COMMON Python <this-file> evidence/mvpfix/wp22/real-<stamp>
No decoder calls. Missing data or a violated durability invariant fails explicitly.
"""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

out = Path(sys.argv[1])
scratch = Path('.wp22') / out.name
result = json.loads((out / 'result.json').read_text())
rows = lambda name: [json.loads(x) for x in (out / name).read_text().splitlines()]
requests = rows('requests.jsonl')
decoder = rows('decoder.jsonl')
tapes = rows('tape-release.jsonl')
rss = rows('rss.jsonl')
assert 'error' not in result, result.get('error')
assert result['source_revision'] == 'a28eecd9bac41e8aea09d1ee5495bfa3c1aef900'
assert result['outcome'] == 'final' and result['saved_status'] == 'completed'
assert result['restart_sqlite_status'] == 'completed'
assert result['accepted_samples'] == result['accounted_samples'] == 28_800_000
assert result['acknowledged_frames'] == 7200
assert result['capture_paused_seconds'] == 0
assert result['snapshot_saved_words_equal']
assert result['decoder_requests'] == len(requests)
assert result['prior_requests'] + len(requests) <= 2600
starts = [x for x in decoder if x['kind'] == 'start']
ends = [x for x in decoder if x['kind'] == 'finish']
assert len(starts) == len(ends) == len(requests)
assert max(x['active'] for x in decoder) <= 2
assert len(tapes) == 1
assert set(tapes[0]['before']) == {'system', 'microphone', 'mixed'}
for lane, before in tapes[0]['before'].items():
    assert before['complete'] and before['refused_samples'] == 0
    assert before['retained_bytes'] == before['capacity_bytes'] == 57_600_000
    after = tapes[0]['after'][lane]
    assert after['released'] and after['retained_bytes'] == 0
snapshot = json.loads((scratch / 'snapshot.json').read_text())
con = sqlite3.connect((scratch / 'state/phase2.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
durable = con.execute('SELECT m.status,t.document_json FROM meetings m JOIN meeting_transcripts t USING(account_id,meeting_id)').fetchall()
con.close()
assert len(durable) == 1 and durable[0][0] == 'completed'
words = [s['text'] for s in json.loads(durable[0][1])['segments']]
assert words == [s['text'] for s in snapshot['session']['effective_transcript']]
assert sum(len(w.split()) for w in words) == result['saved_words'] > 0
probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_name,sample_rate,channels','-of','json',str(scratch/'saved.mp3')], text=True))
assert probe == result['mp3_probe']
assert float(probe['format']['duration']) == 1800
assert result['audio']['duration_ms'] == 1_800_000
resources = result['resources']
capture_started = result['stop_requested_monotonic'] - result['capture_elapsed_seconds']
rss_timed = [dict(elapsed=r['time']-capture_started, rss_bytes=r['rss_bytes']) for r in rss]
checkpoints = [min(rss_timed, key=lambda r: abs(r['elapsed']-s)) for s in (300,900,1800)]
capture_resources = [r for r in resources if r['elapsed'] <= result['capture_elapsed_seconds']]
audit = dict(source_revision=result['source_revision'], saved_words=result['saved_words'],
    sqlite_words_equal_terminal=True, mp3_seconds=float(probe['format']['duration']),
    accepted_samples=result['accepted_samples'], acknowledged_frames=result['acknowledged_frames'],
    stop_to_final_seconds=result['stop_to_final_seconds'], requests=len(requests),
    prior_requests=result['prior_requests'], peak_in_flight=max(x['active'] for x in decoder),
    resource_samples=len(resources), independent_rss_samples=len(rss),
    foreign_resource_samples=sum(r['foreign_load_detected'] for r in resources),
    max_shared_running=max(r['metrics']['num_requests_running'] for r in resources),
    max_shared_waiting=max(r['metrics']['num_requests_waiting'] for r in resources),
    rss_checkpoints=[dict(elapsed=r['elapsed'],rss_bytes=r['rss_bytes']) for r in checkpoints],
    capture_first_rss_bytes=resources[0]['rss_bytes'],
    capture_last_rss_bytes=capture_resources[-1]['rss_bytes'],
    capture_last_elapsed=capture_resources[-1]['elapsed'],
    final_rss_bytes=resources[-1]['rss_bytes'],
    peak_sampled_rss_bytes=max([r['rss_bytes'] for r in resources]+[r['rss_bytes'] for r in rss]),
    total_tape_bytes_before_release=sum(t['retained_bytes'] for t in tapes[0]['before'].values()),
    total_tape_bytes_after_release=sum(t['retained_bytes'] for t in tapes[0]['after'].values()))
audit['lane_output'] = {}
for lane in ('system', 'microphone'):
    segments = [r for r in snapshot['session']['effective_transcript'] if r['source_lane'] == lane]
    audit['lane_output'][lane] = dict(segments=len(segments),
        words=sum(len(r['text'].split()) for r in segments),
        last_end_seconds=max(r['end_sample'] for r in segments)/16000,
        unattributed_segments=sum(r['canonical_speaker'] is None for r in segments))
print(json.dumps(audit, indent=2))
