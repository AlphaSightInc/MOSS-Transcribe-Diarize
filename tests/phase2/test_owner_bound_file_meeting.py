from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import (
    GoogleIdentity,
    Phase2Store,
    SESSION_COOKIE,
    create_phase2_app,
)


class NeverOidc:
    async def begin(self, request):  # pragma: no cover - these tests use stored MOSS sessions.
        raise AssertionError("OIDC must not run")

    async def complete(self, request):  # pragma: no cover - these tests use stored MOSS sessions.
        raise AssertionError("OIDC must not run")


class ControlledRunner:
    model_path = "controlled-file-runner"

    def __init__(self, *, text: str = "[0][S01]owner sentinel[1]", failure: Exception | None = None):
        self.text = text
        self.failure = failure
        self.started = threading.Event()
        self.release = threading.Event()
        self.inputs: list[tuple[str, bytes]] = []

    def transcribe(self, input_path: str | Path, **kwargs: object):
        path = Path(input_path)
        self.inputs.append((path.name, path.read_bytes()))
        self.started.set()
        assert self.release.wait(timeout=5), "test did not release controlled inference"
        if self.failure is not None:
            raise self.failure
        return SimpleNamespace(text=self.text)


async def provision(database: Path) -> dict[str, str]:
    store = await Phase2Store.open(database)
    try:
        sessions: dict[str, str] = {}
        for subject, email in (
            ("sub-a", "a@example.com"),
            ("sub-b", "b@example.com"),
        ):
            await store.allow_email(email)
            _, sessions[subject] = await store.admit(GoogleIdentity(subject, email, subject))
        _, sessions["sub-a-second"] = await store.admit(
            GoogleIdentity("sub-a", "a@example.com", "sub-a")
        )
        return sessions
    finally:
        await store.close()


def make_app(database: Path, runner: object | None, work_root: Path):
    return create_phase2_app(
        database_path=database,
        oidc=NeverOidc(),
        oauth_cookie_secret="test-cookie-secret",
        file_runner=runner,
        file_work_root=work_root,
    )


def session(client: TestClient, session_id: str | None) -> None:
    client.cookies.clear()
    if session_id is not None:
        client.cookies.set(SESSION_COOKIE, session_id, domain="moss.test", path="/")


def await_terminal(client: TestClient, meeting_id: str, status: str) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/meetings/{meeting_id}")
        if response.status_code == 200 and response.json()["status"] == status:
            return response.json()
        time.sleep(0.01)
    raise AssertionError(f"Meeting {meeting_id} did not reach {status}")


def test_upload_runs_after_browser_leaves_and_remains_owner_bound(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    runner = ControlledRunner()
    app = make_app(database, runner, tmp_path / "work")

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        workspace = client.get("/")
        assert 'data-file-upload="form"' in workspace.text
        assert client.post("/api/meetings", json={"mode": "file"}).status_code == 400
        assert client.post("/api/meetings/file", files={}).status_code == 400
        accepted = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", b"owner-audio", "audio/wav")},
        )
        assert accepted.status_code == 201
        meeting_id = accepted.json()["id"]
        assert accepted.json()["status"] == "active"
        assert runner.started.wait(timeout=2)

        # The accepting browser is gone. Work belongs to the server-side Meeting handle.
        session(client, None)
        runner.release.set()
        session(client, sessions["sub-a-second"])
        meeting = await_terminal(client, meeting_id, "completed")
        assert meeting["transcript_version"] == 1
        assert meeting["transcript"] == {
            "segments": [
                {"id": "seg_0001", "start": 0.0, "end": 1.0, "speaker": "S01", "text": "owner sentinel"}
            ]
        }
        assert client.get("/api/meetings").json()["meetings"] == [meeting]

        session(client, sessions["sub-b"])
        assert client.get(f"/api/meetings/{meeting_id}").status_code == 404
        assert "owner sentinel" not in client.get("/api/meetings").text
        session(client, None)
        assert client.get(f"/api/meetings/{meeting_id}").status_code == 401

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM meetings").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM meeting_transcripts").fetchone()[0] == 1
        assert connection.execute("SELECT version FROM meeting_transcripts").fetchone()[0] == 1
    finally:
        connection.close()
    assert runner.inputs == [("input.wav", b"owner-audio")]
    assert list((tmp_path / "work").glob("**/*")) == []


def test_file_meeting_failure_is_durable_and_recoverable(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    runner = ControlledRunner(failure=RuntimeError("provider unavailable"))
    app = make_app(database, runner, tmp_path / "work")

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        accepted = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.mp3", b"input", "audio/mpeg")},
        )
        meeting_id = accepted.json()["id"]
        assert runner.started.wait(timeout=2)
        runner.release.set()
        meeting = await_terminal(client, meeting_id, "failed")
        assert meeting["transcript"] is None
        assert meeting["transcript_version"] == 0

    restarted = make_app(database, None, tmp_path / "restart-work")
    with TestClient(restarted, base_url="https://moss.test") as client:
        session(client, sessions["sub-a-second"])
        assert client.get(f"/api/meetings/{meeting_id}").json() == meeting


def test_revocation_fences_late_file_result_commit(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    runner = ControlledRunner()
    app = make_app(database, runner, tmp_path / "work")

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        accepted = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", b"input", "audio/wav")},
        )
        meeting_id = accepted.json()["id"]
        assert runner.started.wait(timeout=2)

        async def revoke() -> None:
            store = await Phase2Store.open(database)
            try:
                assert await store.revoke_email("a@example.com") is True
            finally:
                await store.close()

        asyncio.run(revoke())
        runner.release.set()
        assert client.get(f"/api/meetings/{meeting_id}").status_code == 401

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            connection = sqlite3.connect(database)
            try:
                row = connection.execute(
                    "SELECT status FROM meetings WHERE meeting_id = ?", (meeting_id,)
                ).fetchone()
                transcript_count = connection.execute(
                    "SELECT COUNT(*) FROM meeting_transcripts WHERE meeting_id = ?", (meeting_id,)
                ).fetchone()[0]
            finally:
                connection.close()
            if row == ("interrupted",) and transcript_count == 0:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("revoked late result was not fenced")


def test_each_owner_bound_commit_versions_and_restart_retains_last_document(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"

    async def commit_twice() -> str:
        store = await Phase2Store.open(database)
        try:
            await store.allow_email("a@example.com")
            account, _ = await store.admit(GoogleIdentity("sub-a", "a@example.com", "A"))
            meeting = await store.workspace(account).create_meeting("file")
            assert await meeting.commit_transcript({"segments": [{"text": "first"}]}) == 1
            assert await meeting.commit_transcript({"segments": [{"text": "second"}]}) == 2
            return meeting.meeting_id
        finally:
            await store.close()

    meeting_id = asyncio.run(commit_twice())
    app = make_app(database, None, tmp_path / "work")
    with TestClient(app, base_url="https://moss.test"):
        pass

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT status FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == ("interrupted",)
        document, version = connection.execute(
            "SELECT document_json, version FROM meeting_transcripts WHERE meeting_id = ?",
            (meeting_id,),
        ).fetchone()
        assert '"second"' in document
        assert version == 2
    finally:
        connection.close()
