from __future__ import annotations

import asyncio
import json
import multiprocessing
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from moss_transcribe_diarize.app import server
from moss_transcribe_diarize.app import jobs as jobs_module
from moss_transcribe_diarize.app.live_auth import LivePeer
from moss_transcribe_diarize.app.live_service_runtime import active_live_session_count
from moss_transcribe_diarize.app.phase1_creation_quiesce import (
    PHASE1_CREATION_GATE_UNAVAILABLE,
    PHASE1_CREATION_QUIESCED,
    Phase1CreationGate,
    Phase1CreationRefused,
    disable_phase1_creation_quiesce,
    enable_phase1_creation_quiesce,
)
from moss_transcribe_diarize.app.phase1_quiesce_cli import main as quiesce_cli_main
from test_app_api import CheckpointRecordingRunner, NoopRunner
from test_live_api import (
    LIVE_AUTH_FINGERPRINT,
    frame_payload,
    helper_heartbeat_payload,
    make_live_runtime,
)
from test_live_terminal_lifecycle import (
    _ManualTerminalScheduler,
    _finalizer as terminal_finalizer,
    _runtime as make_terminal_runtime,
    _stop_after_a_meeting,
)


def _wait_for_job(client: TestClient, job_id: str) -> dict[str, object]:
    observed: dict[str, object] = {}
    for _ in range(200):
        observed = client.get(f"/api/jobs/{job_id}").json()
        if observed.get("status") in {"waiting_review", "done", "failed", "cancelled"}:
            return observed
        time.sleep(0.01)
    raise AssertionError(f"job did not settle: {observed}")


def _pair_live_clients(app):
    local = TestClient(
        app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )
    remote = TestClient(
        app,
        base_url="https://moss.test",
        client=("192.168.68.20", 50001),
    )
    grant = local.post("/api/live/pairing-codes")
    assert grant.status_code == 200
    pairing = remote.post(
        "/api/live/pairings",
        json={
            "device_id": "quiesce-test-device",
            "pairing_payload": grant.json()["pairing_payload"],
        },
    )
    assert pairing.status_code == 200
    return local, remote, {"Authorization": f"Bearer {pairing.json()['device_token']}"}


class _SecondCallBlockingRunner(NoopRunner):
    def __init__(self) -> None:
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()

    def transcribe(self, audio_path, **kwargs):
        self.calls += 1
        if self.calls == 2:
            self.started.set()
            assert self.release.wait(timeout=10)
        return super().transcribe(audio_path, **kwargs)


def _assert_quiesced(response) -> None:
    assert response.status_code == 503
    assert response.json()["failure"] == {
        "code": PHASE1_CREATION_QUIESCED,
        "retryable": True,
        "state": "quiesced",
    }


def _phase1_process_status_worker(marker: str, runs_dir: str, connection: Any) -> None:
    """One real process-local runtime status view over the shared host marker."""

    gate = Phase1CreationGate(Path(marker))
    app = server.create_app(
        model_path="fake-model",
        runs_dir=Path(runs_dir),
        file_mode_runner=NoopRunner(),
        phase1_creation_gate=gate,
    )
    client = TestClient(app)
    admission = None
    connection.send(
        {"pid": os.getpid(), "status": client.get("/api/runtime").json()["phase1_creation"]}
    )
    try:
        while True:
            command = connection.recv()
            if command == "enter":
                admission = gate.enter()
            elif command == "release":
                assert admission is not None
                admission.close()
                admission = None
            elif command == "exit":
                connection.send({"pid": os.getpid(), "closed": True})
                return
            elif command != "status":
                raise AssertionError(f"unknown command: {command}")
            connection.send(
                {
                    "pid": os.getpid(),
                    "status": client.get("/api/runtime").json()["phase1_creation"],
                }
            )
    finally:
        if admission is not None:
            admission.close()
        connection.close()


def _process_status_command(connection: Any, command: str) -> dict[str, Any]:
    connection.send(command)
    assert connection.poll(15), f"spawned process did not answer {command!r}"
    return connection.recv()


def _start_phase1_status_process(context: Any, marker: Path, runs_dir: Path):
    parent, child = context.Pipe()
    process = context.Process(
        target=_phase1_process_status_worker,
        args=(str(marker), str(runs_dir), child),
        name=f"moss-phase1-test-{runs_dir.name}",
    )
    process.start()
    child.close()
    if not parent.poll(15):
        process.terminate()
        process.join(timeout=5)
        raise AssertionError(f"spawned process {runs_dir.name!r} did not start")
    return process, parent, parent.recv()


def _stop_phase1_status_process(process: Any, connection: Any) -> None:
    if process.is_alive():
        try:
            _process_status_command(connection, "exit")
        except (BrokenPipeError, EOFError):
            pass
        process.join(timeout=10)
    connection.close()
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)


def test_marker_and_counted_admission_are_durable_private_and_fail_closed(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "state" / "phase1-creation-quiesced"
    gate = Phase1CreationGate(marker)
    assert gate.snapshot().to_dict() == {"state": "open", "entrants": 0}

    first = gate.enter()
    second = gate.enter()
    assert gate.snapshot().entrants == 2
    first.close()
    first.close()
    assert gate.snapshot().entrants == 1
    second.close()
    with pytest.raises(RuntimeError, match="probe failure"):
        with gate.enter():
            raise RuntimeError("probe failure")
    assert gate.snapshot().entrants == 0

    enable_phase1_creation_quiesce(marker)
    enable_phase1_creation_quiesce(marker)
    assert marker.stat().st_mode & 0o777 == 0o600
    assert marker.parent.stat().st_mode & 0o777 == 0o700
    assert Phase1CreationGate(marker).snapshot().state == "quiesced"
    with pytest.raises(Phase1CreationRefused) as refused:
        gate.enter()
    assert refused.value.code == PHASE1_CREATION_QUIESCED
    assert gate.snapshot().entrants == 0

    disable_phase1_creation_quiesce(marker)
    disable_phase1_creation_quiesce(marker)
    assert gate.snapshot().state == "open"

    broken_parent = tmp_path / "not-a-directory"
    broken_parent.write_text("file", encoding="utf-8")
    broken_gate = Phase1CreationGate(broken_parent / "marker")
    assert broken_gate.snapshot().state == "error"
    with pytest.raises(Phase1CreationRefused) as unavailable:
        broken_gate.enter()
    assert unavailable.value.code == PHASE1_CREATION_GATE_UNAVAILABLE
    assert broken_gate.snapshot().entrants == 0


def test_distinct_os_processes_share_marker_but_report_local_admission(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "host-state" / "phase1-creation-quiesced"
    context = multiprocessing.get_context("spawn")
    first, first_connection, first_initial = _start_phase1_status_process(
        context, marker, tmp_path / "first-runs"
    )
    second, second_connection, second_initial = _start_phase1_status_process(
        context, marker, tmp_path / "second-runs"
    )
    replacement = None
    replacement_connection = None
    try:
        assert len({os.getpid(), first_initial["pid"], second_initial["pid"]}) == 3
        assert first_initial["status"]["state"] == "open"
        assert second_initial["status"]["state"] == "open"

        first_held = _process_status_command(first_connection, "enter")
        second_while_held = _process_status_command(second_connection, "status")
        assert first_held["status"]["entrants"] == 1
        assert second_while_held["status"]["entrants"] == 0

        enable_phase1_creation_quiesce(marker)
        assert _process_status_command(first_connection, "status")["status"] == {
            "state": "quiesced",
            "entrants": 1,
            "active_jobs": 0,
            "queued_jobs": 0,
            "active_live_sessions": 0,
        }
        assert _process_status_command(second_connection, "status")["status"] == {
            "state": "quiesced",
            "entrants": 0,
            "active_jobs": 0,
            "queued_jobs": 0,
            "active_live_sessions": 0,
        }
        assert _process_status_command(first_connection, "release")["status"]["entrants"] == 0

        _stop_phase1_status_process(second, second_connection)
        replacement, replacement_connection, replacement_initial = (
            _start_phase1_status_process(
                context, marker, tmp_path / "replacement-runs"
            )
        )
        assert replacement_initial["pid"] not in {
            os.getpid(),
            first_initial["pid"],
            second_initial["pid"],
        }
        assert replacement_initial["status"]["state"] == "quiesced"

        disable_phase1_creation_quiesce(marker)
        assert _process_status_command(first_connection, "status")["status"]["state"] == "open"
        assert (
            _process_status_command(replacement_connection, "status")["status"]["state"]
            == "open"
        )
    finally:
        _stop_phase1_status_process(first, first_connection)
        if second.is_alive():
            _stop_phase1_status_process(second, second_connection)
        if replacement is not None and replacement_connection is not None:
            _stop_phase1_status_process(replacement, replacement_connection)


def test_operator_command_is_idempotent_and_reports_only_host_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    marker = tmp_path / "state" / "phase1-creation-quiesced"
    for operation, expected in (
        ("enable", "quiesced"),
        ("enable", "quiesced"),
        ("status", "quiesced"),
        ("disable", "open"),
        ("disable", "open"),
    ):
        monkeypatch.setattr(
            sys,
            "argv",
            ["mtd-phase1-quiesce", operation, "--marker-path", str(marker)],
        )
        quiesce_cli_main()
        payload = json.loads(capsys.readouterr().out)
        assert payload == {
            "schema": "moss.phase1-creation-quiesce.v1",
            "state": expected,
            "marker_path": str(marker),
        }


def test_two_phase1_processes_quiesce_new_work_and_drain_existing_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "host-state" / "phase1-creation-quiesced"
    batch_gate = Phase1CreationGate(marker)
    live_gate = Phase1CreationGate(marker)
    runner = _SecondCallBlockingRunner()
    batch_app = server.create_app(
        model_path="fake-model",
        runs_dir=tmp_path / "batch-runs",
        file_mode_runner=runner,
        phase1_creation_gate=batch_gate,
    )
    live_app = server.create_app(
        model_path="fake-model",
        runs_dir=tmp_path / "live-runs",
        file_mode_runner=NoopRunner(),
        live_enabled=True,
        live_runtime_factory=lambda: make_live_runtime(
            max_retained_samples=16,
            session_ids=("quiesce-stop", "quiesce-abort"),
        ),
        live_auth_state_path=tmp_path / "live-auth.json",
        live_server_cert_sha256=LIVE_AUTH_FINGERPRINT,
        live_helper_lease_seconds=30.0,
        phase1_creation_gate=live_gate,
    )
    batch = TestClient(batch_app)
    _local, live, live_headers = _pair_live_clients(live_app)

    malformed_file = batch.post("/api/jobs", files={})
    assert malformed_file.status_code == 400
    malformed_live = live.post(
        "/api/live/sessions",
        headers=live_headers,
        json={"echo_mode": "invalid"},
    )
    assert malformed_live.status_code == 400
    assert batch_gate.snapshot().entrants == 0
    assert live_gate.snapshot().entrants == 0

    constructor_open: list[dict[str, object]] = []
    constructor_cleanup: list[dict[str, object]] = []
    original_path_open = Path.open
    original_rmtree = jobs_module.shutil.rmtree
    batch_runs = tmp_path / "batch-runs"

    def fail_staging_open(path: Path, *args, **kwargs):
        if path.name.endswith(".uploading"):
            constructor_open.append(
                {
                    "entrants": batch_gate.snapshot().entrants,
                    "job_dir_exists": path.parent.exists(),
                }
            )
            raise OSError("test staging open failure")
        return original_path_open(path, *args, **kwargs)

    def observed_rmtree(path, *args, **kwargs):
        if Path(path).parent == batch_runs:
            constructor_cleanup.append(
                {
                    "entrants": batch_gate.snapshot().entrants,
                    "job_dir_exists": Path(path).exists(),
                }
            )
        return original_rmtree(path, *args, **kwargs)

    with monkeypatch.context() as construction:
        construction.setattr(Path, "open", fail_staging_open)
        construction.setattr(jobs_module.shutil, "rmtree", observed_rmtree)
        constructor_failed = batch.post(
            "/api/jobs",
            files={"file": ("constructor-failure.wav", b"body", "audio/wav")},
        )

    assert constructor_failed.status_code == 400
    assert constructor_open == [{"entrants": 1, "job_dir_exists": True}]
    assert constructor_cleanup == [{"entrants": 1, "job_dir_exists": True}]
    assert list(batch_runs.iterdir()) == []
    expected_open_runtime = {
        "state": "open",
        "entrants": 0,
        "active_jobs": 0,
        "queued_jobs": 0,
        "active_live_sessions": 0,
    }
    assert batch.get("/api/runtime").json()["phase1_creation"] == expected_open_runtime
    assert live.get("/api/runtime").json()["phase1_creation"] == expected_open_runtime

    first = batch.post(
        "/api/jobs",
        files={"file": ("first.wav", b"first", "audio/wav")},
    )
    assert first.status_code == 200
    first_id = first.json()["id"]
    _wait_for_job(batch, first_id)
    stop_id = live.post("/api/live/sessions", headers=live_headers).json()["id"]
    abort_id = live.post("/api/live/sessions", headers=live_headers).json()["id"]

    rerun_copy_entered = threading.Event()
    release_rerun_copy = threading.Event()
    rerun_copy_observations: list[dict[str, object]] = []
    rerun_cleanup_observations: list[dict[str, object]] = []
    original_copyfile = jobs_module.shutil.copyfile
    original_rmtree = jobs_module.shutil.rmtree
    before_job_ids = sorted(job.id for job in batch_app.state.manager.list_jobs())
    before_job_dirs = sorted(path.name for path in (tmp_path / "batch-runs").iterdir())
    before_queue = batch_app.state.manager._queue.qsize()

    def held_partial_copy(source, destination, *args, **kwargs):
        rerun_copy_entered.set()
        assert release_rerun_copy.wait(timeout=5)
        with Path(source).open("rb") as incoming, Path(destination).open("wb") as output:
            output.write(incoming.read(4))
            output.flush()
        rerun_copy_observations.append(
            {
                "entrants": batch_gate.snapshot().entrants,
                "state": batch_gate.snapshot().state,
                "destination": Path(destination).read_bytes(),
            }
        )
        raise OSError("test partial rerun copy failure")

    def observed_rerun_rmtree(path, *args, **kwargs):
        if Path(path).parent == tmp_path / "batch-runs":
            rerun_cleanup_observations.append(
                {
                    "entrants": batch_gate.snapshot().entrants,
                    "state": batch_gate.snapshot().state,
                    "job_dir_exists": Path(path).exists(),
                }
            )
        return original_rmtree(path, *args, **kwargs)

    rerun_result: dict[str, object] = {}

    def fail_preadmitted_rerun() -> None:
        response = batch.post(f"/api/jobs/{first_id}/rerun", json={})
        rerun_result["status"] = response.status_code

    with monkeypatch.context() as rerun_failure:
        rerun_failure.setattr(jobs_module.shutil, "copyfile", held_partial_copy)
        rerun_failure.setattr(jobs_module.shutil, "rmtree", observed_rerun_rmtree)
        rerun_thread = threading.Thread(target=fail_preadmitted_rerun, daemon=True)
        rerun_thread.start()
        assert rerun_copy_entered.wait(timeout=5)
        assert batch_gate.snapshot().to_dict() == {"state": "open", "entrants": 1}
        enable_phase1_creation_quiesce(marker)
        assert batch.get("/api/runtime").json()["phase1_creation"]["entrants"] == 1
        assert live.get("/api/runtime").json()["phase1_creation"]["active_live_sessions"] == 2
        release_rerun_copy.set()
        rerun_thread.join(timeout=5)

    assert not rerun_thread.is_alive()
    assert rerun_result == {"status": 400}
    assert rerun_copy_observations == [
        {"entrants": 1, "state": "quiesced", "destination": b"firs"}
    ]
    assert rerun_cleanup_observations == [
        {"entrants": 1, "state": "quiesced", "job_dir_exists": True}
    ]
    assert sorted(job.id for job in batch_app.state.manager.list_jobs()) == before_job_ids
    assert batch_app.state.manager._queue.qsize() == before_queue
    assert sorted(path.name for path in (tmp_path / "batch-runs").iterdir()) == before_job_dirs
    assert batch.get("/api/runtime").json()["phase1_creation"] == {
        "state": "quiesced",
        "entrants": 0,
        "active_jobs": 0,
        "queued_jobs": 0,
        "active_live_sessions": 0,
    }
    assert live.get("/api/runtime").json()["phase1_creation"] == {
        "state": "quiesced",
        "entrants": 0,
        "active_jobs": 0,
        "queued_jobs": 0,
        "active_live_sessions": 2,
    }
    disable_phase1_creation_quiesce(marker)

    original_read = server._read_upload_chunk
    upload_started = threading.Event()
    release_upload = threading.Event()
    first_read = True

    async def held_read(upload) -> bytes:
        nonlocal first_read
        if first_read:
            first_read = False
            upload_started.set()
            await asyncio.to_thread(release_upload.wait, 10)
        return await original_read(upload)

    monkeypatch.setattr(server, "_read_upload_chunk", held_read)
    held_result: dict[str, object] = {}

    def create_held_job() -> None:
        response = batch.post(
            "/api/jobs",
            files={"file": ("held.wav", b"held", "audio/wav")},
        )
        held_result["status"] = response.status_code
        held_result["body"] = response.json()

    upload_thread = threading.Thread(target=create_held_job, daemon=True)
    upload_thread.start()
    assert upload_started.wait(timeout=5)
    assert batch.get("/api/runtime").json()["phase1_creation"] == {
        "state": "open",
        "entrants": 1,
        "active_jobs": 0,
        "queued_jobs": 0,
        "active_live_sessions": 0,
    }

    enable_phase1_creation_quiesce(marker)
    assert batch.get("/api/runtime").json()["phase1_creation"]["entrants"] == 1
    assert batch.get("/api/runtime").json()["phase1_creation"]["state"] == "quiesced"
    assert live.get("/api/runtime").json()["phase1_creation"] == {
        "state": "quiesced",
        "entrants": 0,
        "active_jobs": 0,
        "queued_jobs": 0,
        "active_live_sessions": 2,
    }

    _assert_quiesced(
        batch.post(
            "/api/jobs",
            files={"file": ("blocked.wav", b"blocked", "audio/wav")},
        )
    )
    _assert_quiesced(batch.post(f"/api/jobs/{first_id}/rerun", json={}))
    _assert_quiesced(batch.post(f"/api/jobs/{first_id}/resume"))
    _assert_quiesced(batch.post(f"/api/jobs/{first_id}/render", json={}))
    _assert_quiesced(live.post("/api/live/sessions", headers=live_headers))
    assert len(batch_app.state.manager.list_jobs()) == 1
    assert active_live_session_count(live_app.state.live_runtime) == 2

    assert live.post(
        f"/api/live/sessions/{stop_id}/heartbeat",
        headers=live_headers,
        json=helper_heartbeat_payload(),
    ).status_code == 200
    assert live.post(
        f"/api/live/sessions/{stop_id}/frames",
        headers=live_headers,
        json=frame_payload(0, 2),
    ).status_code == 200
    assert live.get(
        f"/api/live/sessions/{stop_id}/snapshot",
        headers=live_headers,
    ).status_code == 200
    assert live.get(
        f"/api/live/sessions/{stop_id}/events?since_seq=-1",
        headers=live_headers,
    ).status_code == 200
    assert batch.get(f"/api/jobs/{first_id}/download?kind=transcript").status_code == 200

    release_upload.set()
    upload_thread.join(timeout=5)
    assert not upload_thread.is_alive()
    assert held_result["status"] == 200
    held_id = held_result["body"]["id"]
    assert runner.started.wait(timeout=5)
    status_while_running = batch.get("/api/runtime").json()["phase1_creation"]
    assert status_while_running["entrants"] == 0
    assert status_while_running["active_jobs"] + status_while_running["queued_jobs"] == 1

    assert live.post(
        f"/api/live/sessions/{stop_id}/stop",
        headers=live_headers,
        json={"deadline": 1.0},
    ).status_code == 200
    assert live.post(
        f"/api/live/sessions/{abort_id}/abort",
        headers=live_headers,
        json={"reason": "phase1 cutover drain"},
    ).status_code == 200
    runner.release.set()
    _wait_for_job(batch, held_id)
    assert batch.get("/api/runtime").json()["phase1_creation"] == {
        "state": "quiesced",
        "entrants": 0,
        "active_jobs": 0,
        "queued_jobs": 0,
        "active_live_sessions": 0,
    }
    assert live.get("/api/runtime").json()["phase1_creation"] == {
        "state": "quiesced",
        "entrants": 0,
        "active_jobs": 0,
        "queued_jobs": 0,
        "active_live_sessions": 0,
    }

    restarted_gate = Phase1CreationGate(marker)
    restarted_app = server.create_app(
        model_path="fake-model",
        runs_dir=tmp_path / "restart-runs",
        file_mode_runner=NoopRunner(),
        phase1_creation_gate=restarted_gate,
    )
    restarted = TestClient(restarted_app)
    assert restarted.get("/api/runtime").json()["phase1_creation"] == {
        "state": "quiesced",
        "entrants": 0,
        "active_jobs": 0,
        "queued_jobs": 0,
        "active_live_sessions": 0,
    }
    _assert_quiesced(
        restarted.post(
            "/api/jobs",
            files={"file": ("restart.wav", b"restart", "audio/wav")},
        )
    )

    disable_phase1_creation_quiesce(marker)
    reopened = restarted.post(
        "/api/jobs",
        files={"file": ("reopened.wav", b"reopened", "audio/wav")},
    )
    assert reopened.status_code == 200
    _wait_for_job(restarted, reopened.json()["id"])


def test_live_bind_refusal_aborts_owned_raw_session_before_admission_closes(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "state" / "phase1-creation-quiesced"
    gate = Phase1CreationGate(marker)
    app = server.create_app(
        model_path="fake-model",
        runs_dir=tmp_path / "runs",
        file_mode_runner=NoopRunner(),
        live_enabled=True,
        live_runtime_factory=lambda: make_live_runtime(
            max_retained_samples=16,
            session_ids=("bind-failure", "bind-retry"),
        ),
        live_auth_state_path=tmp_path / "live-auth.json",
        live_server_cert_sha256=LIVE_AUTH_FINGERPRINT,
        live_helper_lease_seconds=30.0,
        phase1_creation_gate=gate,
    )
    local, remote, headers = _pair_live_clients(app)
    access = app.state.live_access_registry
    original_bind = access.bind_session
    observed: list[dict[str, object]] = []

    def revoke_then_bind(principal, session_id: str, now: float):
        observed.append(
            {
                "session_id": session_id,
                "entrants": gate.snapshot().entrants,
                "raw_status": app.state.live_runtime.snapshot(session_id).session.status,
                "active_live": active_live_session_count(app.state.live_runtime),
            }
        )
        access.revoke_device(
            LivePeer("127.0.0.1", "http"), principal.device_id, now=now
        )
        return original_bind(principal, session_id, now)

    access.bind_session = revoke_then_bind
    try:
        refused = remote.post("/api/live/sessions", headers=headers)
    finally:
        access.bind_session = original_bind

    assert refused.status_code == 403
    assert observed == [
        {
            "session_id": "bind-failure",
            "entrants": 1,
            "raw_status": "active",
            "active_live": 1,
        }
    ]
    assert gate.snapshot().to_dict() == {"state": "open", "entrants": 0}
    assert app.state.live_runtime.snapshot("bind-failure").session.status == "aborted"
    assert active_live_session_count(app.state.live_runtime) == 0
    assert "bind-failure" not in access._sessions
    assert not app.state.live_v2_sessions.contains("bind-failure")
    assert "bind-failure" not in app.state.live_helper_failures._sessions

    grant = local.post("/api/live/pairing-codes")
    retry_pairing = remote.post(
        "/api/live/pairings",
        json={
            "device_id": "quiesce-retry-device",
            "pairing_payload": grant.json()["pairing_payload"],
        },
    )
    retry_headers = {
        "Authorization": f"Bearer {retry_pairing.json()['device_token']}"
    }
    retried = remote.post("/api/live/sessions", headers=retry_headers)
    assert retried.status_code == 200
    assert active_live_session_count(app.state.live_runtime) == 1
    assert remote.post(
        "/api/live/sessions/bind-retry/abort",
        headers=retry_headers,
        json={"reason": "test cleanup"},
    ).status_code == 200
    assert active_live_session_count(app.state.live_runtime) == 0


def test_resume_save_failure_restores_old_truth_before_admission_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = Phase1CreationGate(tmp_path / "state" / "phase1-creation-quiesced")
    app = server.create_app(
        model_path="fake-model",
        runs_dir=tmp_path / "runs",
        file_mode_runner=CheckpointRecordingRunner(),
        phase1_creation_gate=gate,
    )
    client = TestClient(app)
    created = client.post(
        "/api/jobs", files={"file": ("resume.wav", b"resume", "audio/wav")}
    )
    job_id = created.json()["id"]
    _wait_for_job(client, job_id)
    job = app.state.manager.get_job(job_id)
    job.status = "failed"
    job.progress = 0.5
    job.error = "prior failure"
    job.resume_attempts = 2
    job.checkpoint_state = "partial"
    app.state.manager._save_job(job)
    before = job.to_dict()
    save_observed: list[dict[str, object]] = []
    original_save = app.state.manager._save_job

    def fail_candidate(candidate) -> None:
        if candidate.id == job_id and candidate.status == "queued":
            save_observed.append(
                {
                    "entrants": gate.snapshot().entrants,
                    "registry_status": app.state.manager.get_job(job_id).status,
                }
            )
            raise OSError("test resume save failure")
        original_save(candidate)

    monkeypatch.setattr(app.state.manager, "_save_job", fail_candidate)
    failed = client.post(f"/api/jobs/{job_id}/resume")
    assert failed.status_code == 400
    assert save_observed == [{"entrants": 1, "registry_status": "failed"}]
    assert gate.snapshot().entrants == 0
    assert app.state.manager.get_job(job_id).to_dict() == before
    assert json.loads(job.job_path.read_text(encoding="utf-8")) == before
    assert app.state.manager._queue.qsize() == 0
    assert app.state.manager.activity_counts() == {"queued": 0, "active": 0}

    monkeypatch.setattr(app.state.manager, "_save_job", original_save)
    retried = client.post(f"/api/jobs/{job_id}/resume")
    assert retried.status_code == 200
    assert retried.json()["resume_attempts"] == 3
    terminal = _wait_for_job(client, job_id)
    assert terminal["status"] == "waiting_review"
    assert terminal["resume_attempts"] == 3
    assert app.state.manager.activity_counts() == {"queued": 0, "active": 0}


def test_render_save_failure_restores_old_truth_before_thread_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = Phase1CreationGate(tmp_path / "state" / "phase1-creation-quiesced")
    app = server.create_app(
        model_path="fake-model",
        runs_dir=tmp_path / "runs",
        file_mode_runner=NoopRunner(),
        phase1_creation_gate=gate,
    )
    client = TestClient(app)
    created = client.post(
        "/api/jobs", files={"file": ("render.wav", b"render", "audio/wav")}
    )
    job_id = created.json()["id"]
    _wait_for_job(client, job_id)
    job = app.state.manager.get_job(job_id)
    before = job.to_dict()

    class AvailableFfmpeg:
        available = True

    held_threads: list[object] = []

    class HeldThread:
        def __init__(self, *args, **kwargs) -> None:
            self._thread = threading.Thread(*args, **kwargs)

        def start(self) -> None:
            held_threads.append(self)

        def run(self) -> None:
            self._thread.run()

    class ThreadFactory:
        Thread = HeldThread

    monkeypatch.setattr(jobs_module, "threading", ThreadFactory())
    monkeypatch.setattr(jobs_module, "detect_ffmpeg", lambda: AvailableFfmpeg())
    monkeypatch.setattr(jobs_module, "probe_video_size", lambda _path: (1280, 720))
    monkeypatch.setattr(
        jobs_module,
        "burn_ass_subtitles",
        lambda _input, _ass, output: Path(output).write_bytes(b"rendered"),
    )
    original_save = app.state.manager._save_job
    save_observed: list[dict[str, object]] = []

    def fail_candidate(candidate) -> None:
        if candidate.id == job_id and candidate.status == "rendering":
            save_observed.append(
                {
                    "entrants": gate.snapshot().entrants,
                    "registry_status": app.state.manager.get_job(job_id).status,
                }
            )
            raise OSError("test render save failure")
        original_save(candidate)

    monkeypatch.setattr(app.state.manager, "_save_job", fail_candidate)
    failed = client.post(f"/api/jobs/{job_id}/render", json={})
    assert failed.status_code == 400
    assert save_observed == [{"entrants": 1, "registry_status": "waiting_review"}]
    assert gate.snapshot().entrants == 0
    assert app.state.manager.get_job(job_id).to_dict() == before
    assert json.loads(job.job_path.read_text(encoding="utf-8")) == before
    assert held_threads == []
    assert app.state.manager.activity_counts() == {"queued": 0, "active": 0}

    monkeypatch.setattr(app.state.manager, "_save_job", original_save)
    retried = client.post(f"/api/jobs/{job_id}/render", json={})
    assert retried.status_code == 200
    assert retried.json()["status"] == "rendering"
    assert len(held_threads) == 1
    assert app.state.manager.activity_counts() == {"queued": 0, "active": 1}
    held_threads[0].run()
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "done"
    assert app.state.manager.activity_counts() == {"queued": 0, "active": 0}


def test_preadmitted_render_is_durably_active_before_its_thread_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "state" / "phase1-creation-quiesced"
    gate = Phase1CreationGate(marker)
    app = server.create_app(
        model_path="fake-model",
        runs_dir=tmp_path / "runs",
        file_mode_runner=NoopRunner(),
        phase1_creation_gate=gate,
    )
    client = TestClient(app)
    created = client.post(
        "/api/jobs",
        files={"file": ("render.wav", b"render", "audio/wav")},
    )
    assert created.status_code == 200
    job_id = created.json()["id"]
    _wait_for_job(client, job_id)

    class AvailableFfmpeg:
        available = True

    held_threads: list[object] = []

    class HeldThread:
        def __init__(self, *args, **kwargs) -> None:
            self._thread = threading.Thread(*args, **kwargs)

        def start(self) -> None:
            held_threads.append(self)

        def run(self) -> None:
            self._thread.run()

    class ThreadFactory:
        Thread = HeldThread

    monkeypatch.setattr(jobs_module, "threading", ThreadFactory())
    monkeypatch.setattr(jobs_module, "detect_ffmpeg", lambda: AvailableFfmpeg())
    monkeypatch.setattr(jobs_module, "probe_video_size", lambda _path: (1280, 720))
    monkeypatch.setattr(
        jobs_module,
        "burn_ass_subtitles",
        lambda _input, _ass, output: Path(output).write_bytes(b"rendered"),
    )

    started = client.post(f"/api/jobs/{job_id}/render", json={})
    assert started.status_code == 200
    assert started.json()["status"] == "rendering"
    assert gate.snapshot().entrants == 0
    assert len(held_threads) == 1

    enable_phase1_creation_quiesce(marker)
    assert client.get("/api/runtime").json()["phase1_creation"] == {
        "state": "quiesced",
        "entrants": 0,
        "active_jobs": 1,
        "queued_jobs": 0,
        "active_live_sessions": 0,
    }
    held_threads[0].run()
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "done"
    assert client.get("/api/runtime").json()["phase1_creation"]["active_jobs"] == 0


def test_runtime_counts_closed_terminal_finalization_until_real_pass_finishes(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "state" / "phase1-creation-quiesced"
    gate = Phase1CreationGate(marker)
    scheduler = _ManualTerminalScheduler()
    runtime, _witness = make_terminal_runtime(
        finalizer=terminal_finalizer(), scheduler=scheduler
    )
    session_id = _stop_after_a_meeting(runtime)
    enable_phase1_creation_quiesce(marker)
    app = server.create_app(
        model_path="fake-model",
        runs_dir=tmp_path / "runs",
        file_mode_runner=NoopRunner(),
        live_enabled=True,
        live_runtime_factory=lambda: runtime,
        live_auth_state_path=tmp_path / "live-auth.json",
        live_server_cert_sha256=LIVE_AUTH_FINGERPRINT,
        live_helper_lease_seconds=30.0,
        phase1_creation_gate=gate,
    )
    client = TestClient(app)

    held = runtime.snapshot(session_id).session
    assert held.status == "closed"
    assert held.finalization_status == "running"
    assert scheduler.pending == 1
    assert client.get("/api/runtime").json()["phase1_creation"] == {
        "state": "quiesced",
        "entrants": 0,
        "active_jobs": 0,
        "queued_jobs": 0,
        "active_live_sessions": 1,
    }

    assert scheduler.run_one()
    assert runtime.snapshot(session_id).session.finalization_status == "final"
    assert client.get("/api/runtime").json()["phase1_creation"]["active_live_sessions"] == 0


def test_cancelled_upload_aborts_transaction_before_admission_releases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "state" / "phase1-creation-quiesced"
    gate = Phase1CreationGate(marker)
    runs_dir = tmp_path / "runs"
    app = server.create_app(
        model_path="fake-model",
        runs_dir=runs_dir,
        file_mode_runner=NoopRunner(),
        phase1_creation_gate=gate,
    )
    endpoint = next(
        route.endpoint
        for route in app.routes
        if route.path == "/api/jobs" and "POST" in (route.methods or set())
    )
    abort_observations: list[dict[str, object]] = []
    original_abort = jobs_module.UploadTransaction.abort

    def observed_abort(upload) -> None:
        abort_observations.append(
            {
                "entrants": gate.snapshot().entrants,
                "job_dir_exists": Path(upload.job.job_dir).exists(),
                "staging_exists": Path(upload._tmp_path).exists(),
            }
        )
        original_abort(upload)

    monkeypatch.setattr(jobs_module.UploadTransaction, "abort", observed_abort)

    class HeldUpload:
        filename = "cancelled.wav"

        def __init__(self) -> None:
            self.started: asyncio.Event | None = None

        async def read(self, _size: int) -> bytes:
            assert self.started is not None
            self.started.set()
            await asyncio.Event().wait()
            raise AssertionError("cancelled upload read resumed")

    async def exercise() -> None:
        upload = HeldUpload()
        upload.started = asyncio.Event()
        task = asyncio.create_task(endpoint(file=upload))
        await upload.started.wait()
        assert gate.snapshot().entrants == 1
        assert len(list(runs_dir.iterdir())) == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert abort_observations == [
        {"entrants": 1, "job_dir_exists": True, "staging_exists": True}
    ]
    assert gate.snapshot().entrants == 0
    assert list(runs_dir.iterdir()) == []


def test_marker_error_is_visible_and_creation_fails_closed(tmp_path: Path) -> None:
    broken_parent = tmp_path / "not-a-directory"
    broken_parent.write_text("file", encoding="utf-8")
    gate = Phase1CreationGate(broken_parent / "marker")
    app = server.create_app(
        model_path="fake-model",
        runs_dir=tmp_path / "runs",
        file_mode_runner=NoopRunner(),
        phase1_creation_gate=gate,
    )
    client = TestClient(app)
    assert client.get("/api/runtime").json()["phase1_creation"]["state"] == "error"
    response = client.post(
        "/api/jobs",
        files={"file": ("blocked.wav", b"blocked", "audio/wav")},
    )
    assert response.status_code == 503
    assert response.json()["failure"] == {
        "code": PHASE1_CREATION_GATE_UNAVAILABLE,
        "retryable": True,
        "state": "error",
    }
