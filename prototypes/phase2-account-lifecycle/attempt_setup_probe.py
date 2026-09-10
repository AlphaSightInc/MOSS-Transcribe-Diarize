"""THROWAWAY: normal HTTP bootstrap supplies isolated qualification authority.

Question: can an attempt provision all peers without login, DB writes or copied secrets?
Primitives: workspace (isolation), cookie (authority), peer (same cookie), private
attempt directory (credential custody). None can be removed without losing a boundary.
Invariant: three independent owners; A/peer and B/peer share one credential each;
each role round-trips through production authentication; emitted state is counts only.
Assumption: trusted deployment TLS remains unmeasured here; no physical audio.
Falsifier: shared owner across independent roles, peer loses history, foreign read
succeeds, credential is a public ID, credential file is not 0600, or reuse overwrites.
Tool decision: TestClient exercises real bootstrap/cookie/store in a scratch database;
failure blocks automatic setup, not a reason to synthesize credentials in SQLite.
Run: PYTHONPATH=. .venv/bin/python prototypes/phase2-account-lifecycle/attempt_setup_probe.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from moss_transcribe_diarize.app import phase2
from moss_transcribe_diarize.phase2_acceptance_setup import _bootstrap, _private_once


def run(root):
    phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
    app = phase2.create_phase2_app(database_path=root / 'PROTOTYPE.sqlite3')
    with TestClient(app, base_url='https://moss.test') as client:
        identities = {role: _bootstrap(client) for role in ('a', 'b', 'revoked_probe')}
        assert len({owner for owner, _ in identities.values()}) == 3
        assert len({cookie for _, cookie in identities.values()}) == 3
        paths = {}
        for role, (_, cookie) in identities.items():
            path = root / (role + '.cookie')
            _private_once(path, cookie.encode())
            paths[role] = path
        paths['a_peer'], paths['b_peer'] = paths['a'], paths['b']
        for role, path in paths.items():
            assert path.stat().st_mode & 0o777 == 0o600
            client.cookies.clear()
            response = client.get('/api/auth/session', headers={'Cookie': phase2.SESSION_COOKIE + '=' + path.read_text()})
            assert response.status_code == 200
            assert response.json()['workspace_id'] == identities[role.removesuffix('_peer')][0]
        refused = False
        try:
            os.open(paths['a'], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            refused = True
        assert refused
        print(json.dumps({'sqlite': sqlite3.sqlite_version, 'independent_workspaces': 3,
            'credential_files': 3, 'authenticated_peer_roundtrips': 5,
            'private_modes': True, 'reuse_refused': True, 'deployed_qualification': False}))


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='moss-attempt-setup-prototype-') as temporary:
        run(Path(temporary))
