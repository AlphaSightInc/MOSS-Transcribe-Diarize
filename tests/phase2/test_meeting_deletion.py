from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import create_phase2_app
from tests.phase2.test_owner_bound_live_meeting import (
    EligibleIdentity, feed_two_lane_span, make_app, provision, session, wait_snapshot,
)
from tests.phase2.test_voiceprint_matching import observation


def seed(client, token, *, status='completed', mode='file'):
    async def create():
        store = client.app.state.phase2_store
        account = await store.account_for_session(token)
        handle = await store.workspace(account).create_meeting(mode)
        await handle.commit_transcript({'segments': [{'id': 's', 'start': 0, 'end': 1, 'speaker': 'Alex', 'text': 'synthetic words'}]})
        await handle.record_audio_unavailable()
        if status != 'active':
            await handle.finish(status, notice='synthetic outcome')
        async with store._mutation():
            await store._connection.execute("INSERT INTO meeting_speakers VALUES (?, ?, 's', 'Alex', NULL)", (account.account_id, handle.meeting_id))
            await store._connection.execute("INSERT INTO llm_artifacts VALUES (?, ?, 'summary', 'summary', 'done', '{}', '{}', 1, 1)", (account.account_id, handle.meeting_id))
        return account.account_id, handle.meeting_id
    return client.portal.call(create)


@pytest.mark.parametrize('status', ['completed', 'interrupted', 'failed'])
def test_delete_terminal_removes_rows_and_all_audio_and_is_account_owned(tmp_path: Path, status):
    database = tmp_path / 'moss.sqlite3'
    tokens = asyncio.run(provision(database))
    audio = tmp_path / 'audio'
    app = create_phase2_app(database_path=database, meeting_audio_root=audio)
    with TestClient(app, base_url='https://moss.test') as client:
        account, mid = seed(client, tokens['a'], status=status)
        directory = audio / account / mid
        directory.mkdir(parents=True)
        for name in ('audio.mp3', 'audio.partial.mp3', '.audio.staged.mp3', '.live-mix.pcm'):
            (directory / name).write_bytes(b'synthetic audio')
        session(client, tokens['b'])
        assert client.delete(f'/api/meetings/{mid}').status_code == 404
        assert len(list(directory.iterdir())) == 4
        session(client, tokens['a-observer'])
        assert client.delete(f'/api/meetings/{mid}', headers={'Origin': 'https://foreign.test'}).status_code == 403
        assert client.delete(f'/api/meetings/{mid}').status_code == 204
        assert not list(directory.iterdir())
        assert client.get('/api/meetings').json() == {'meetings': []}
        assert client.delete(f'/api/meetings/{mid}').status_code == 404
        with sqlite3.connect(database) as db:
            for table in ('meetings', 'meeting_transcripts', 'meeting_speakers', 'meeting_outcomes', 'llm_artifacts', 'meeting_audio'):
                assert db.execute(f'SELECT COUNT(*) FROM {table} WHERE meeting_id=?', (mid,)).fetchone()[0] == 0
            assert db.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('mode', ['live', 'file'])
def test_delete_all_keeps_running_and_foreign_sessions(tmp_path: Path, mode):
    database = tmp_path / 'moss.sqlite3'
    tokens = asyncio.run(provision(database))
    app = create_phase2_app(database_path=database, meeting_audio_root=tmp_path / 'audio')
    with TestClient(app, base_url='https://moss.test') as client:
        _, running = seed(client, tokens['a'], status='active', mode=mode)
        _, terminal = seed(client, tokens['a'])
        _, foreign = seed(client, tokens['b'])
        session(client, tokens['a'])
        before = client.get(f'/api/meetings/{running}').json()
        assert client.delete(f'/api/meetings/{running}').status_code == 409
        assert client.get(f'/api/meetings/{running}').json() == before
        result = client.delete('/api/meetings')
        assert result.status_code == 200
        assert result.json() == {'deleted': 1, 'kept': [{'meeting_id': running, 'reason': 'Stop recording first.'}]}
        assert [m['id'] for m in client.get('/api/meetings').json()['meetings']] == [running]
        assert client.get(f'/api/meetings/{terminal}').status_code == 404
        session(client, tokens['b'])
        assert client.get(f'/api/meetings/{foreign}').status_code == 200


def test_delete_preserves_saved_voiceprint_and_real_matching_path(tmp_path: Path):
    database = tmp_path / 'moss.sqlite3'
    tokens = asyncio.run(provision(database))
    app = make_app(database, identity_factory=EligibleIdentity)
    with TestClient(app, base_url='https://moss.test') as client:
        session(client, tokens['a'])
        mid = client.post('/api/live/sessions').json()['id']
        feed_two_lane_span(client, mid)
        wait_snapshot(client, mid, lambda body: body['meeting_transcript_version'] == 1)
        profile = client.put(f'/api/meetings/{mid}/speakers/speaker-0001/name', json={'label': 'Alex'}).json()['voiceprint_id']
        assert client.post(f'/api/live/sessions/{mid}/stop', json={'deadline': 2.0}).status_code == 200
        bank = client.get('/api/voiceprints').json()
        assert client.delete(f'/api/meetings/{mid}').status_code == 204
        assert client.get('/api/voiceprints').json() == bank
        async def match():
            store = app.state.phase2_store
            account = await store.account_for_session(tokens['a'])
            handle = await store.workspace(account).create_meeting('file')
            prepared = await app.state.phase2_speaker_identity.prepare_matches(handle, (observation((.6, .8), embedder='wespeaker:test-revision'),))
            assert prepared[2][0][1].voiceprint_id == profile
        client.portal.call(match)
        with sqlite3.connect(database) as db:
            assert db.execute('SELECT source_meeting_id FROM voiceprint_samples WHERE voiceprint_id=?', (profile,)).fetchone() == (None,)


def test_audio_cleanup_failure_retains_rows_and_reports_reason(tmp_path: Path, monkeypatch):
    database = tmp_path / 'moss.sqlite3'
    tokens = asyncio.run(provision(database))
    app = create_phase2_app(database_path=database, meeting_audio_root=tmp_path / 'audio')
    with TestClient(app, base_url='https://moss.test') as client:
        _, mid = seed(client, tokens['a'])
        def fail(*args):
            raise OSError('synthetic disk failure')
        monkeypatch.setattr(app.state.phase2_audio_archive, 'discard_unrecorded', fail)
        session(client, tokens['a'])
        result = client.delete(f'/api/meetings/{mid}')
        assert result.status_code == 503
        assert 'audio' in result.json()['detail'].lower()
        assert client.get(f'/api/meetings/{mid}').status_code == 200


def test_delete_keeps_post_stop_refinement_until_writer_finishes(tmp_path: Path, monkeypatch):
    database = tmp_path / 'moss.sqlite3'
    tokens = asyncio.run(provision(database))
    app = make_app(database)
    with TestClient(app, base_url='https://moss.test') as client:
        _, mid = seed(client, tokens['a'], mode='live')
        session(client, tokens['a'])
        monkeypatch.setattr(app.state.phase2_live, 'refinement_running', lambda meeting_id: meeting_id == mid)
        result = client.delete(f'/api/meetings/{mid}')
        assert result.status_code == 409
        assert result.json()['detail'] == 'Wait for transcript clean-up to finish.'
        assert client.delete('/api/meetings').json() == {
            'deleted': 0, 'kept': [{'meeting_id': mid, 'reason': 'Wait for transcript clean-up to finish.'}]
        }
        monkeypatch.setattr(app.state.phase2_live, 'refinement_running', lambda meeting_id: False)
        assert client.delete(f'/api/meetings/{mid}').status_code == 204


def test_delete_removes_retained_file_and_url_staging(tmp_path: Path):
    database = tmp_path / 'moss.sqlite3'
    tokens = asyncio.run(provision(database))
    app = create_phase2_app(database_path=database, file_runner=object(),
                           file_work_root=tmp_path / 'file-work', meeting_audio_root=tmp_path / 'audio')
    with TestClient(app, base_url='https://moss.test') as client:
        account, mid = seed(client, tokens['a'], status='interrupted')
        directory = app.state.phase2_file_tasks.retained_root / account / mid
        directory.mkdir(parents=True)
        (directory / 'input.wav').write_bytes(b'synthetic input')
        (directory / 'mix.wav').write_bytes(b'synthetic mix')
        session(client, tokens['a'])
        assert client.delete(f'/api/meetings/{mid}').status_code == 204
        assert not directory.exists()
