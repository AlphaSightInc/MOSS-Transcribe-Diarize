from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import (
    GoogleIdentity,
    Phase2Store,
    SESSION_COOKIE,
    create_phase2_app,
)


class NeverOidc:
    async def begin(self, request):  # pragma: no cover - stored sessions bypass OIDC.
        raise AssertionError("OIDC must not run")

    async def complete(self, request):  # pragma: no cover - stored sessions bypass OIDC.
        raise AssertionError("OIDC must not run")


def set_session(client: TestClient, session_id: str | None) -> None:
    client.cookies.clear()
    if session_id is not None:
        client.cookies.set(SESSION_COOKIE, session_id, domain="moss.test", path="/")


def make_app(database: Path):
    return create_phase2_app(
        database_path=database,
        oidc=NeverOidc(),
        oauth_cookie_secret="history-test-cookie-secret",
    )


def test_workspace_order_is_active_first_then_terminal_newest_with_id_tie_break(
    tmp_path: Path,
) -> None:
    database = tmp_path / "moss.sqlite3"

    async def exercise() -> None:
        store = await Phase2Store.open(database)
        try:
            await store.allow_email("owner@example.com")
            admitted = await store.admit(
                GoogleIdentity("owner-sub", "owner@example.com", "Owner")
            )
            assert admitted is not None
            account, _ = admitted
            rows = (
                ("terminal-new", "file", "URL review", "completed", 9_000),
                ("active-old", "file", "Upload running", "active", 1_000),
                ("active-new", "live", None, "active", 8_000),
                ("terminal-tie-a", "file", "A", "failed", 7_000),
                ("terminal-tie-z", "live", "Z", "interrupted", 7_000),
            )
            async with store._mutation():
                await store._connection.executemany(
                    """
                    INSERT INTO meetings(
                        account_id, meeting_id, mode, title, title_source,
                        status, created_at_ms, updated_at_ms
                    ) VALUES (?, ?, ?, ?, 'automatic', ?, ?, ?)
                    """,
                    [
                        (account.account_id, meeting_id, mode, title, status, created, created)
                        for meeting_id, mode, title, status, created in rows
                    ],
                )

            meetings = await store.workspace(account).list_meetings()
            assert [meeting.meeting_id for meeting in meetings] == [
                "active-new",
                "active-old",
                "terminal-new",
                "terminal-tie-z",
                "terminal-tie-a",
            ]
            assert {meeting.mode for meeting in meetings} == {"live", "file"}
            assert {meeting.title_source for meeting in meetings} == {"automatic"}
        finally:
            await store.close()

    asyncio.run(exercise())


def test_same_account_rename_converges_restarts_and_foreign_id_is_zero_mutation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "moss.sqlite3"

    async def provision() -> tuple[str, str, str, str]:
        store = await Phase2Store.open(database)
        try:
            await store.allow_email("owner@example.com")
            await store.allow_email("foreign@example.com")
            owner_first = await store.admit(
                GoogleIdentity("owner-sub", "owner@example.com", "Owner")
            )
            owner_second = await store.admit(
                GoogleIdentity("owner-sub", "owner@example.com", "Owner")
            )
            foreign = await store.admit(
                GoogleIdentity("foreign-sub", "foreign@example.com", "Foreign")
            )
            assert owner_first is not None and owner_second is not None and foreign is not None
            handle = await store.workspace(owner_first[0]).create_meeting("file")
            await handle.commit_transcript(
                {
                    "segments": [
                        {
                            "id": "seg_0001",
                            "start": 0.0,
                            "end": 1.0,
                            "speaker": "S01",
                            "text": "durable history sentinel",
                        }
                    ]
                }
            )
            await handle.finish("completed")
            return handle.meeting_id, owner_first[1], owner_second[1], foreign[1]
        finally:
            await store.close()

    meeting_id, owner_first, owner_second, foreign = asyncio.run(provision())

    app = make_app(database)
    with TestClient(app, base_url="https://moss.test") as client:
        set_session(client, owner_first)
        renamed = client.put(
            f"/api/meetings/{meeting_id}/title",
            json={"title": "  Customer interview  "},
        )
        assert renamed.status_code == 200
        assert renamed.json() == {
            "id": meeting_id,
            "title": "Customer interview",
            "title_source": "manual",
        }
        assert client.put(f"/api/meetings/{meeting_id}/title", json={"title": "  "}).status_code == 400

        set_session(client, owner_second)
        same_account = client.get("/api/meetings").json()["meetings"]
        assert len(same_account) == 1
        assert same_account[0]["title"] == "Customer interview"
        assert same_account[0]["title_source"] == "manual"
        assert same_account[0]["transcript"]["segments"][0]["text"] == "durable history sentinel"

        connection = sqlite3.connect(database)
        try:
            before = connection.execute(
                "SELECT title, title_source, updated_at_ms FROM meetings WHERE meeting_id = ?",
                (meeting_id,),
            ).fetchone()
        finally:
            connection.close()

        set_session(client, foreign)
        assert client.get(f"/api/meetings/{meeting_id}").status_code == 404
        assert client.put(
            f"/api/meetings/{meeting_id}/title", json={"title": "Foreign overwrite"}
        ).status_code == 404

        connection = sqlite3.connect(database)
        try:
            after = connection.execute(
                "SELECT title, title_source, updated_at_ms FROM meetings WHERE meeting_id = ?",
                (meeting_id,),
            ).fetchone()
        finally:
            connection.close()
        assert after == before

        set_session(client, None)
        assert client.get("/api/meetings").status_code == 401
        assert client.put(
            f"/api/meetings/{meeting_id}/title", json={"title": "Anonymous"}
        ).status_code == 401

    restarted = make_app(database)
    with TestClient(restarted, base_url="https://moss.test") as client:
        set_session(client, owner_second)
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["title"] == "Customer interview"
        assert meeting["title_source"] == "manual"
        workspace = client.get("/")
        assert workspace.status_code == 200
        assert 'id="meeting-history-app"' in workspace.text
        assert "Customer interview" in workspace.text
