"""A failed last decode is not a refused HTTP Stop."""
import asyncio

import pytest
from fastapi.testclient import TestClient
from tests.phase2 import test_owner_bound_live_meeting as fixture


@pytest.mark.parametrize('failure', ['decode_failed', 'no_transcript', 'finalizer_defect'])
def test_successful_stop_can_be_followed_by_failed_finalization(tmp_path, monkeypatch, failure):
    database = tmp_path / 'account.sqlite3'
    sessions = asyncio.run(fixture.provision(database))
    app = fixture.make_app(database, terminal_text='')
    if failure == 'decode_failed':
        def failed_decode(*args, **kwargs):
            raise RuntimeError('controlled provider failure')
        monkeypatch.setattr(fixture.WholeMeetingStub, 'transcribe', failed_decode)
    with TestClient(app, base_url='https://moss.test') as client:
        fixture.session(client, sessions['a'])
        meeting_id = client.post('/api/live/sessions').json()['id']
        fixture.feed_two_lane_span(client, meeting_id)
        fixture.wait_snapshot(client, meeting_id, lambda row: row['meeting_transcript_version'] > 0)
        if failure == 'finalizer_defect':
            def defect(**kwargs):
                raise ZeroDivisionError('controlled finalizer defect')
            monkeypatch.setattr(app.state.phase2_live.runtime._terminal_finalizer, 'finalize', defect)
        stopped = client.post(f'/api/live/sessions/{meeting_id}/stop', json={'deadline': 2.0})
        assert stopped.status_code == 200
        after = fixture.wait_snapshot(client, meeting_id,
            lambda row: row['snapshot']['session']['finalization_status'] == 'failed')
        assert after['snapshot']['session']['status'] == 'closed'
        assert after['snapshot']['terminal_failure'] is None
        assert after['snapshot']['session']['effective_transcript']
        events = app.state.phase2_live.runtime.events(meeting_id)
        event = next(row for row in events if row.kind == 'terminal_finalization_failed')
        assert event.payload.get('outcome', event.payload.get('reason')) == failure
        assert client.get(f'/api/meetings/{meeting_id}').json()['status'] == 'completed'
