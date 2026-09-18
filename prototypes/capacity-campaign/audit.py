"""WP30 retained-run audit: no server or decoder calls; never emits transcript text.

COMMON Python prototypes/capacity-campaign/audit.py evidence/mvpfix/wp30/<run>
Checks metadata against action records, original final snapshots and reopened SQLite.
A failed campaign is reported as failed, not turned into a successful durability claim.
"""
import json
from pathlib import Path
import sqlite3
import sys


def audit(out):
    result = json.loads((out/'result.json').read_text())
    scratch = Path(result['scratch'])
    def rows(name):
        p = out/name
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
    actions, telemetry, decoder = rows('actions.jsonl'), rows('telemetry.jsonl'), rows('decoder.jsonl')
    starts = [r for r in decoder if r['kind']=='start']
    finishes = [r for r in decoder if r['kind']=='finish']
    assert result['decoder_calls']==len(starts)
    assert len(starts)==len(finishes), 'decoder requests left unfinished'
    assert max([r['active'] for r in decoder] or [0])<=2
    requests = rows('requests.jsonl')
    assert len(requests)==len(starts), 'wire request ledger differs from decoder calls'
    if result['stub_latency'] is None:
        assert len(requests)<=600
    assert not any(r['kind'] in ('pause','resume') for r in actions)
    assert len({r['pid'] for r in telemetry})==1, 'repeat must use the same process'
    con=sqlite3.connect((scratch/'state/phase2.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    saved={row[0]:(row[1],json.loads(row[2])) for row in con.execute(
        'SELECT m.meeting_id,m.status,t.document_json FROM meetings m JOIN meeting_transcripts t USING(account_id,meeting_id)')}
    con.close()
    sessions=[]
    for r in sorted(result['session_results'],key=lambda x:(x['repeat'],x['ordinal'])):
        frames=[x for x in actions if x['kind']=='frame' and x['repeat']==r['repeat'] and x['ordinal']==r['ordinal']]
        assert max([x['acknowledged_frames'] for x in frames] or [0])<=r['acknowledged_frames']
        snap_path=scratch/f"snapshot-{r['repeat']}-{r['ordinal']}.json"
        d=dict(repeat=r['repeat'],session=r['ordinal'],acknowledged_frames=r['acknowledged_frames'],
            retries=r['retries'],wrong_owner_failures=r['wrong_owner_failures'],foreign_probes=r['foreign_probes'],
            first_text_seconds=r.get('first_text_seconds'),max_update_gap_seconds=r.get('max_live_update_gap_seconds'),
            p95_update_gap_seconds=r.get('p95_live_update_gap_seconds'),capture_seconds=r.get('capture_elapsed_seconds'),
            stop_to_final_seconds=r.get('stop_to_final_seconds'),finalization=r.get('finalization_status'),
            error=r.get('error'),failure_code=r.get('failure_code'),http_failure_code=r.get('http_failure_code'),
            saved_words=r.get('saved_words'),unaccounted_acknowledged_samples=r.get('unaccounted_acknowledged_samples'))
        if snap_path.exists():
            snap=json.loads(snap_path.read_text())['session']
            status,document=saved[r['session_id']]
            expected=[s['text'] for s in snap['effective_transcript']]
            actual=[s['text'] for s in document['segments']]
            d['sqlite_words_equal_terminal']=actual==expected
            assert d['sqlite_words_equal_terminal']==r['saved_text_equal']
            d['saved_status']=status
            d['accepted_samples']=snap['accepted_samples']
            d['accounted_samples']=snap['accounted_samples']
            assert snap['accepted_samples']==r['accepted_samples']
            assert snap['accounted_samples']==r['accounted_samples']
            d['lanes']={lane:dict(segments=len(parts),words=sum(len(s['text'].split()) for s in parts),
                first_sample=min([s['start_sample'] for s in parts] or [0]),last_sample=max([s['end_sample'] for s in parts] or [0]))
                for lane in ('system','microphone') if (parts:=[s for s in snap['effective_transcript'] if s.get('source_lane')==lane])}
        sessions.append(d)
    flat=[s for t in telemetry for r in t['runtimes'] for s in r['sessions']]
    runtime=[r for t in telemetry for r in t['runtimes']]
    checkpoints=[]
    for t in telemetry:
        if not t.get('checkpoint'):continue
        state=[s for r in t['runtimes'] for s in r['sessions']]
        checkpoints.append(dict(label=t['checkpoint'],rss_mib=t['rss_bytes']/1048576,
            traced_mib=t['python_bytes']/1048576,retained_sessions=len(state),
            retained_album_entries=sum(o['album_entries'] for s in state for o in s['owners'].values()),
            retained_sweep_spans=sum(o['sweep_spans'] for s in state for o in s['owners'].values()),
            retained_tape_bytes=sum(sum(s['tapes'].values()) for s in state),replay_acks=sum(t['replay_acks'])))
    tapes=rows('tape-release.jsonl')
    return dict(run=out.name,source=result['source_revision'],sessions=result['sessions'],seconds=result['seconds'],repeat=result['repeat'],
        stub_latency=result['stub_latency'],campaign_completed=result.get('campaign_completed'),campaign_clean=result['clean'],
        requests=len(requests),peak_own_inflight=max([r['active'] for r in decoder] or [0]),
        contention_samples=sum(r['foreign_load_detected'] for r in result['resources']),resource_samples=len(result['resources']),
        maximum_pending_signals=max([r['pending_signals'] for r in runtime] or [0]),
        maximum_ready_sessions=max([r['ready'] for r in runtime] or [0]),
        maximum_session_canonical_queue=max([s['queues']['live_canonical'] for s in flat] or [0]),
        maximum_session_refinement_queue=max([s['queues']['live_refinement'] for s in flat] or [0]),
        maximum_aggregate_canonical_queue=max([sum(s['queues']['live_canonical'] for r in t['runtimes'] for s in r['sessions']) for t in telemetry] or [0]),
        peak_rss_mib=max([t['rss_bytes']/1048576 for t in telemetry] or [0]),
        checkpoints=checkpoints,session_results=sessions,failures=result['failures'],fairness=result.get('fairness'),
        tape_releases=len(tapes),retained_bytes_after_release=sum(a['retained_bytes'] for t in tapes for a in t['after'].values()),
        word_loss_vs_acknowledged_audio='unmeasured: audio acknowledgements contain no word labels')


if __name__=='__main__':
    print(json.dumps(audit(Path(sys.argv[1])),indent=2))
