"""WP2 consumer evidence probe (absorbed from the throwaway prototype): can optional lane preserve independent overlapping speech?
Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> evidence/mvpfix/wp2/consumer_probe.py
No provider/audio; scratch persistence inside this worktree. Full state at each boundary.
"""
import asyncio, json, subprocess, tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from moss_transcribe_diarize.app.phase2 import create_phase2_app
from moss_transcribe_diarize.app import phase2
import sqlite3
# Same semantic-only runtime override as tests/phase2/conftest.py.
phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
print("SEMANTIC TEST SQLITE", sqlite3.sqlite_version, "production requires 3.53.4")

HERE = Path(__file__).resolve().parent
CORPUS = Path('/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus')
segments = []
names = {}
for lane, clip in [('system', 'interview_bill_ackman_60s'), ('microphone', 'interview_keyu_jin_60s')]:
    for i, line in enumerate((CORPUS / clip / 'reference.jsonl').read_text().splitlines()):
        row = json.loads(line)
        key = (lane, row['speaker'])
        names.setdefault(key, f'speaker-{len(names)+1:04d}')
        segments.append({k: row[k] for k in ('start', 'end', 'text')} | {'id': f'{lane}-{i}', 'speaker': row['speaker'], 'speaker_entity_id': names[key], 'source_lane': lane})
segments.sort(key=lambda s: (s['start'], s['source_lane'] != 'system', s['end']))
fixtures = {'overlap': {'schema_version': 2, 'segments': segments}, 'legacy': {'segments': [{k:v for k,v in s.items() if k != 'source_lane'} for s in segments if s['source_lane'] == 'system']}}
(HERE / 'fixtures.json').write_text(json.dumps(fixtures, indent=2, ensure_ascii=False)+'\n')
outputs = {}
with tempfile.TemporaryDirectory(prefix='PROTOTYPE-wipe-', dir=HERE) as scratch:
    app = create_phase2_app(database_path=Path(scratch)/'scratch.sqlite3', open_workspace=True)
    with TestClient(app, base_url='https://testserver') as client:
        client.post('/api/workspace/bootstrap').raise_for_status()
        async def persist(doc):
            store = app.state.phase2_store
            account, _ = await store.bootstrap_browser(None, open_workspace=True)
            handle = await store.workspace(account).create_meeting('live')
            version = await handle.commit_transcript(doc, terminal=True)
            return handle.meeting_id, version, (await handle.snapshot()).to_dict()
        for key, doc in fixtures.items():
            print('FIXTURE', key, json.dumps(doc, ensure_ascii=False))
            mid, version, saved = client.portal.call(persist, doc)
            print('SQLITE', key, version, json.dumps(saved, ensure_ascii=False))
            fetched = client.get('/api/meetings/'+mid).json()
            print('GET', key, json.dumps(fetched, ensure_ascii=False))
            history = client.get('/api/meetings').json()
            print('HISTORY', key, json.dumps(history, ensure_ascii=False))
            assert fetched['transcript'] == doc
            outputs[key] = fetched
(HERE / 'meetings.json').write_text(json.dumps(outputs, indent=2, ensure_ascii=False)+'\n')
subprocess.run(['node', 'evidence/mvpfix/wp2/consumer_probe.mjs'], check=True)
