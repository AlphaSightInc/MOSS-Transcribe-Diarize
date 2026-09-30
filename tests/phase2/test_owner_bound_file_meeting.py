from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import sqlite3
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace

from _browser_workspace_fixtures import seed_workspace

from fastapi.testclient import TestClient
import pytest

from moss_transcribe_diarize.app import phase2_file
from moss_transcribe_diarize.app.phase2 import (
    MeetingHandle,
    Phase2Store,
    SESSION_COOKIE,
    create_phase2_app,
)
from moss_transcribe_diarize.app.phase2_admin import (
    execute as execute_admin,
    execute_interrupt,
)
from moss_transcribe_diarize.app.phase2_control import Phase2ControlError
from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner



class ControlledRunner:
    model_path = "controlled-file-runner"

    def __init__(self, *, text: str = "[0][S01]owner sentinel[1]", failure: Exception | None = None):
        self.text = text
        self.failure = failure
        self.started = threading.Event()
        self.release = threading.Event()
        self.inputs: list[tuple[str, bytes]] = []
        self.options: list[dict[str, object]] = []

    def transcribe(self, input_path: str | Path, **kwargs: object):
        path = Path(input_path)
        self.inputs.append((path.name, path.read_bytes()))
        self.options.append(dict(kwargs))
        self.started.set()
        assert self.release.wait(timeout=5), "test did not release controlled inference"
        if self.failure is not None:
            raise self.failure
        return SimpleNamespace(text=self.text)


class SelectiveRunner:
    model_path = "selective-file-runner"

    def __init__(self) -> None:
        self.started = {key: threading.Event() for key in (b"target", b"peer")}
        self.release = {key: threading.Event() for key in (b"target", b"peer")}

    def transcribe(self, input_path: str | Path, **kwargs: object):
        del kwargs
        payload = Path(input_path).read_bytes()
        self.started[payload].set()
        assert self.release[payload].wait(timeout=5), "test did not release selected inference"
        label = payload.decode("ascii")
        return SimpleNamespace(text=f"[0][S01]{label} result[1]")


def wav_bytes(*, frames: int = 1600) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\x01\x00" * frames)
    return output.getvalue()


async def provision(database: Path) -> dict[str, str]:
    store = await Phase2Store.open(database)
    try:
        sessions: dict[str, str] = {}
        for subject, email in (
            ("sub-a", "sub-a"),
            ("sub-b", "sub-b"),
        ):
            _, sessions[subject] = await seed_workspace(store, subject)
        _, sessions["sub-a-second"] = await seed_workspace(store, "sub-a")
        return sessions
    finally:
        await store.close()


def make_app(
    database: Path,
    runner: object | None,
    work_root: Path,
    *,
    control_socket: Path | None = None,
):
    return create_phase2_app(
        database_path=database,
        file_runner=runner,
        file_work_root=work_root,
        control_socket_path=control_socket,
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
    app = make_app(database, runner, tmp_path / "file-work")

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        workspace = client.get("/")
        assert 'data-file-upload="form"' in workspace.text
        assert client.post("/api/meetings", json={"mode": "file"}).status_code == 405
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
                {"id": "seg_0001", "start": 0.0, "end": 1.0, "speaker": "Speaker 1",
                 "text": "owner sentinel", "speaker_entity_id": "S01"}
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
    assert list((tmp_path / "file-work").glob("**/*")) == []


def test_file_work_is_meeting_owned_before_inference_and_removed_after_terminal(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    runner = ControlledRunner()
    work_root = tmp_path / "file-work"
    app = make_app(database, runner, work_root)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        accepted = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", b"durable-source", "audio/wav")},
        )
        assert accepted.status_code == 201
        meeting_id = accepted.json()["id"]
        assert runner.started.wait(timeout=2)

        tasks = app.state.phase2_file_tasks
        owner_dir = tasks.retained_root / "sub-a" / meeting_id
        assert list(work_root.iterdir()) == []
        assert json.loads((owner_dir / "owner.json").read_text()) == {
            "account_id": "sub-a",
            "checkpoint": "checkpoint",
            "contract_version": 1,
            "ingress": "file",
            "meeting_id": meeting_id,
            "source": "input.wav",
        }
        assert (owner_dir / "input.wav").read_bytes() == b"durable-source"
        assert (owner_dir / "checkpoint").is_dir()
        assert runner.options == [{"checkpoint_dir": owner_dir / "checkpoint"}]

        runner.release.set()
        assert await_terminal(client, meeting_id, "completed")["status"] == "completed"
        assert not owner_dir.exists()


def test_201_minute_file_tail_is_saved_and_survives_app_reopen(tmp_path: Path):
    class TailDecoder:
        model_path = "duration-tail-stub"

        def transcribe(self, audio_path: str | Path, **kwargs: object):
            del kwargs
            index = int(Path(audio_path).stem.rsplit("-", 1)[1])
            start = 59 if index == 100 else 60
            text = f"window-{index:04d}" + ("-tail" if index == 100 else "")
            return TranscriptionResult(
                text=f"[{start}][S01]{text}[{start + 1}]",
                prompt_len=1,
                generated_tokens=1,
                elapsed_sec=0.0,
                model=self.model_path,
                audio=str(audio_path),
                decoding="greedy",
                temperature=None,
            )

    def extract(_source, destination, *, start_seconds, duration_seconds):
        del start_seconds, duration_seconds
        Path(destination).write_bytes(b"bounded-window")

    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    work_root = tmp_path / "file-work"
    runner = WindowedRunner(
        TailDecoder(),
        duration_probe=lambda _path: 12_060.0,
        window_extractor=extract,
    )
    app = make_app(database, runner, work_root)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        accepted = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", b"accelerated-source", "audio/wav")},
        )
        assert accepted.status_code == 201
        meeting_id = accepted.json()["id"]
        completed = await_terminal(client, meeting_id, "completed")
        assert len(completed["transcript"]["segments"]) == 101
        tail = completed["transcript"]["segments"][-1]
        assert tail["id"] == "seg_0101"
        assert (tail["start"], tail["end"], tail["text"]) == (
            12_059.0,
            12_060.0,
            "window-0100-tail",
        )

    reopened = make_app(database, None, work_root)
    with TestClient(reopened, base_url="https://moss.test") as client:
        session(client, sessions["sub-a-second"])
        saved = client.get(f"/api/meetings/{meeting_id}")
        assert saved.status_code == 200
        assert saved.json()["status"] == "completed"
        assert saved.json()["transcript"]["segments"][-1]["text"] == "window-0100-tail"
        assert saved.json()["transcript"]["segments"][-1]["end"] == 12_060.0


def test_lost_browser_cookie_does_not_cancel_accepted_file_work(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    runner = ControlledRunner()
    app = make_app(database, runner, tmp_path / "file-work")

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        meeting_id = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", b"accepted", "audio/wav")},
        ).json()["id"]
        assert runner.started.wait(timeout=2)
        client.cookies.clear()
        assert client.get("/api/auth/session").status_code == 401
        runner.release.set()
        session(client, sessions["sub-a-second"])
        meeting = await_terminal(client, meeting_id, "completed")
        assert meeting["transcript_version"] == 1


def test_host_revoke_waits_for_file_quiescence_and_fences_late_result(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i18-file-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    runner = ControlledRunner()
    work_root = tmp_path / "file-work"
    app = make_app(
        database,
        runner,
        work_root,
        control_socket=socket,
    )

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        meeting_id = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", b"held-result", "audio/wav")},
        ).json()["id"]
        assert runner.started.wait(timeout=2)
        outcome: dict[str, object] = {}

        def revoke() -> None:
            outcome["result"] = asyncio.run(
                execute_admin(socket, "revoke", "sub-a")
            )

        worker = threading.Thread(target=revoke)
        worker.start()
        deadline = time.monotonic() + 2
        owner_key = ("sub-a", 0)
        while owner_key not in app.state.phase2_file_tasks._fenced_owner_keys:
            if time.monotonic() >= deadline:
                raise AssertionError("Account File tasks were not fenced")
            time.sleep(0.01)
        assert worker.is_alive()
        assert client.post(
            "/api/meetings/file",
            files={"file": ("later.wav", b"later", "audio/wav")},
        ).status_code == 409
        # Durable authority changes last, after the held provider result is quiesced.
        assert client.get("/api/auth/session").status_code == 200
        runner.release.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert outcome["result"] == {"account_id": "sub-a", "revoked": True}
        assert client.get("/api/auth/session").status_code == 401

    connection = sqlite3.connect(database)
    try:
        status = connection.execute(
            "SELECT status FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ).fetchone()[0]
        transcript_count = connection.execute(
            "SELECT COUNT(*) FROM meeting_transcripts WHERE meeting_id = ?", (meeting_id,)
        ).fetchone()[0]
        audio_state = connection.execute(
            "SELECT state FROM meeting_audio WHERE meeting_id = ?", (meeting_id,)
        ).fetchone()[0]
    finally:
        connection.close()
    assert (status, transcript_count, audio_state) == ("interrupted", 0, "unavailable")


def test_operator_interrupt_claims_one_file_task_and_leaves_peer_running(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i20-file-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    runner = SelectiveRunner()
    work_root = tmp_path / "file-work"
    app = make_app(database, runner, work_root, control_socket=socket)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        target = client.post(
            "/api/meetings/file",
            files={"file": ("target.media", b"target", "application/octet-stream")},
        ).json()["id"]
        peer = client.post(
            "/api/meetings/file",
            files={"file": ("peer.media", b"peer", "application/octet-stream")},
        ).json()["id"]
        assert runner.started[b"target"].wait(timeout=2)
        assert runner.started[b"peer"].wait(timeout=2)

        outcome: dict[str, object] = {}

        def interrupt() -> None:
            outcome["result"] = asyncio.run(execute_interrupt(socket, target))

        worker = threading.Thread(target=interrupt)
        worker.start()
        deadline = time.monotonic() + 2
        while target not in app.state.phase2_file_tasks._fenced_meeting_ids:
            if time.monotonic() >= deadline:
                raise AssertionError("target File task was not synchronously claimed")
            time.sleep(0.01)
        assert peer not in app.state.phase2_file_tasks._fenced_meeting_ids
        assert worker.is_alive()
        assert client.get(f"/api/meetings/{peer}").json()["status"] == "active"

        runner.release[b"target"].set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert outcome == {
            "result": {"meeting_id": target, "interrupted": True}
        }
        mutations = [
            event
            for event in app.state.phase2_operator_status._recent_events
            if event["kind"] == "operator_mutation"
        ]
        assert mutations[-1]["context"] == {
            "command": "meetings.interrupt",
            "outcome": "succeeded",
        }
        assert target not in json.dumps(mutations, sort_keys=True)
        assert asyncio.run(execute_interrupt(socket, target)) == {
            "meeting_id": target,
            "interrupted": False,
        }
        target_state = client.get(f"/api/meetings/{target}").json()
        assert target_state["status"] == "interrupted"
        assert target_state["transcript"] is None
        assert target_state["audio"]["state"] == "unavailable"
        assert client.get(f"/api/meetings/{peer}").json()["status"] == "active"

        runner.release[b"peer"].set()
        peer_state = await_terminal(client, peer, "completed")
        assert peer_state["transcript"]["segments"][0]["text"] == "peer result"

    assert list(work_root.glob("**/*")) == []


def test_control_shutdown_joins_service_owned_file_interrupt(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i20-file-stop-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    runner = ControlledRunner()
    work_root = tmp_path / "file-work"
    app = make_app(database, runner, work_root, control_socket=socket)
    client = TestClient(app, base_url="https://moss.test")
    client.__enter__()
    session(client, sessions["sub-a"])
    meeting_id = client.post(
        "/api/meetings/file",
        files={"file": ("meeting.wav", b"held-interrupt", "audio/wav")},
    ).json()["id"]
    assert runner.started.wait(timeout=2)
    source = app.state.phase2_file_tasks.retained_root / "sub-a" / meeting_id / "input.wav"
    outcome: dict[str, object] = {}

    def interrupt() -> None:
        try:
            outcome["result"] = asyncio.run(execute_interrupt(socket, meeting_id))
        except BaseException as exc:
            outcome["error"] = exc

    command = threading.Thread(target=interrupt)
    command.start()
    deadline = time.monotonic() + 2
    while meeting_id not in app.state.phase2_file_tasks._fenced_meeting_ids:
        if time.monotonic() >= deadline:
            raise AssertionError("File interrupt was not claimed before shutdown")
        time.sleep(0.01)

    shutdown_errors: list[BaseException] = []

    def shutdown() -> None:
        try:
            client.__exit__(None, None, None)
        except BaseException as exc:  # pragma: no cover - asserted empty below.
            shutdown_errors.append(exc)

    shutdown_thread = threading.Thread(target=shutdown)
    shutdown_thread.start()
    time.sleep(0.05)
    assert shutdown_thread.is_alive()
    assert source.is_file()
    runner.release.set()
    command.join(timeout=5)
    shutdown_thread.join(timeout=5)
    assert not command.is_alive() and not shutdown_thread.is_alive()
    assert shutdown_errors == []
    assert isinstance(outcome.get("error"), Phase2ControlError)
    assert not source.exists()

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT status FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == ("interrupted",)
        assert connection.execute(
            "SELECT COUNT(*) FROM meeting_transcripts WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT state FROM meeting_audio WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == ("unavailable",)
        assert connection.execute(
            "SELECT enabled, authority_generation FROM accounts WHERE account_id = 'sub-a'"
        ).fetchone() == (1, 0)
    finally:
        connection.close()


def test_operator_interrupt_downgrades_file_audio_at_finish_boundary(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i20-file-audio-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    runner = ControlledRunner()
    work_root = tmp_path / "file-work"
    app = make_app(database, runner, work_root, control_socket=socket)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        finish_started = threading.Event()
        release_finish = client.portal.call(asyncio.Event)
        original_finish = app.state.phase2_store._finish_meeting
        target_id: str | None = None

        async def held_complete(
            account_id: str,
            authority_generation: int,
            meeting_id: str,
            status: str,
        ) -> None:
            if meeting_id == target_id and status == "completed":
                finish_started.set()
                await release_finish.wait()
            await original_finish(
                account_id,
                authority_generation,
                meeting_id,
                status,
            )

        app.state.phase2_store._finish_meeting = held_complete
        target_id = client.post(
            "/api/meetings/file",
            files={"file": ("target.wav", wav_bytes(), "audio/wav")},
        ).json()["id"]
        assert runner.started.wait(timeout=2)
        runner.release.set()
        assert finish_started.wait(timeout=5)
        before = client.get(f"/api/meetings/{target_id}").json()
        assert before["status"] == "active"
        assert before["audio"]["state"] == "available"
        artifact = database.parent / "meetings" / before["audio"]["relative_path"]
        original_bytes = artifact.read_bytes()

        assert asyncio.run(execute_interrupt(socket, target_id)) == {
            "meeting_id": target_id,
            "interrupted": True,
        }
        after = client.get(f"/api/meetings/{target_id}").json()
        assert after["status"] == "interrupted"
        assert after["transcript"] == before["transcript"]
        assert after["audio"] == {**before["audio"], "state": "partial"}
        assert artifact.read_bytes() == original_bytes
        assert list(work_root.glob("**/*")) == []


def test_control_shutdown_joins_service_owned_file_revoke_and_runner(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i18-file-stop-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    runner = ControlledRunner()
    work_root = tmp_path / "file-work"
    app = make_app(database, runner, work_root, control_socket=socket)
    client = TestClient(app, base_url="https://moss.test")
    client.__enter__()
    session(client, sessions["sub-a"])
    meeting_id = client.post(
        "/api/meetings/file",
        files={"file": ("meeting.wav", b"held-shutdown", "audio/wav")},
    ).json()["id"]
    assert runner.started.wait(timeout=2)
    source = app.state.phase2_file_tasks.retained_root / "sub-a" / meeting_id / "input.wav"
    outcome: dict[str, object] = {}

    def revoke() -> None:
        try:
            outcome["result"] = asyncio.run(
                execute_admin(socket, "revoke", "sub-a")
            )
        except BaseException as exc:
            outcome["error"] = exc

    revoke_thread = threading.Thread(target=revoke)
    revoke_thread.start()
    deadline = time.monotonic() + 2
    owner_key = ("sub-a", 0)
    while owner_key not in app.state.phase2_file_tasks._fenced_owner_keys:
        if time.monotonic() >= deadline:
            raise AssertionError("Account File tasks were not fenced")
        time.sleep(0.01)

    shutdown_errors: list[BaseException] = []

    def shutdown() -> None:
        try:
            client.__exit__(None, None, None)
        except BaseException as exc:  # pragma: no cover - asserted empty below.
            shutdown_errors.append(exc)

    shutdown_thread = threading.Thread(target=shutdown)
    shutdown_thread.start()
    time.sleep(0.05)
    assert shutdown_thread.is_alive()
    assert source.is_file()
    assert meeting_id in app.state.phase2_file_tasks._tasks

    runner.release.set()
    revoke_thread.join(timeout=5)
    shutdown_thread.join(timeout=5)
    assert not revoke_thread.is_alive()
    assert not shutdown_thread.is_alive()
    assert shutdown_errors == []
    assert isinstance(outcome.get("error"), Phase2ControlError)
    assert not source.exists()
    assert app.state.phase2_file_tasks._tasks == {}

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT status FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == ("interrupted",)
        assert connection.execute(
            "SELECT COUNT(*) FROM meeting_transcripts WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT state FROM meeting_audio WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == ("unavailable",)
        assert connection.execute(
            "SELECT enabled, authority_generation FROM accounts WHERE account_id = 'sub-a'"
        ).fetchone() == (0, 1)
    finally:
        connection.close()
    assert list(work_root.glob("**/*")) == []


def test_file_meeting_failure_is_durable_and_recoverable(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    runner = ControlledRunner(failure=RuntimeError("provider unavailable"))
    app = make_app(database, runner, tmp_path / "file-work")

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
        assert meeting["audio"] is None
        assert meeting["transcript_version"] == 0

    restarted = make_app(database, None, tmp_path / "restart-work")
    with TestClient(restarted, base_url="https://moss.test") as client:
        session(client, sessions["sub-a-second"])
        assert client.get(f"/api/meetings/{meeting_id}").json() == meeting


@pytest.mark.parametrize("failure_arm", ["commit", "publication"])
def test_unresumed_failure_is_durable_and_resignals_task(
    tmp_path: Path, failure_arm: str
):
    """D4: ordinary File work retains its settlement failure signal."""

    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    runner = ControlledRunner()
    app = make_app(database, runner, tmp_path / "file-work")
    original_commit = MeetingHandle.commit_transcript
    original_publish = MeetingHandle.record_audio_unavailable
    failure_seen = threading.Event()

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        accepted = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", b"ordinary-failure", "audio/wav")},
        )
        meeting_id = accepted.json()["id"]
        assert runner.started.wait(timeout=2)
        entry = app.state.phase2_file_tasks._tasks[meeting_id]
        owner_dir = app.state.phase2_file_tasks.retained_root / "sub-a" / meeting_id

        async def fail_commit(self, document, *, terminal=False):
            if self.meeting_id != meeting_id:
                return await original_commit(self, document, terminal=terminal)
            failure_seen.set()
            raise RuntimeError("controlled ordinary commit failure")

        async def fail_publication(self):
            if self.meeting_id != meeting_id:
                return await original_publish(self)
            failure_seen.set()
            raise RuntimeError("controlled ordinary publication failure")

        if failure_arm == "commit":
            MeetingHandle.commit_transcript = fail_commit
        else:
            MeetingHandle.record_audio_unavailable = fail_publication
        try:
            runner.release.set()
            assert failure_seen.wait(timeout=2)
            meeting = await_terminal(client, meeting_id, "failed")
            deadline = time.monotonic() + 2
            while not entry.task.done() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert isinstance(entry.task.exception(), RuntimeError)
            assert meeting["failure_code"] == "storage_failed"
            assert not owner_dir.exists()
        finally:
            MeetingHandle.commit_transcript = original_commit
            MeetingHandle.record_audio_unavailable = original_publish


def test_revocation_fences_late_file_result_commit(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i18-late-file-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    runner = ControlledRunner()
    app = make_app(
        database,
        runner,
        tmp_path / "file-work",
        control_socket=socket,
    )

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        accepted = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", b"input", "audio/wav")},
        )
        meeting_id = accepted.json()["id"]
        assert runner.started.wait(timeout=2)

        outcome: dict[str, object] = {}

        def revoke() -> None:
            outcome["result"] = asyncio.run(
                execute_admin(socket, "revoke", "sub-a")
            )

        worker = threading.Thread(target=revoke)
        worker.start()
        deadline = time.monotonic() + 2
        while ("sub-a", 0) not in app.state.phase2_file_tasks._fenced_owner_keys:
            if time.monotonic() >= deadline:
                raise AssertionError("late File result was not fenced")
            time.sleep(0.01)
        runner.release.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert outcome == {
            "result": {"account_id": "sub-a", "revoked": True}
        }
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
            account, _ = await seed_workspace(store, "sub-a")
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


def test_shutdown_preserves_meeting_owned_source_before_restart_recovery(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    work_root = tmp_path / "file-work"
    runner = ControlledRunner()
    app = make_app(database, runner, work_root)
    client = TestClient(app, base_url="https://moss.test")
    client.__enter__()
    session(client, sessions["sub-a"])
    accepted = client.post(
        "/api/meetings/file",
        files={"file": ("meeting.wav", b"shutdown-input", "audio/wav")},
    )
    meeting_id = accepted.json()["id"]
    assert runner.started.wait(timeout=2)
    source = app.state.phase2_file_tasks.retained_root / "sub-a" / meeting_id / "input.wav"

    shutdown_error: list[BaseException] = []

    def shutdown() -> None:
        try:
            client.__exit__(None, None, None)
        except BaseException as exc:  # pragma: no cover - asserted empty below.
            shutdown_error.append(exc)

    shutdown_thread = threading.Thread(target=shutdown)
    shutdown_thread.start()
    time.sleep(0.05)
    assert shutdown_thread.is_alive()
    assert source.exists()
    assert app.state.phase2_file_tasks._tasks

    runner.release.set()
    shutdown_thread.join(timeout=5)
    assert not shutdown_thread.is_alive()
    assert shutdown_error == []
    assert source.exists()
    assert app.state.phase2_file_tasks._tasks == {}

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT status FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == ("active",)
        assert connection.execute(
            "SELECT COUNT(*) FROM meeting_transcripts WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == (0,)
    finally:
        connection.close()

    restart_runner = ControlledRunner()
    restarted = make_app(database, restart_runner, work_root)
    with TestClient(restarted, base_url="https://moss.test") as after_restart:
        session(after_restart, sessions["sub-a-second"])
        assert restart_runner.started.wait(timeout=2)
        restart_runner.release.set()
        meeting = await_terminal(after_restart, meeting_id, "completed")
        assert meeting["transcript_version"] == 1
        assert meeting["transcript"] is not None
        assert restart_runner.inputs == [("input.wav", b"shutdown-input")]


def test_startup_removes_transient_crash_orphan_after_durable_recovery(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    work_root = tmp_path / "file-work"
    orphan = work_root / "crash-orphan" / "input.wav"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"private transient source")

    async def create_active() -> str:
        store = await Phase2Store.open(database)
        try:
            account = await store.account_for_session(sessions["sub-a"])
            assert account is not None
            return (await store.workspace(account).create_meeting("file")).meeting_id
        finally:
            await store.close()

    meeting_id = asyncio.run(create_active())
    app = make_app(database, ControlledRunner(), work_root)
    with TestClient(app, base_url="https://moss.test") as client:
        assert not orphan.exists()
        assert list(work_root.iterdir()) == []
        session(client, sessions["sub-a"])
        assert client.get(f"/api/meetings/{meeting_id}").json()["status"] == "interrupted"


def test_startup_removes_file_mp3_crash_stage_before_truthful_interruption(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    work_root = tmp_path / "file-work"

    async def create_crashed_file() -> str:
        store = await Phase2Store.open(database)
        try:
            account = await store.account_for_session(sessions["sub-a"])
            assert account is not None
            handle = await store.workspace(account).create_meeting("file")
            await handle.commit_transcript(
                {"segments": [{"id": "seg_0001", "text": "durable file transcript"}]}
            )
            return handle.meeting_id
        finally:
            await store.close()

    meeting_id = asyncio.run(create_crashed_file())
    meeting_dir = tmp_path / "meetings" / "sub-a" / meeting_id
    meeting_dir.mkdir(parents=True)
    staged = meeting_dir / ".audio.staged.mp3"
    staged.write_bytes(b"crash-staged-file-mp3")

    app = make_app(database, ControlledRunner(), work_root)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "interrupted"
        assert meeting["transcript"]["segments"][0]["text"] == "durable file transcript"
        assert meeting["audio"]["state"] == "unavailable"
        assert not staged.exists()
        assert not tuple(meeting_dir.glob("*.mp3"))


def test_startup_cleanup_failure_blocks_admission_logs_no_content_and_closes_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    database = tmp_path / "moss.sqlite3"
    asyncio.run(provision(database))
    work_root = tmp_path / "file-work"
    orphan = work_root / "private-orphan" / "input.wav"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"sentinel private source")
    store_closed = threading.Event()
    original_close = Phase2Store.close

    async def tracked_close(store: Phase2Store) -> None:
        store_closed.set()
        await original_close(store)

    def fail_remove(path: str | Path) -> None:
        raise OSError("sentinel private source must not enter logs")

    monkeypatch.setattr(Phase2Store, "close", tracked_close)
    monkeypatch.setattr(phase2_file.shutil, "rmtree", fail_remove)
    app = make_app(database, ControlledRunner(), work_root)
    with caplog.at_level(logging.ERROR, logger="moss_transcribe_diarize.app.phase2_file"):
        with pytest.raises(RuntimeError, match="Transient File work cleanup failed"):
            with TestClient(app, base_url="https://moss.test"):
                raise AssertionError("startup cleanup failure must prevent admission")

    assert store_closed.is_set()
    assert orphan.exists()
    assert "Transient File work cleanup failed." in caplog.text
    assert "sentinel private source" not in caplog.text


def test_failed_retained_cleanup_preserves_completed_meeting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    work_root = tmp_path / "file-work"
    runner = ControlledRunner()
    app = make_app(database, runner, work_root)
    original_rmtree = phase2_file.shutil.rmtree

    with TestClient(app, base_url="https://moss.test") as client, caplog.at_level(
        logging.ERROR, logger="moss_transcribe_diarize.app.phase2_file"
    ):
        session(client, sessions["sub-a"])
        accepted = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", b"retained-on-failure", "audio/wav")},
        )
        meeting_id = accepted.json()["id"]
        assert runner.started.wait(timeout=2)
        source = app.state.phase2_file_tasks.retained_root / "sub-a" / meeting_id / "input.wav"

        def fail_remove(path: str | Path) -> None:
            if Path(path) == source.parent:
                raise OSError("secret path must not enter logs")
            original_rmtree(path)

        monkeypatch.setattr(phase2_file.shutil, "rmtree", fail_remove)
        runner.release.set()
        meeting = await_terminal(client, meeting_id, "completed")
        deadline = time.monotonic() + 5
        while app.state.phase2_file_tasks._tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        assert app.state.phase2_file_tasks._tasks == {}
        assert meeting["transcript"]["segments"][0]["text"] == "owner sentinel"
        assert meeting["audio"]["state"] == "unavailable"
        assert source.exists()
        assert "Retained File Meeting cleanup failed after terminal completion." in caplog.text
        assert "secret path" not in caplog.text
        monkeypatch.setattr(phase2_file.shutil, "rmtree", original_rmtree)

    original_rmtree(app.state.phase2_file_tasks.retained_root)


def test_deployed_file_inference_settings_reach_runner(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    runner = ControlledRunner()
    runner.release.set()
    app = create_phase2_app(
        database_path=database,
        file_runner=runner,
        file_work_root=tmp_path / "file-work",
        file_inference_options={
            "prompt": "deployed prompt",
            "max_length": 16384,
            "max_new_tokens": 12000,
            "decoding": "greedy",
            "temperature": 1.0,
        },
    )

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        meeting_id = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", b"configured", "audio/wav")},
        ).json()["id"]
        await_terminal(client, meeting_id, "completed")

    assert len(runner.options) == 1
    assert runner.options[0].pop("checkpoint_dir") == (
        tmp_path / "file-retained" / "sub-a" / meeting_id / "checkpoint"
    )
    assert runner.options == [{
        "prompt": "deployed prompt",
        "max_length": 16384,
        "max_new_tokens": 12000,
        "decoding": "greedy",
    }]
