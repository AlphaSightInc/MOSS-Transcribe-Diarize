"""Count terminal attribution gaps in retained WP12/WP17 sessions, no words emitted."""
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

root = Path.cwd()
records = []


def record(package, run, segments, lane_mode):
    for lane in sorted({s.get('source_lane') or 'mono' for s in segments}):
        selected = [s for s in segments if (s.get('source_lane') or 'mono') == lane]
        missing = [s for s in selected if s.get('canonical_speaker') is None]
        def words(rows):
            return sum(len(re.findall(r'[a-z0-9]+', s['text'].lower())) for s in rows)
        def seconds(rows):
            return round(sum(s['end_sample']-s['start_sample'] for s in rows)/16000, 6)
        records.append(dict(package=package, run=run, lane=lane, implementation=lane_mode,
            segments=len(selected), words=words(selected), seconds=seconds(selected),
            assigned_speakers=sorted({s['canonical_speaker'] for s in selected if s.get('canonical_speaker')}),
            unassigned_segments=len(missing), unassigned_words=words(missing), unassigned_seconds=seconds(missing),
            gaps=[dict(start=s['start_sample']/16000, end=s['end_sample']/16000,
                       words=words([s])) for s in missing]))


old = root.parent/'MOSS-Transcribe-Diarize-wt-wp12-stop-latency-identity/.wp12'
for path in sorted(old.glob('*-surface.json')):
    mode = 'accepted_overlap' if path.name.startswith('overlap-fixed-') else 'historical_control'
    record('wp12', path.stem, json.loads(path.read_text()), mode)
wp17 = root.parent/'MOSS-Transcribe-Diarize-wt-wp17-lane-quality-voiceprint/runs/wp17'
seen = set()
for line in (wp17/'surfaces.jsonl').read_text().splitlines():
    row = json.loads(line)
    snapshot = row['result'].get('snapshot', {})
    session = snapshot.get('session', {})
    if session.get('finalization_status') != 'final':
        continue
    ident = snapshot['session_id']
    if ident not in seen:
        record('wp17', ident, session['effective_transcript'], 'accepted_overlap')
        seen.add(ident)
for path in sorted((wp17/'durations').glob('*.json')):
    if path.name == 'cookies.json':
        continue
    row = json.loads(path.read_text())
    assert row['final']['snapshot']['session']['finalization_status'] == 'final'
    assert row['id'] not in seen
    seen.add(row['id'])
    record('wp17', path.stem, row['final']['snapshot']['session']['effective_transcript'], 'accepted_overlap')

surface_records = list(records)
records = []
databases = []
for package, paths in (
    ('wp12', sorted(old.glob('state-*/phase2.sqlite'))),
    ('wp17', [Path('/private/tmp/wp17/state/phase2.sqlite')]),
):
    for path in paths:
        wal = Path(str(path)+'-wal')
        assert not wal.exists() or wal.stat().st_size == 0, 'Nonempty WAL: immutable read would miss data'
        db = sqlite3.connect(f'file:{path.resolve()}?mode=ro&immutable=1',uri=True)
        saved = db.execute('''SELECT t.meeting_id,t.document_json,m.status FROM meeting_transcripts t
            JOIN meetings m USING(account_id,meeting_id)''').fetchall()
        databases.append(dict(package=package,path=str(path),saved_documents=len(saved),statuses=dict(Counter(s[2] for s in saved))))
        for ident, document, status in saved:
            if status != 'completed':
                continue
            mode = 'accepted_overlap' if package=='wp17' or path.parent.name=='state-overlap-fixed' else 'historical_control'
            segs = [dict(start_sample=round(s['start']*16000),end_sample=round(s['end']*16000),
                         text=s['text'],canonical_speaker=s.get('speaker_entity_id'),source_lane=s.get('source_lane','not_persisted'))
                    for s in json.loads(document)['segments']]
            record(package, path.parent.name+'/'+ident, segs, mode)


def summarize(records):
    totals = []
    for package, mode in sorted({(r['package'], r['implementation']) for r in records}):
        rows = [r for r in records if (r['package'],r['implementation']) == (package, mode)]
        totals.append(dict(package=package, implementation=mode, sessions=len({r['run'] for r in rows}),
            lane_rows=len(rows), affected_sessions=len({r['run'] for r in rows if r['unassigned_segments']}),
            **{key:round(sum(r[key] for r in rows),6) for key in
               ('segments','words','seconds','unassigned_segments','unassigned_words','unassigned_seconds')}))
    return totals


print(json.dumps(dict(totals=summarize(surface_records), lanes=surface_records,
    saved_store_totals=summarize(records), saved_store_lanes=records, databases=databases,
    population='Surface census: all extant WP12 surface JSONs, distinct final WP17 quality snapshots plus all 12 duration sessions. Saved-store census separately includes all completed meetings from 17 WP12 state databases and the WP17 state database, including recognition. These populations overlap: do not add their denominators. WP12 saved documents lack lane metadata; no lane guessed. Historical acoustic controls separated from accepted overlap implementation. Durations sum segment intervals, not meeting time.'), indent=2))
