"""Required workspace reachability API contract, independent of browser binaries.
Real desktop/mobile rendering remains in test_workspace_reachability_browser.py.
"""
import hashlib
import os
import re
import time
from pathlib import Path
from fastapi.testclient import TestClient
from moss_transcribe_diarize.app.phase2 import (
    Account,
    FRONTEND_ASSET_DIR,
    _asset_content_version,
    _workspace_html,
    create_phase2_app,
)
from tests.phase2.workspace_reachability_fixtures import _runtime, _heartbeat, _v2_frame


def test_frontend_asset_version_is_cached_and_changes_after_deployment_swap(
    tmp_path: Path, monkeypatch
):
    asset = tmp_path / 'app.js'
    asset.write_bytes(b'first build')
    os.utime(asset, ns=(1_000_000_000, 1_000_000_000))
    read_count = 0
    read_bytes = Path.read_bytes

    def counted_read_bytes(path: Path) -> bytes:
        nonlocal read_count
        read_count += 1
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)
    first = _asset_content_version(asset)
    assert _asset_content_version(asset) == first
    assert read_count == 1

    replacement = tmp_path / 'replacement.js'
    replacement.write_bytes(b'other build')
    os.utime(replacement, ns=(2_000_000_000, 2_000_000_000))
    replacement.replace(asset)
    assert _asset_content_version(asset) != first
    assert read_count == 2
    workspace = _workspace_html(Account('account', 'This browser', 0), [], live_enabled=True)
    assert '<p data-history="empty">No meetings yet.</p>' in workspace


def test_same_workspace_reads_converge_without_acquiring_capture(tmp_path):
    app = create_phase2_app(database_path=tmp_path/'moss.sqlite3',
                            live_runtime_factory=_runtime, live_helper_lease_seconds=30)
    with TestClient(app, base_url='https://moss.test') as owner:
        assert owner.post('/api/workspace/bootstrap').status_code == 200
        created = owner.post('/api/live/sessions', json={'echo_mode': 'speakers'})
        assert created.status_code == 201
        ident = created.json()['id']
        prefix = '/api/live/sessions/' + ident
        assert owner.post(prefix+'/heartbeat', json=_heartbeat()).status_code == 200
        for sequence in range(3):
            for lane in ('system', 'microphone'):
                assert owner.post(prefix+'/frames', json=_v2_frame(sequence, lane)).status_code == 200
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            before = owner.get(prefix+'/snapshot').json()
            if before['snapshot']['session']['effective_transcript']:
                break
            time.sleep(.02)
        assert before['snapshot']['session']['effective_transcript']
        # Two independent readers share only the workspace cookie. GETs cannot capture.
        readers = [TestClient(app, base_url='https://moss.test') for _ in range(2)]
        for reader in readers:
            reader.cookies.update(owner.cookies)
            html = reader.get('/').text
            assert 'id="workspace-file"' not in html
            assert 'id="app"' in html
            for section in ('live', 'history', 'voiceprints'):
                assert f'id="workspace-{section}"' in html
                assert f'href="#workspace-{section}"' in html
            assert 'data-auth-state="signed-in"' in html
            for asset in ('app.js', 'styles.css', 'worklets/lane-framer.js'):
                match = re.search(rf'(/static/{re.escape(asset)}\?v=[0-9a-f]{{64}})', html)
                assert match is not None
                expected_version = hashlib.sha256(
                    (FRONTEND_ASSET_DIR / asset).read_bytes()
                ).hexdigest()
                assert match.group(1) == f'/static/{asset}?v={expected_version}'
                assert reader.get(match.group(1)).status_code == 200
            assert reader.get('/api/meetings/'+ident).json()['id'] == ident
            assert reader.get(prefix+'/snapshot').json()['snapshot']['session']['effective_transcript'] == before['snapshot']['session']['effective_transcript']
        assert readers[0].put('/api/meetings/'+ident+'/title', json={'title':'Shared observed meeting'}).status_code == 200
        for reader in readers:
            assert reader.get('/api/meetings/'+ident).json()['title'] == 'Shared observed meeting'
            assert reader.get('/').status_code == 200
        after = owner.get(prefix+'/snapshot').json()
        assert after['snapshot']['session']['effective_transcript'] == before['snapshot']['session']['effective_transcript']
        assert after['snapshot']['session']['status'] == 'active'
        assert len(owner.get('/api/meetings').json()['meetings']) == 1
        for reader in readers:
            reader.close()
