"""PROTOTYPE absorbed as WP9 replay bench: durable names across the capture boundary.
Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python prototypes/rename-after-stop/run.py
Synthetic words; local ASGI stack and disposable SQLite only; no decoder requests.
Every action prints route/status, durable document, history and private bank state.
Falsifier: the owner cannot rename an opened meeting, or label selection changes IDs.
"""
import argparse
import asyncio
import json
import sys
import tempfile
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/phase2'))
from fastapi.testclient import TestClient
from test_owner_bound_live_meeting import (
    make_app, provision, session, heartbeat, feed_two_lane_span, wait_snapshot,
)
from moss_transcribe_diarize.app.phase2 import create_phase2_app
from moss_transcribe_diarize.app import phase2
# Same semantic-only override as tests/phase2/conftest.py, never production.
phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
from moss_transcribe_diarize.subtitle import subtitle_segments_from_transcript


def inspect(client, case, meeting_id, speaker_id):
    route = f'/api/meetings/{meeting_id}/speakers/{speaker_id}/name'
    label = f'WP9 {case}'
    response = client.put(route, json={'label': label, 'save_voiceprint': False})
    meeting = client.get(f'/api/meetings/{meeting_id}').json()
    history = client.get('/api/meetings').json()['meetings']
    row = dict(case=case, route=route, status=response.status_code, response=response.json(),
               meeting=meeting, history=next(m for m in history if m['id'] == meeting_id),
               bank=client.get('/api/voiceprints').json(),
               history_card_speaker_field=False)
    print(json.dumps(row), flush=True)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'evidence/mvpfix/wp9/prototype-latest.json')
    args = parser.parse_args()
    rows = []
    with tempfile.TemporaryDirectory(prefix='wp9-', dir=ROOT / '.wp9runtime/tmp') as scratch:
        database = Path(scratch) / 'm.sqlite'
        sessions = asyncio.run(provision(database))
        app = make_app(database)
        with TestClient(app, base_url='https://moss.test') as client:
            session(client, sessions['a'])
            meeting_id = client.post('/api/live/sessions').json()['id']
            client.post(f'/api/live/sessions/{meeting_id}/heartbeat', json=heartbeat())
            feed_two_lane_span(client, meeting_id)
            wait_snapshot(client, meeting_id, lambda body: body['meeting_transcript_version'] == 1)
            rows.append(inspect(client, 'capture', meeting_id, 'speaker-0001'))
            stopped = client.post(f'/api/live/sessions/{meeting_id}/stop', json={'deadline': 30})
            print(json.dumps({'action': 'Stop', 'status': stopped.status_code}), flush=True)
            rows.append(inspect(client, 'after_stop', meeting_id, 'speaker-0001'))
            session(client, sessions['a-observer'])
            rows.append(inspect(client, 'reload', meeting_id, 'speaker-0001'))
        # A new process-equivalent app has no live bindings, including for old meetings.
        app = create_phase2_app(database_path=database)
        with TestClient(app, base_url='https://moss.test') as client:
            session(client, sessions['a'])
            rows.append(inspect(client, 'history', meeting_id, 'speaker-0001'))
            async def seed_file():
                account = await app.state.phase2_store.account_for_session(sessions['a'])
                handle = await app.state.phase2_store.workspace(account).create_meeting('file')
                document = {'segments': [s.to_dict() for s in subtitle_segments_from_transcript(
                    '[0][S01]synthetic file words[1]', postprocess=False)]}
                await handle.finish_with_transcript(document, 'completed')
                return handle.meeting_id
            file_id = client.portal.call(seed_file)
            rows.append(inspect(client, 'file', file_id, 'S01'))
    args.output.write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps({'rename_successes': sum(r['status'] == 200 for r in rows), 'cases': len(rows),
                      'decoder_requests': 0}), flush=True)


if __name__ == '__main__':
    main()
