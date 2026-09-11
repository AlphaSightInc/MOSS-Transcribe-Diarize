"""A late Stop conflict does not identify what terminalized the cached meeting."""
import asyncio
import pytest
from fastapi.testclient import TestClient
from tests.phase2 import test_owner_bound_live_meeting as fixture


@pytest.mark.parametrize('ending', ['lease_expiry', 'explicit_abort'])
def test_late_stop_has_same_refusal_for_distinct_prior_endings(tmp_path, ending):
    database = tmp_path / 'account.sqlite3'
    sessions = asyncio.run(fixture.provision(database))
    app = fixture.make_app(database, lease_seconds=.1 if ending == 'lease_expiry' else 30)
    with TestClient(app, base_url='https://moss.test') as client:
        fixture.session(client, sessions['a'])
        meeting_id = client.post('/api/live/sessions').json()['id']
        if ending == 'explicit_abort':
            assert client.post(f'/api/live/sessions/{meeting_id}/abort',
                               json={'reason': 'earlier explicit abort'}).status_code == 200
        terminal = fixture.wait_snapshot(client, meeting_id,
            lambda row: row['snapshot']['session']['status'] != 'active')
        assert terminal['snapshot']['session']['finalization_status'] == 'not_started'
        response = client.post(f'/api/live/sessions/{meeting_id}/stop')
        assert response.status_code == 409
        assert response.json() == {'detail': 'live Meeting is terminal.'}
        if ending == 'lease_expiry':
            assert 'helper_lease_expired' in str(terminal)
