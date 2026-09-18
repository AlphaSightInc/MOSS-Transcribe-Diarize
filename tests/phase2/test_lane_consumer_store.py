"""Tagged overlap and legacy documents survive the schema-v2 persistence boundary."""
import asyncio
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from moss_transcribe_diarize.app.phase2 import create_phase2_app

FIXTURES = json.loads((Path(__file__).resolve().parents[2] / 'evidence/mvpfix/wp2/fixtures.json').read_text())

@pytest.mark.parametrize('fixture', ['overlap', 'legacy'])
def test_lane_document_commit_terminal_reopen_get_history(tmp_path, fixture):
    database = tmp_path / 'moss.sqlite3'
    document = FIXTURES[fixture]
    with TestClient(create_phase2_app(database_path=database, open_workspace=True)) as client:
        client.post('/api/workspace/bootstrap').raise_for_status()
        async def commit():
            store = client.app.state.phase2_store
            assert await store.user_version() == 2
            account, _ = await store.bootstrap_browser(None, open_workspace=True)
            handle = await store.workspace(account).create_meeting('live')
            assert await handle.commit_transcript(document) == 1
            assert (await handle.snapshot()).transcript == document
            await handle.rename('Independent lanes')
            assert await handle.finish_with_transcript(document, 'completed') == 2
            return handle.meeting_id
        meeting_id = client.portal.call(commit)
    # New connection/application, exercising persisted bytes rather than a cached object.
    with TestClient(create_phase2_app(database_path=database, open_workspace=True)) as client:
        client.post('/api/workspace/bootstrap').raise_for_status()
        meeting = client.get('/api/meetings/' + meeting_id).json()
        assert meeting['transcript'] == document
        assert meeting['transcript_version'] == 2
        assert meeting['status'] == 'completed'
        assert meeting['title'] == 'Independent lanes'
        assert client.get('/api/meetings').json()['meetings'] == [meeting]
