from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from moss_transcribe_diarize.app.phase2 import (
    SESSION_COOKIE, AccountRevoked, Phase2Store, SchemaVersionError, create_phase2_app,
)
from moss_transcribe_diarize.app.phase2_admin import execute as execute_admin, execute_status


def test_browser_bootstrap_owns_history_without_google_and_survives_restart(tmp_path: Path):
    async def exercise():
        path = tmp_path / "browser.sqlite3"
        store = await Phase2Store.open(path)
        try:
            owner, credential = await store.bootstrap_browser(None)
            peer, peer_credential = await store.bootstrap_browser(None)
            assert owner.account_id != peer.account_id
            assert credential != peer_credential
            assert owner.account_id != credential
            assert "account_allowlist" not in await store.table_names()
            assert await store.user_version() == 2
            meeting = await store.workspace(owner).create_meeting("file")
            await meeting.commit_transcript({"segments": [{"text": "saved content"}]})
            await meeting.finish("completed")
            assert await store.workspace(peer).open_meeting(meeting.meeting_id) is None
            same, same_credential = await store.bootstrap_browser(credential)
            assert same == owner
            assert same_credential == credential
        finally:
            await store.close()
        reopened = await Phase2Store.open(path)
        try:
            returned, returned_credential = await reopened.bootstrap_browser(credential)
            assert returned == owner
            assert returned_credential == credential
            history = await reopened.workspace(returned).list_meetings()
            assert [m.meeting_id for m in history] == [meeting.meeting_id]
            assert history[0].transcript == {"segments": [{"text": "saved content"}]}
        finally:
            await reopened.close()

    asyncio.run(exercise())


def test_browser_http_bootstrap_is_explicit_private_and_same_origin(tmp_path: Path):
    app = create_phase2_app(database_path=tmp_path / "browser.sqlite3")
    with TestClient(app, base_url="https://moss.test") as client:
        landing = client.get("/")
        assert landing.status_code == 200
        assert "navigator.locks.request" in landing.text
        assert "Google" not in landing.text
        assert SESSION_COOKIE not in client.cookies
        assert client.get("/api/meetings").status_code == 401
        denied = client.post("/api/workspace/bootstrap", headers={"Origin": "https://other.test"})
        assert denied.status_code == 403
        assert SESSION_COOKIE not in client.cookies
        created = client.post("/api/workspace/bootstrap", headers={"Origin": "https://moss.test"})
        assert created.status_code == 200
        owner_id = created.json()["workspace_id"]
        credential = client.cookies[SESSION_COOKIE]
        assert owner_id != credential
        assert credential not in created.text
        cookie = created.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
        assert created.headers["cache-control"] == "no-store"
        assert client.get("/api/auth/session").json()["workspace_id"] == owner_id
        assert client.post("/api/workspace/bootstrap").json()["workspace_id"] == owner_id
        assert client.cookies[SESSION_COOKIE] == credential
        workspace = client.get("/")
        assert "This browser" in workspace.text
        assert "Sign out" not in workspace.text
        assert "Google" not in workspace.text
        assert client.get("/auth/google").status_code == 404
        assert client.post("/auth/logout").status_code == 404
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, "invalid")
        assert client.post("/api/workspace/bootstrap").status_code == 401
        unavailable = client.get("/").text
        assert "Workspace unavailable" in unavailable and "data-new-workspace" in unavailable
        # The explicit action replaces the unknown credential with a new, empty workspace …
        fresh = client.post("/api/workspace/new")
        assert fresh.status_code == 200 and fresh.json()["workspace_id"] != owner_id
        replaced = fresh.cookies[SESSION_COOKIE]
        assert replaced not in ("invalid", credential)
        client.cookies.clear()  # a browser replaces the cookie; the test client would keep both
        client.cookies.set(SESSION_COOKIE, replaced)
        assert "This browser" in client.get("/").text
        # … and never abandons a workspace the browser still holds.
        assert client.post("/api/workspace/new").status_code == 409


def test_page_shell_uses_product_name_and_keeps_only_actionable_copy(tmp_path: Path):
    # J7 + Q6: the tab title and loading page say "aiSight - LiveTranscribe"; the browser-profile
    # storage notices are gone from both server-rendered pages.
    app = create_phase2_app(database_path=tmp_path / "browser.sqlite3")
    with TestClient(app, base_url="https://moss.test") as client:
        loading = client.get("/").text
        assert client.post("/api/workspace/bootstrap").status_code == 200
        workspace = client.get("/").text
    for page in (loading, workspace):
        assert "<title>aiSight - LiveTranscribe</title>" in page
        assert "MOSS</" not in page
        assert "Clearing site data" not in page
    assert "<h1>aiSight - LiveTranscribe</h1>" in loading


def test_page_shells_name_the_existing_logo_as_their_icon(tmp_path: Path):
    # r4 UI stress: without a declared icon the browser requested /favicon.ico and got a 404.
    app = create_phase2_app(database_path=tmp_path / "browser.sqlite3")
    icon = '<link rel="icon" href="/static/logo-mark.svg" type="image/svg+xml">'
    with TestClient(app, base_url="https://moss.test") as client:
        loading = client.get("/").text
        assert client.post("/api/workspace/bootstrap").status_code == 200
        workspace = client.get("/").text
        served = client.get("/static/logo-mark.svg")
    assert icon in loading and icon in workspace
    assert served.status_code == 200 and served.headers["content-type"].startswith("image/svg+xml")


def test_open_workspace_binds_independent_clients_to_shared_history(tmp_path: Path):
    database = tmp_path / "open.sqlite3"
    first_app = create_phase2_app(database_path=database, open_workspace=True)
    with TestClient(first_app, base_url="https://moss.test") as first:
        initial = first.get("/api/meetings")
        assert initial.status_code == 200
        assert initial.json() == {"meetings": []}
        first_session = first.cookies[SESSION_COOKIE]
        first_workspace = first.get("/api/auth/session").json()["workspace_id"]

        async def seed_meeting():
            account = await first_app.state.phase2_store.account_for_session(first_session)
            assert account is not None
            meeting = await first_app.state.phase2_store.workspace(account).create_meeting("file")
            await meeting.commit_transcript({"segments": [{"text": "shared content"}]})
            await meeting.finish("completed")
            return meeting.meeting_id

        meeting_id = first.portal.call(seed_meeting)

    second_app = create_phase2_app(database_path=database, open_workspace=True)
    with TestClient(second_app, base_url="https://moss.test") as second:
        shared = second.get("/api/meetings")
        assert shared.status_code == 200
        assert [meeting["id"] for meeting in shared.json()["meetings"]] == [meeting_id]
        assert second.get("/api/auth/session").json()["workspace_id"] == first_workspace
        assert second.cookies[SESSION_COOKIE] == first_session

        second.cookies.clear()
        second.cookies.set(SESSION_COOKIE, "unknown", domain="moss.test", path="/")
        rebound = second.get("/api/meetings")
        assert rebound.status_code == 200
        assert [meeting["id"] for meeting in rebound.json()["meetings"]] == [meeting_id]
        assert second.cookies[SESSION_COOKIE] == first_session


def test_old_schema_is_refused_without_changing_bytes_or_creating_sidecars(tmp_path: Path):
    database = tmp_path / "previous.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE preserved(value TEXT)")
        connection.execute("INSERT INTO preserved VALUES ('existing history')")
        connection.execute("PRAGMA user_version=1")
    before = database.read_bytes()
    with pytest.raises(SchemaVersionError, match="user_version=1; expected 2"):
        asyncio.run(Phase2Store.open(database))
    assert database.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == [database.name]


def test_operator_revocation_uses_workspace_id_without_content_or_credentials(tmp_path: Path):
    # The host-local socket is independent of the browser cookie and contains no content.
    import tempfile

    with tempfile.TemporaryDirectory(prefix="moss-control-") as socket_root:
        socket = Path(socket_root) / "control.sock"
        if socket.is_relative_to(Path.cwd()):
            socket = socket.relative_to(Path.cwd())
        app = create_phase2_app(database_path=tmp_path / "browser.sqlite3", control_socket_path=socket)
        with TestClient(app, base_url="https://moss.test") as client:
            owner = client.post("/api/workspace/bootstrap").json()["workspace_id"]
            credential = client.cookies[SESSION_COOKIE]
            status = asyncio.run(execute_status(socket))
            assert status["accounts"][0]["account_id"] == owner
            assert credential not in str(status)
            assert "email" not in str(status)
            assert asyncio.run(execute_admin(socket, "list")) == [{"account_id": owner, "enabled": True}]
            assert asyncio.run(execute_admin(socket, "revoke", owner)) == {"account_id": owner, "revoked": True}
            assert client.get("/api/meetings").status_code == 401
            assert client.post("/api/workspace/bootstrap").status_code == 401
            assert asyncio.run(execute_admin(socket, "revoke", owner)) == {"account_id": owner, "revoked": False}


def test_revoked_owner_cannot_write_or_be_restored_by_fresh_browser(tmp_path: Path):
    async def exercise():
        store = await Phase2Store.open(tmp_path / "browser.sqlite3")
        try:
            owner, credential = await store.bootstrap_browser(None)
            workspace = store.workspace(owner)
            handle = await workspace.create_meeting("file")
            with pytest.raises(RuntimeError, match="durably terminal"):
                await store.revoke_account(owner.account_id)
            assert await store.account_for_session(credential) == owner
            await handle.finish("interrupted")
            assert await store.revoke_account(owner.account_id)
            with pytest.raises(AccountRevoked):
                await workspace.create_meeting("file")
            with pytest.raises(AccountRevoked):
                await store.bootstrap_browser(credential)
            fresh, _ = await store.bootstrap_browser(None)
            assert fresh.account_id != owner.account_id
            assert await store.workspace(fresh).open_meeting(handle.meeting_id) is None
        finally:
            await store.close()

    asyncio.run(exercise())
