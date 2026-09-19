"""WP9: naming follows owned durable meetings, never display-label equality."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import create_phase2_app
from test_owner_bound_live_meeting import (
    make_app, provision, session, heartbeat, feed_two_lane_span, wait_snapshot, EligibleIdentity,
)


@pytest.mark.parametrize('restart', [False, True])
@pytest.mark.parametrize('enrolled', [False, True])
def test_saved_live_rename_after_stop_and_restart(tmp_path, restart, enrolled):
    database = tmp_path / 'm.sqlite'
    sessions = asyncio.run(provision(database))
    app = make_app(database, **({'identity_factory': EligibleIdentity} if enrolled else {}))
    with TestClient(app, base_url='https://moss.test') as client:
        session(client, sessions['a'])
        mid = client.post('/api/live/sessions').json()['id']
        client.post(f'/api/live/sessions/{mid}/heartbeat', json=heartbeat())
        feed_two_lane_span(client, mid)
        wait_snapshot(client, mid, lambda b: b['meeting_transcript_version'] == 1)
        if enrolled:
            assert client.put(f'/api/meetings/{mid}/speakers/speaker-0001/name',
                              json={'label': 'Before'}).json()['enrollment'] == 'enrolled'
        assert client.post(f'/api/live/sessions/{mid}/stop', json={'deadline': 30}).status_code == 200
        if not restart:
            check_rename(client, app, sessions, mid, 'speaker-0001', enrolled)
    if restart:
        with TestClient(create_phase2_app(database_path=database), base_url='https://moss.test') as client:
            check_rename(client, client.app, sessions, mid, 'speaker-0001', enrolled)


def check_rename(client, app, sessions, mid, sid, enrolled):
    session(client, sessions['a-observer'])
    original = client.get(f'/api/meetings/{mid}').json()
    for label in ['After Stop', 'After reload']:
        result = client.put(f'/api/meetings/{mid}/speakers/{sid}/name', json={'label': label})
        assert result.status_code == 200, result.text
        assert result.json()['enrollment'] == ('enrolled' if enrolled else 'unavailable')
        saved = client.get(f'/api/meetings/{mid}').json()
        assert saved['status'] == original['status'] == 'completed'
        assert saved['transcript_version'] == original['transcript_version'] + 1
        assert saved['transcript']['segments'][0]['speaker'] == label
        assert saved['transcript']['segments'][0]['speaker_entity_id'] == sid
        history = next(m for m in client.get('/api/meetings').json()['meetings'] if m['id'] == mid)
        assert history == saved
        assert app.state.phase2_speaker_identity.pending_count == 0
        bank = client.get('/api/voiceprints').json()['voiceprints']
        assert len(bank) == int(enrolled)
        if enrolled:
            assert (bank[0]['label'], bank[0]['sample_count']) == (label, 1)
        original = saved
    session(client, sessions['b'])
    assert client.put(f'/api/meetings/{mid}/speakers/{sid}/name', json={'label': 'Foreign'}).status_code == 404
    session(client, sessions['a'])
    assert client.get(f'/api/meetings/{mid}').json() == original
    assert client.put(f'/api/meetings/{mid}/speakers/missing/name', json={'label': 'Unknown'}).status_code == 404
    assert client.put(f'/api/meetings/{mid}/speakers/{sid}/name', json={'label': '  '}).status_code == 400


@pytest.mark.parametrize('mode', ['file', 'live'])
@pytest.mark.parametrize('status', ['completed', 'failed', 'interrupted'])
def test_saved_exact_id_duplicate_labels_and_legacy_file_tokens(tmp_path, mode, status):
    database = tmp_path / 'm.sqlite'
    sessions = asyncio.run(provision(database))
    app = create_phase2_app(database_path=database)
    with TestClient(app, base_url='https://moss.test') as client:
        session(client, sessions['a'])
        async def seed():
            account = await app.state.phase2_store.account_for_session(sessions['a'])
            handle = await app.state.phase2_store.workspace(account).create_meeting(mode)
            segments = [dict(id=str(i), start=i, end=i+1, speaker=s, text='synthetic words')
                        for i, s in enumerate(['S01', 'S02', 'S01', 'S00'])]
            if mode == 'live':
                for s in segments[:3]:
                    s['speaker_entity_id'] = s['speaker']
                    s['speaker'] = 'Same name'
            await handle.finish_with_transcript({'segments': segments}, status)
            return handle.meeting_id
        mid = client.portal.call(seed)
        for sid, label in [('S01', 'S02'), ('S01', 'Changed'), ('S02', 'Other')]:
            response = client.put(f'/api/meetings/{mid}/speakers/{sid}/name',
                                  json={'label': label, 'save_voiceprint': False})
            assert response.status_code == 200, response.text
            assert response.json()['enrollment'] == 'not_requested'
        saved = client.get(f'/api/meetings/{mid}').json()
        rows = saved['transcript']['segments']
        assert [s['speaker'] for s in rows] == ['Changed', 'Other', 'Changed', 'Speaker uncertain']
        assert [s.get('speaker_entity_id') for s in rows] == ['S01', 'S02', 'S01', 'S00']
        assert saved['needs_review'] is True
        assert saved['status'] == status
        assert client.put(f'/api/meetings/{mid}/speakers/S00/name', json={'label': 'No'}).status_code == 404
        assert client.get('/api/voiceprints').json()['voiceprints'] == []
