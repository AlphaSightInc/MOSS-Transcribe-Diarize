#!/usr/bin/env python3
"""PROTOTYPE ONLY: falsify the Phase-1 creation-quiesce state model.

One command:

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
      prototypes/phase1-creation-quiesce/probe.py

The probe spawns two independent operating-system processes, each with a production
``create_app`` runtime-status view over the shared marker, and runs isolated production
registration, upload-cancellation, and terminal-runtime falsifiers. The first recorded verdict
preceded production; this retained bench now prevents the measured state ordering from drifting.
"""

from __future__ import annotations

import asyncio
import json
import multiprocessing
import os
import shutil
import sys
import tempfile
import threading
import time
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tests"))

# The lean development environment intentionally has no torch.  The prototype exercises
# HTTP/job/Live admission, never model construction, so install the same tiny import seam its
# fake runner actually needs instead of making torch an unrelated prerequisite.
inference_utils_stub = types.ModuleType("moss_transcribe_diarize.inference_utils")
inference_utils_stub.DEFAULT_PROMPT = "prototype"
inference_utils_stub.load_audio_item = lambda *_args, **_kwargs: (_ for _ in ()).throw(
    AssertionError("prototype must not decode through the real model adapter")
)
sys.modules["moss_transcribe_diarize.inference_utils"] = inference_utils_stub

model_runner_stub = types.ModuleType("moss_transcribe_diarize.app.model_runner")


@dataclass(slots=True)
class _TranscriptionResult:
    text: str
    prompt_len: int
    generated_tokens: int
    elapsed_sec: float
    model: str
    audio: str
    decoding: str
    temperature: float | None
    top_p: float | None = None
    top_k: int | None = None
    window_count: int | None = None
    completed_windows: int | None = None
    possibly_truncated: bool | None = None
    identity_summary: dict[str, Any] | None = None
    identity_resolution: dict[str, Any] | None = None


class _UnusedModelRunner:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("prototype must inject its fake runner")


model_runner_stub.TranscriptionResult = _TranscriptionResult
model_runner_stub.ModelRunner = _UnusedModelRunner
model_runner_stub.StatusCallback = Any
model_runner_stub.generation_progress = (
    lambda generated_tokens, max_new_tokens: 0.0
    if not max_new_tokens
    else min(1.0, generated_tokens / max_new_tokens)
)
sys.modules["moss_transcribe_diarize.app.model_runner"] = model_runner_stub

from fastapi.testclient import TestClient  # noqa: E402
from test_live_api import (  # noqa: E402
    LIVE_AUTH_FINGERPRINT,
    frame_payload,
    helper_heartbeat_payload,
    make_live_runtime,
)
from test_live_terminal_lifecycle import (  # noqa: E402
    _ManualTerminalScheduler,
    _finalizer as terminal_finalizer,
    _runtime as make_terminal_runtime,
    _stop_after_a_meeting,
)

from moss_transcribe_diarize.app import server  # noqa: E402
from moss_transcribe_diarize.app import jobs as jobs_module  # noqa: E402
from moss_transcribe_diarize.app.jobs import ACTIVE_STATES  # noqa: E402
from moss_transcribe_diarize.app.model_runner import TranscriptionResult  # noqa: E402
from moss_transcribe_diarize.app.live_service_runtime import (  # noqa: E402
    active_live_session_count,
)
from moss_transcribe_diarize.app.live_auth import LivePeer  # noqa: E402
from moss_transcribe_diarize.app.phase1_creation_quiesce import (  # noqa: E402
    PHASE1_CREATION_GATE_UNAVAILABLE,
    PHASE1_CREATION_QUIESCED,
    Phase1CreationGate,
    disable_phase1_creation_quiesce,
    enable_phase1_creation_quiesce,
)


class ProbeRunner:
    model_path = "phase1-quiesce-probe"
    device_name = "cpu"
    dtype_name = "float32"
    window_seconds = 150.0
    stride_seconds = 120.0

    def __init__(self) -> None:
        self._call_count = 0
        self.held_started = threading.Event()
        self.release_held = threading.Event()

    def transcribe(self, audio_path: str, **kwargs: Any) -> TranscriptionResult:
        self._call_count += 1
        if self._call_count == 3:
            self.held_started.set()
            if not self.release_held.wait(timeout=10):
                raise RuntimeError("prototype held runner timed out")
        callback = kwargs.get("status_callback")
        if callback is not None:
            callback("transcribing", 0.5, 1)
        return TranscriptionResult(
            text="[0][S01]prototype[1]",
            prompt_len=1,
            generated_tokens=1,
            elapsed_sec=0.01,
            model=self.model_path,
            audio=str(audio_path),
            decoding="greedy",
            temperature=None,
        )


class ConcurrentResumeRunner(ProbeRunner):
    """Hold a second job so two resume requests can register before worker dequeue."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0
        self.blocker_started = threading.Event()
        self.release_blocker = threading.Event()

    def transcribe(self, audio_path: str, **kwargs: Any) -> TranscriptionResult:
        self.calls += 1
        callback = kwargs.get("status_callback")
        if callback is not None:
            callback("transcribing", 0.5, 1)
        if self.calls == 2:
            self.blocker_started.set()
            if not self.release_blocker.wait(timeout=10):
                raise RuntimeError("prototype resume blocker timed out")
        return TranscriptionResult(
            text="[0][S01]prototype[1]",
            prompt_len=1,
            generated_tokens=1,
            elapsed_sec=0.01,
            model=self.model_path,
            audio=str(audio_path),
            decoding="greedy",
            temperature=None,
        )


def make_batch_app(root: Path, gate: Phase1CreationGate, runner: ProbeRunner):
    app = server.create_app(
        model_path="fake-model",
        runs_dir=root,
        file_mode_runner=runner,
        phase1_creation_gate=gate,
    )
    return app, app


def make_live_app(root: Path, gate: Phase1CreationGate):
    app = server.create_app(
        model_path="fake-model",
        runs_dir=root,
        file_mode_runner=ProbeRunner(),
        live_enabled=True,
        live_runtime_factory=lambda: make_live_runtime(
            max_retained_samples=16,
            session_ids=("prototype-stop", "prototype-abort"),
        ),
        live_auth_state_path=root / "live-auth.json",
        live_server_cert_sha256=LIVE_AUTH_FINGERPRINT,
        live_shared_token="prototype-token",
        live_helper_lease_seconds=30.0,
        phase1_creation_gate=gate,
    )
    return app, app


def job_counts(app: Any) -> dict[str, int]:
    jobs = app.state.manager.list_jobs()
    return {
        "queued": sum(job.status == "queued" for job in jobs),
        "active": sum(job.status in ACTIVE_STATES and job.status != "queued" for job in jobs),
        "total": len(jobs),
    }


def live_active_count(app: Any) -> int:
    return active_live_session_count(app.state.live_runtime)


def wait_job(client: TestClient, job_id: str) -> dict[str, Any]:
    observed: dict[str, Any] = {}
    for _ in range(200):
        observed = client.get(f"/api/jobs/{job_id}").json()
        if observed.get("status") in {"waiting_review", "done", "failed", "cancelled"}:
            return observed
        time.sleep(0.01)
    raise AssertionError(f"job did not settle: {observed}")


def emit(states: list[dict[str, Any]], label: str, **state: Any) -> None:
    record = {"label": label, **state}
    states.append(record)
    print(json.dumps(record, sort_keys=True))


def _phase1_process_worker(marker: str, runs_dir: str, connection: Any) -> None:
    """One spawned production app/gate view; parent supplies only test coordination."""

    gate = Phase1CreationGate(Path(marker))
    app, wrapped = make_batch_app(Path(runs_dir), gate, ProbeRunner())
    client = TestClient(wrapped)
    admission = None
    connection.send({"pid": os.getpid(), "runtime": client.get("/api/runtime").json()["phase1_creation"]})
    try:
        while True:
            command = connection.recv()
            if command == "status":
                connection.send(
                    {
                        "pid": os.getpid(),
                        "runtime": client.get("/api/runtime").json()["phase1_creation"],
                    }
                )
            elif command == "enter":
                admission = gate.enter()
                connection.send(
                    {
                        "pid": os.getpid(),
                        "runtime": client.get("/api/runtime").json()["phase1_creation"],
                    }
                )
            elif command == "release":
                assert admission is not None
                admission.close()
                admission = None
                connection.send(
                    {
                        "pid": os.getpid(),
                        "runtime": client.get("/api/runtime").json()["phase1_creation"],
                    }
                )
            elif command == "exit":
                connection.send({"pid": os.getpid(), "closed": True})
                return
            else:
                raise AssertionError(f"unknown process command: {command}")
    finally:
        if admission is not None:
            admission.close()
        connection.close()


def _process_command(connection: Any, command: str) -> dict[str, Any]:
    connection.send(command)
    if not connection.poll(15):
        raise AssertionError(f"spawned process did not answer {command!r}")
    return connection.recv()


def two_os_process_state(root: Path, marker: Path) -> dict[str, Any]:
    """Prove the marker/reboot truth across two genuinely separate Python processes."""

    context = multiprocessing.get_context("spawn")

    def start(name: str):
        parent, child = context.Pipe()
        process = context.Process(
            target=_phase1_process_worker,
            args=(str(marker), str(root / name), child),
            name=f"moss-phase1-prototype-{name}",
        )
        process.start()
        child.close()
        if not parent.poll(15):
            process.terminate()
            process.join(timeout=5)
            raise AssertionError(f"spawned process {name!r} did not start")
        return process, parent, parent.recv()

    first, first_connection, first_initial = start("process-a")
    second, second_connection, second_initial = start("process-b")
    replacement = None
    replacement_connection = None
    try:
        first_held = _process_command(first_connection, "enter")
        second_while_first_held = _process_command(second_connection, "status")
        enable_phase1_creation_quiesce(marker)
        first_quiesced = _process_command(first_connection, "status")
        second_quiesced = _process_command(second_connection, "status")
        first_released = _process_command(first_connection, "release")
        _process_command(second_connection, "exit")
        second.join(timeout=10)
        replacement, replacement_connection, replacement_initial = start("process-b-restart")
        disable_phase1_creation_quiesce(marker)
        first_reopened = _process_command(first_connection, "status")
        replacement_reopened = _process_command(replacement_connection, "status")
        replacement_held = _process_command(replacement_connection, "enter")
        replacement_released = _process_command(replacement_connection, "release")
        return {
            "parent_pid": os.getpid(),
            "first_initial": first_initial,
            "second_initial": second_initial,
            "first_held": first_held,
            "second_while_first_held": second_while_first_held,
            "first_quiesced": first_quiesced,
            "second_quiesced": second_quiesced,
            "first_released": first_released,
            "second_exitcode": second.exitcode,
            "replacement_initial": replacement_initial,
            "first_reopened": first_reopened,
            "replacement_reopened": replacement_reopened,
            "replacement_held": replacement_held,
            "replacement_released": replacement_released,
        }
    finally:
        for process, connection in (
            (first, first_connection),
            (second, second_connection),
            (replacement, replacement_connection),
        ):
            if process is None or connection is None:
                continue
            if process.is_alive():
                try:
                    _process_command(connection, "exit")
                except (BrokenPipeError, EOFError):
                    pass
                process.join(timeout=10)
            connection.close()
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)


def cancelled_upload_state(root: Path, marker: Path) -> dict[str, Any]:
    """Cancel after upload transaction creation and expose cleanup ordering."""

    gate = Phase1CreationGate(marker)
    app, _wrapped = make_batch_app(root, gate, ProbeRunner())
    endpoint = next(
        route.endpoint
        for route in app.routes
        if route.path == "/api/jobs" and "POST" in (route.methods or set())
    )
    abort_observations: list[dict[str, Any]] = []
    original_abort = jobs_module.UploadTransaction.abort

    def observed_abort(upload: Any) -> None:
        abort_observations.append(
            {
                "entrants": gate.snapshot().entrants,
                "job_dir_exists": Path(upload.job.job_dir).exists(),
                "staging_exists": Path(upload._tmp_path).exists(),
            }
        )
        original_abort(upload)

    jobs_module.UploadTransaction.abort = observed_abort

    class HeldUpload:
        filename = "cancelled.wav"

        def __init__(self) -> None:
            self.started: asyncio.Event | None = None

        async def read(self, _size: int) -> bytes:
            assert self.started is not None
            self.started.set()
            await asyncio.Event().wait()
            raise AssertionError("cancelled upload read resumed")

    async def exercise() -> dict[str, Any]:
        upload = HeldUpload()
        upload.started = asyncio.Event()
        task = asyncio.create_task(endpoint(file=upload))
        await upload.started.wait()
        held_state = {
            "gate": gate.snapshot().to_dict(),
            "job_dirs": sorted(path.name for path in root.iterdir()),
        }
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return {
            "held": held_state,
            "after": {
                "gate": gate.snapshot().to_dict(),
                "job_dirs": sorted(path.name for path in root.iterdir()),
            },
            "abort_observations": abort_observations,
        }

    try:
        result = asyncio.run(exercise())
    finally:
        jobs_module.UploadTransaction.abort = original_abort
        # A deliberately failing pre-production probe still has to release its own scratch
        # resources so TemporaryDirectory can finish and report the derived verdict.
        for path in root.iterdir():
            if path.is_dir():
                shutil.rmtree(path)
    return result


def constructor_failure_state(root: Path, marker: Path) -> dict[str, Any]:
    """Fail the staging-file open after job-dir creation and expose cleanup ordering."""

    gate = Phase1CreationGate(marker)
    app, _wrapped = make_batch_app(root, gate, ProbeRunner())
    endpoint = next(
        route.endpoint
        for route in app.routes
        if route.path == "/api/jobs" and "POST" in (route.methods or set())
    )
    open_observations: list[dict[str, Any]] = []
    cleanup_observations: list[dict[str, Any]] = []
    original_open = Path.open
    original_rmtree = jobs_module.shutil.rmtree

    def fail_staging_open(path: Path, *args: Any, **kwargs: Any):
        if path.name.endswith(".uploading"):
            open_observations.append(
                {
                    "entrants": gate.snapshot().entrants,
                    "job_dir_exists": path.parent.exists(),
                    "staging_exists": path.exists(),
                }
            )
            raise OSError("prototype staging open failure")
        return original_open(path, *args, **kwargs)

    def observed_rmtree(path: Any, *args: Any, **kwargs: Any):
        cleanup_observations.append(
            {
                "entrants": gate.snapshot().entrants,
                "job_dir_exists": Path(path).exists(),
            }
        )
        return original_rmtree(path, *args, **kwargs)

    class UnreadUpload:
        filename = "constructor-failure.wav"

        async def read(self, _size: int) -> bytes:
            raise AssertionError("constructor failure must precede body read")

    async def exercise() -> dict[str, Any]:
        error_status = None
        try:
            await endpoint(file=UnreadUpload())
        except Exception as exc:
            error_status = getattr(exc, "status_code", None)
        return {
            "error_status": error_status,
            "after": {
                "gate": gate.snapshot().to_dict(),
                "job_dirs": sorted(path.name for path in root.iterdir()),
            },
        }

    Path.open = fail_staging_open
    jobs_module.shutil.rmtree = observed_rmtree
    try:
        result = asyncio.run(exercise())
        result["open_observations"] = open_observations
        result["cleanup_observations"] = cleanup_observations
    finally:
        Path.open = original_open
        jobs_module.shutil.rmtree = original_rmtree
        for path in root.iterdir():
            if path.is_dir():
                shutil.rmtree(path)
    return result


def rerun_copy_failure_state(root: Path, marker: Path) -> dict[str, Any]:
    """Pre-admit rerun, enable marker, then fail after writing a real partial copy."""

    runs_dir = root / "runs"
    gate = Phase1CreationGate(marker)
    app, _wrapped = make_batch_app(runs_dir, gate, ProbeRunner())
    source_path = root / "seed.wav"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"real-source-bytes")
    source_job = app.state.manager.create_job_from_file(source_path)
    app.state.manager._queue.join()
    endpoint = next(
        route.endpoint
        for route in app.routes
        if route.path == "/api/jobs/{job_id}/rerun" and "POST" in (route.methods or set())
    )
    original_copyfile = jobs_module.shutil.copyfile
    original_rmtree = jobs_module.shutil.rmtree
    copy_observations: list[dict[str, Any]] = []
    cleanup_observations: list[dict[str, Any]] = []
    before_registry = sorted(app.state.manager._jobs)
    before_queue = app.state.manager._queue.qsize()
    before_job_dirs = sorted(path.name for path in runs_dir.iterdir())

    def partial_copy(source: Any, destination: Any, *args: Any, **kwargs: Any):
        source = Path(source)
        destination = Path(destination)
        with source.open("rb") as source_handle, destination.open("wb") as destination_handle:
            destination_handle.write(source_handle.read(4))
            destination_handle.flush()
        copy_observations.append(
            {
                "entrants": gate.snapshot().entrants,
                "marker_state": gate.snapshot().state,
                "destination_exists": destination.exists(),
                "destination_bytes": destination.read_bytes().hex(),
            }
        )
        raise OSError("prototype partial rerun copy failure")

    def observed_rmtree(path: Any, *args: Any, **kwargs: Any):
        path = Path(path)
        if path.parent == runs_dir:
            cleanup_observations.append(
                {
                    "entrants": gate.snapshot().entrants,
                    "marker_state": gate.snapshot().state,
                    "job_dir_exists": path.exists(),
                }
            )
        return original_rmtree(path, *args, **kwargs)

    class HeldRequest:
        def __init__(self) -> None:
            self.started: asyncio.Event | None = None
            self.release: asyncio.Event | None = None

        async def json(self) -> dict[str, Any]:
            assert self.started is not None and self.release is not None
            self.started.set()
            await self.release.wait()
            return {}

    async def exercise() -> dict[str, Any]:
        request = HeldRequest()
        request.started = asyncio.Event()
        request.release = asyncio.Event()
        task = asyncio.create_task(endpoint(source_job.id, request))
        await request.started.wait()
        held = gate.snapshot().to_dict()
        enable_phase1_creation_quiesce(marker)
        quiesced_held = gate.snapshot().to_dict()
        request.release.set()
        error_status = None
        try:
            await task
        except Exception as exc:
            error_status = getattr(exc, "status_code", None)
        return {
            "error_status": error_status,
            "held_before_enable": held,
            "held_after_enable": quiesced_held,
            "after": {
                "gate": gate.snapshot().to_dict(),
                "registry": sorted(app.state.manager._jobs),
                "queue": app.state.manager._queue.qsize(),
                "job_dirs": sorted(path.name for path in runs_dir.iterdir()),
            },
        }

    jobs_module.shutil.copyfile = partial_copy
    jobs_module.shutil.rmtree = observed_rmtree
    try:
        result = asyncio.run(exercise())
        result.update(
            {
                "before_registry": before_registry,
                "before_queue": before_queue,
                "before_job_dirs": before_job_dirs,
                "copy_observations": copy_observations,
                "cleanup_observations": cleanup_observations,
            }
        )
    finally:
        jobs_module.shutil.copyfile = original_copyfile
        jobs_module.shutil.rmtree = original_rmtree
    return result


def live_bind_failure_state(root: Path, marker: Path) -> dict[str, Any]:
    """Revoke after raw create but before access binding, then inspect undisclosed work."""

    gate = Phase1CreationGate(marker)
    app, wrapped = make_live_app(root, gate)
    local = TestClient(
        wrapped,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )
    remote = TestClient(
        wrapped,
        base_url="https://moss.test",
        client=("192.168.68.20", 50001),
    )

    def pair(device_id: str) -> dict[str, str]:
        grant = local.post("/api/live/pairing-codes")
        grant.raise_for_status()
        paired = remote.post(
            "/api/live/pairings",
            json={
                "device_id": device_id,
                "pairing_payload": grant.json()["pairing_payload"],
            },
        )
        paired.raise_for_status()
        return {"Authorization": f"Bearer {paired.json()['device_token']}"}

    headers = pair("bind-failure-device")
    access = app.state.live_access_registry
    original_bind = access.bind_session
    bind_observations: list[dict[str, Any]] = []

    def revoke_then_bind(principal: Any, session_id: str, now: float):
        bind_observations.append(
            {
                "session_id": session_id,
                "entrants": gate.snapshot().entrants,
                "raw_status": app.state.live_runtime.snapshot(session_id).session.status,
                "active_live": live_active_count(app),
            }
        )
        access.revoke_device(
            LivePeer("127.0.0.1", "http"), principal.device_id, now=now
        )
        return original_bind(principal, session_id, now)

    access.bind_session = revoke_then_bind
    try:
        failed = remote.post("/api/live/sessions", headers=headers)
    finally:
        access.bind_session = original_bind
    leaked_id = bind_observations[0]["session_id"]
    raw_after = app.state.live_runtime.snapshot(leaked_id).to_dict()
    try:
        app.state.live_v2_sessions.get(leaked_id)
        v2_registered = True
    except KeyError:
        v2_registered = False
    after_failure = {
        "status": failed.status_code,
        "gate": gate.snapshot().to_dict(),
        "active_live": live_active_count(app),
        "raw": raw_after,
        "access_bound": leaked_id in access._sessions,
        "v2_registered": v2_registered,
        "helper_lease": leaked_id in app.state.live_helper_failures._sessions,
    }

    retry_headers = pair("bind-retry-device")
    retried = remote.post("/api/live/sessions", headers=retry_headers)
    retry_id = retried.json().get("id") if retried.status_code == 200 else None
    retry_active = live_active_count(app)
    if retry_id is not None:
        remote.post(
            f"/api/live/sessions/{retry_id}/abort",
            headers=retry_headers,
            json={"reason": "prototype retry cleanup"},
        )
    result = {
        "bind_observations": bind_observations,
        "after_failure": after_failure,
        "retry": {
            "status": retried.status_code,
            "session_id": retry_id,
            "active_before_abort": retry_active,
            "active_after_abort": live_active_count(app),
        },
    }
    if raw_after["session"]["status"] == "active":
        asyncio.run(app.state.live_runtime.abort(leaked_id, "prototype leaked-create cleanup"))
    return result


def resume_save_failure_state(root: Path, marker: Path) -> dict[str, Any]:
    """Fail durable resume publication and compare memory, disk, queue, retry, and drain."""

    gate = Phase1CreationGate(marker)
    app, wrapped = make_batch_app(root, gate, ProbeRunner())
    client = TestClient(wrapped)
    created = client.post(
        "/api/jobs", files={"file": ("resume.wav", b"resume-source", "audio/wav")}
    )
    created.raise_for_status()
    job_id = created.json()["id"]
    wait_job(client, job_id)
    job = app.state.manager.get_job(job_id)
    job.status = "failed"
    job.progress = 0.5
    job.error = "prototype prior failure"
    job.resume_attempts = 2
    job.checkpoint_state = "partial"
    app.state.manager._save_job(job)
    before_memory = job.to_dict()
    before_disk = json.loads(job.job_path.read_text(encoding="utf-8"))
    before_queue = app.state.manager._queue.qsize()
    save_observations: list[dict[str, Any]] = []
    original_save = app.state.manager._save_job

    def fail_queued_save(candidate: Any) -> None:
        if candidate.id == job_id and candidate.status == "queued":
            save_observations.append(
                {
                    "entrants": gate.snapshot().entrants,
                    "candidate": candidate.to_dict(),
                    "registry": app.state.manager.get_job(job_id).to_dict(),
                    "disk": json.loads(job.job_path.read_text(encoding="utf-8")),
                }
            )
            raise OSError("prototype resume save failure")
        original_save(candidate)

    app.state.manager._save_job = fail_queued_save
    try:
        failed = client.post(f"/api/jobs/{job_id}/resume")
    finally:
        app.state.manager._save_job = original_save
    after_failure = {
        "status": failed.status_code,
        "gate": gate.snapshot().to_dict(),
        "memory": app.state.manager.get_job(job_id).to_dict(),
        "disk": json.loads(job.job_path.read_text(encoding="utf-8")),
        "queue": app.state.manager._queue.qsize(),
        "activity": app.state.manager.activity_counts(),
    }
    enqueue_observations: list[dict[str, Any]] = []
    original_put = app.state.manager._queue.put

    def fail_enqueue(candidate_id: str) -> None:
        if candidate_id == job_id:
            enqueue_observations.append(
                {
                    "entrants": gate.snapshot().entrants,
                    "registry": app.state.manager.get_job(job_id).to_dict(),
                    "disk": json.loads(job.job_path.read_text(encoding="utf-8")),
                }
            )
            raise OSError("prototype resume enqueue failure")
        original_put(candidate_id)

    app.state.manager._queue.put = fail_enqueue
    try:
        enqueue_failed = client.post(f"/api/jobs/{job_id}/resume")
    finally:
        app.state.manager._queue.put = original_put
    after_enqueue_failure = {
        "status": enqueue_failed.status_code,
        "gate": gate.snapshot().to_dict(),
        "memory": app.state.manager.get_job(job_id).to_dict(),
        "disk": json.loads(job.job_path.read_text(encoding="utf-8")),
        "queue": app.state.manager._queue.qsize(),
        "activity": app.state.manager.activity_counts(),
    }
    retried = client.post(f"/api/jobs/{job_id}/resume")
    retry_body = retried.json()
    try:
        retry_terminal = wait_job(client, job_id)
    except AssertionError:
        retry_terminal = client.get(f"/api/jobs/{job_id}").json()
    return {
        "before": {"memory": before_memory, "disk": before_disk, "queue": before_queue},
        "save_observations": save_observations,
        "after_failure": after_failure,
        "enqueue_observations": enqueue_observations,
        "after_enqueue_failure": after_enqueue_failure,
        "retry": {
            "status": retried.status_code,
            "body": retry_body,
            "terminal": retry_terminal,
            "activity": app.state.manager.activity_counts(),
        },
    }


def concurrent_resume_state(root: Path, marker: Path) -> dict[str, Any]:
    """Force two failed-to-queued transitions while the one production worker is held."""

    gate = Phase1CreationGate(marker)
    runner = ConcurrentResumeRunner()
    app, wrapped = make_batch_app(root, gate, runner)
    setup = TestClient(wrapped)
    first = TestClient(wrapped)
    second = TestClient(wrapped)
    created = setup.post(
        "/api/jobs", files={"file": ("resume-target.wav", b"target", "audio/wav")}
    )
    created.raise_for_status()
    job_id = created.json()["id"]
    wait_job(setup, job_id)
    target = app.state.manager.get_job(job_id)
    target.status = "failed"
    target.progress = 0.5
    target.error = "prototype prior failure"
    target.resume_attempts = 2
    target.checkpoint_state = "partial"
    app.state.manager._save_job(target)

    blocker = setup.post(
        "/api/jobs", files={"file": ("resume-blocker.wav", b"blocker", "audio/wav")}
    )
    blocker.raise_for_status()
    if not runner.blocker_started.wait(timeout=10):
        raise AssertionError("resume blocker did not start")

    original_save = app.state.manager._save_job
    save_barrier = threading.Barrier(2)
    save_serial = threading.Lock()
    save_observations: list[dict[str, Any]] = []

    def interleaved_save(candidate: Any) -> None:
        if candidate.id == job_id and candidate.status == "queued":
            save_observations.append(
                {
                    "entrants": gate.snapshot().entrants,
                    "registry": app.state.manager.get_job(job_id).to_dict(),
                    "candidate": candidate.to_dict(),
                }
            )
            try:
                save_barrier.wait(timeout=1)
            except threading.BrokenBarrierError:
                pass
            with save_serial:
                original_save(candidate)
            return
        original_save(candidate)

    responses: list[dict[str, Any]] = []

    def resume(client: TestClient, label: str) -> None:
        response = client.post(f"/api/jobs/{job_id}/resume")
        responses.append(
            {
                "label": label,
                "status": response.status_code,
                "body": response.json(),
            }
        )

    app.state.manager._save_job = interleaved_save
    try:
        first_thread = threading.Thread(target=resume, args=(first, "first"), daemon=True)
        second_thread = threading.Thread(target=resume, args=(second, "second"), daemon=True)
        first_thread.start()
        second_thread.start()
        first_thread.join(timeout=5)
        second_thread.join(timeout=5)
        if first_thread.is_alive() or second_thread.is_alive():
            raise AssertionError("concurrent resume requests did not return")
    finally:
        app.state.manager._save_job = original_save

    while_held = {
        "responses": sorted(responses, key=lambda item: item["label"]),
        "save_observations": save_observations,
        "gate": gate.snapshot().to_dict(),
        "queue": app.state.manager._queue.qsize(),
        "activity": app.state.manager.activity_counts(),
        "target": app.state.manager.get_job(job_id).to_dict(),
        "runner_calls": runner.calls,
    }
    runner.release_blocker.set()
    app.state.manager._queue.join()
    after_drain = {
        "target": app.state.manager.get_job(job_id).to_dict(),
        "blocker": app.state.manager.get_job(blocker.json()["id"]).to_dict(),
        "queue": app.state.manager._queue.qsize(),
        "activity": app.state.manager.activity_counts(),
        "runner_calls": runner.calls,
    }
    return {"while_held": while_held, "after_drain": after_drain}


def render_save_failure_state(root: Path, marker: Path) -> dict[str, Any]:
    """Fail durable rendering publication before thread start, then retry and drain."""

    gate = Phase1CreationGate(marker)
    app, wrapped = make_batch_app(root, gate, ProbeRunner())
    client = TestClient(wrapped)
    created = client.post(
        "/api/jobs", files={"file": ("render.wav", b"render-source", "audio/wav")}
    )
    created.raise_for_status()
    job_id = created.json()["id"]
    wait_job(client, job_id)
    job = app.state.manager.get_job(job_id)
    before_memory = job.to_dict()
    before_disk = json.loads(job.job_path.read_text(encoding="utf-8"))
    save_observations: list[dict[str, Any]] = []
    captured_threads: list[Any] = []
    starts: list[str] = []
    original_save = app.state.manager._save_job
    original_detect = jobs_module.detect_ffmpeg
    original_probe = jobs_module.probe_video_size
    original_burn = jobs_module.burn_ass_subtitles
    original_threading = jobs_module.threading

    class AvailableFfmpeg:
        available = True

    class HeldThread:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._thread = threading.Thread(*args, **kwargs)

        def start(self) -> None:
            starts.append(self._thread.name)
            captured_threads.append(self)

        def run(self) -> None:
            self._thread.run()

    class ThreadFactory:
        Thread = HeldThread

    def fail_rendering_save(candidate: Any) -> None:
        if candidate.id == job_id and candidate.status == "rendering":
            save_observations.append(
                {
                    "entrants": gate.snapshot().entrants,
                    "candidate": candidate.to_dict(),
                    "registry": app.state.manager.get_job(job_id).to_dict(),
                    "disk": json.loads(job.job_path.read_text(encoding="utf-8")),
                }
            )
            raise OSError("prototype rendering save failure")
        original_save(candidate)

    jobs_module.detect_ffmpeg = lambda: AvailableFfmpeg()
    jobs_module.probe_video_size = lambda _path: (1280, 720)
    jobs_module.burn_ass_subtitles = (
        lambda _input, _ass, output: Path(output).write_bytes(b"prototype-render")
    )
    jobs_module.threading = ThreadFactory()
    app.state.manager._save_job = fail_rendering_save
    try:
        failed = client.post(f"/api/jobs/{job_id}/render", json={})
        after_failure = {
            "status": failed.status_code,
            "gate": gate.snapshot().to_dict(),
            "memory": app.state.manager.get_job(job_id).to_dict(),
            "disk": json.loads(job.job_path.read_text(encoding="utf-8")),
            "starts": list(starts),
            "activity": app.state.manager.activity_counts(),
        }
        app.state.manager._save_job = original_save
        retried = client.post(f"/api/jobs/{job_id}/render", json={})
        retry_active = app.state.manager.activity_counts()
        for held_thread in captured_threads:
            held_thread.run()
        retry_terminal = app.state.manager.get_job(job_id).to_dict()
        retry_activity = app.state.manager.activity_counts()
    finally:
        app.state.manager._save_job = original_save
        jobs_module.detect_ffmpeg = original_detect
        jobs_module.probe_video_size = original_probe
        jobs_module.burn_ass_subtitles = original_burn
        jobs_module.threading = original_threading
    return {
        "before": {"memory": before_memory, "disk": before_disk},
        "save_observations": save_observations,
        "after_failure": after_failure,
        "retry": {
            "status": retried.status_code,
            "active": retry_active,
            "thread_starts": list(starts),
            "terminal": retry_terminal,
            "activity": retry_activity,
        },
    }


def terminal_finalization_state(root: Path, marker: Path) -> dict[str, Any]:
    """Hold the real terminal pass and read the production runtime status surface."""

    scheduler = _ManualTerminalScheduler()
    runtime, _witness = make_terminal_runtime(
        finalizer=terminal_finalizer(), scheduler=scheduler
    )
    session_id = _stop_after_a_meeting(runtime)
    gate = Phase1CreationGate(marker)
    enable_phase1_creation_quiesce(marker)
    app = server.create_app(
        model_path="fake-model",
        runs_dir=root,
        file_mode_runner=ProbeRunner(),
        live_enabled=True,
        live_runtime_factory=lambda: runtime,
        live_auth_state_path=root / "live-auth.json",
        live_server_cert_sha256=LIVE_AUTH_FINGERPRINT,
        live_shared_token="prototype-token",
        live_helper_lease_seconds=30.0,
        phase1_creation_gate=gate,
    )
    client = TestClient(app)
    during_snapshot = runtime.snapshot(session_id).to_dict()["session"]
    during_runtime = client.get("/api/runtime").json()["phase1_creation"]
    pending_before_release = scheduler.pending
    released = scheduler.run_one()
    after_snapshot = runtime.snapshot(session_id).to_dict()["session"]
    after_runtime = client.get("/api/runtime").json()["phase1_creation"]
    return {
        "session_id": session_id,
        "pending_before_release": pending_before_release,
        "released": released,
        "during_snapshot": during_snapshot,
        "during_runtime": during_runtime,
        "after_snapshot": after_snapshot,
        "after_runtime": after_runtime,
    }


def main() -> int:
    states: list[dict[str, Any]] = []
    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="moss-phase1-quiesce-prototype-") as temporary:
        root = Path(temporary)
        os_processes = two_os_process_state(
            root / "os-process-runs", root / "os-process-state" / "marker"
        )
        open_zero = {
            "state": "open",
            "entrants": 0,
            "active_jobs": 0,
            "queued_jobs": 0,
            "active_live_sessions": 0,
        }
        quiesced_zero = {**open_zero, "state": "quiesced"}
        checks["two_real_os_processes_converge"] = (
            len(
                {
                    os_processes["parent_pid"],
                    os_processes["first_initial"]["pid"],
                    os_processes["second_initial"]["pid"],
                    os_processes["replacement_initial"]["pid"],
                }
            )
            == 4
            and os_processes["first_initial"]["runtime"] == open_zero
            and os_processes["second_initial"]["runtime"] == open_zero
            and os_processes["second_quiesced"]["runtime"] == quiesced_zero
            and os_processes["replacement_initial"]["runtime"] == quiesced_zero
            and os_processes["first_reopened"]["runtime"] == open_zero
            and os_processes["replacement_reopened"]["runtime"] == open_zero
            and os_processes["second_exitcode"] == 0
        )
        checks["os_process_entrants_are_local_and_visible"] = (
            os_processes["first_held"]["runtime"]["entrants"] == 1
            and os_processes["second_while_first_held"]["runtime"]["entrants"] == 0
            and os_processes["first_quiesced"]["runtime"]["entrants"] == 1
            and os_processes["first_released"]["runtime"] == quiesced_zero
            and os_processes["replacement_held"]["runtime"]["entrants"] == 1
            and os_processes["replacement_released"]["runtime"] == open_zero
        )
        emit(states, "two_real_os_processes", **os_processes)

        marker = root / "host-state" / "phase1-creation-quiesced"
        batch_gate = Phase1CreationGate(marker)
        live_gate = Phase1CreationGate(marker)
        runner = ProbeRunner()
        batch_app, batch_wrapped = make_batch_app(root / "batch-runs", batch_gate, runner)
        live_app, live_wrapped = make_live_app(root / "live-runs", live_gate)

        constructor_failure = constructor_failure_state(
            root / "constructor-failure-runs",
            root / "constructor-failure-state" / "marker",
        )
        checks["constructor_failure_visible_before_return"] = (
            constructor_failure["error_status"] == 400
            and constructor_failure["open_observations"]
            == [{"entrants": 1, "job_dir_exists": True, "staging_exists": False}]
        )
        checks["constructor_failure_cleanup_ordered"] = (
            constructor_failure["cleanup_observations"]
            == [{"entrants": 1, "job_dir_exists": True}]
            and constructor_failure["after"]["gate"]["entrants"] == 0
            and constructor_failure["after"]["job_dirs"] == []
        )
        emit(states, "constructor_failure", **constructor_failure)

        rerun_failure = rerun_copy_failure_state(
            root / "rerun-failure", root / "rerun-failure-state" / "marker"
        )
        checks["preadmitted_rerun_failure_visible"] = (
            rerun_failure["held_before_enable"] == {"state": "open", "entrants": 1}
            and rerun_failure["held_after_enable"]
            == {"state": "quiesced", "entrants": 1}
            and rerun_failure["error_status"] == 400
            and rerun_failure["copy_observations"]
            == [
                {
                    "entrants": 1,
                    "marker_state": "quiesced",
                    "destination_exists": True,
                    "destination_bytes": b"real".hex(),
                }
            ]
        )
        checks["preadmitted_rerun_failure_cleanup_ordered"] = (
            rerun_failure["cleanup_observations"]
            == [
                {
                    "entrants": 1,
                    "marker_state": "quiesced",
                    "job_dir_exists": True,
                }
            ]
            and rerun_failure["after"]["gate"] == {"state": "quiesced", "entrants": 0}
            and rerun_failure["after"]["registry"] == rerun_failure["before_registry"]
            and rerun_failure["after"]["queue"] == rerun_failure["before_queue"]
            and rerun_failure["after"]["job_dirs"] == rerun_failure["before_job_dirs"]
        )
        emit(states, "preadmitted_rerun_copy_failure", **rerun_failure)

        live_bind_failure = live_bind_failure_state(
            root / "live-bind-failure", root / "live-bind-failure-state" / "marker"
        )
        checks["live_bind_failure_aborts_before_admission_closes"] = (
            live_bind_failure["bind_observations"][0]["entrants"] == 1
            and live_bind_failure["bind_observations"][0]["raw_status"] == "active"
            and live_bind_failure["after_failure"]["status"] == 403
            and live_bind_failure["after_failure"]["gate"]
            == {"state": "open", "entrants": 0}
            and live_bind_failure["after_failure"]["active_live"] == 0
            and live_bind_failure["after_failure"]["raw"]["session"]["status"] != "active"
            and not live_bind_failure["after_failure"]["access_bound"]
            and not live_bind_failure["after_failure"]["v2_registered"]
            and not live_bind_failure["after_failure"]["helper_lease"]
        )
        checks["live_bind_failure_retry_drains"] = (
            live_bind_failure["retry"]["status"] == 200
            and live_bind_failure["retry"]["active_before_abort"] == 1
            and live_bind_failure["retry"]["active_after_abort"] == 0
        )
        emit(states, "live_bind_failure", **live_bind_failure)

        resume_failure = resume_save_failure_state(
            root / "resume-save-failure", root / "resume-save-failure-state" / "marker"
        )
        checks["resume_save_failure_restores_exact_truth"] = (
            resume_failure["save_observations"][0]["entrants"] == 1
            and resume_failure["after_failure"]["status"] == 400
            and resume_failure["after_failure"]["gate"]
            == {"state": "open", "entrants": 0}
            and resume_failure["after_failure"]["memory"]
            == resume_failure["before"]["memory"]
            and resume_failure["after_failure"]["disk"] == resume_failure["before"]["disk"]
            and resume_failure["after_failure"]["queue"] == resume_failure["before"]["queue"]
            and resume_failure["after_failure"]["activity"] == {"queued": 0, "active": 0}
        )
        checks["resume_enqueue_failure_restores_exact_truth"] = (
            resume_failure["enqueue_observations"][0]["entrants"] == 1
            and resume_failure["enqueue_observations"][0]["registry"]["status"]
            == "queued"
            and resume_failure["after_enqueue_failure"]["status"] == 400
            and resume_failure["after_enqueue_failure"]["gate"]
            == {"state": "open", "entrants": 0}
            and resume_failure["after_enqueue_failure"]["memory"]
            == resume_failure["before"]["memory"]
            and resume_failure["after_enqueue_failure"]["disk"]
            == resume_failure["before"]["disk"]
            and resume_failure["after_enqueue_failure"]["queue"]
            == resume_failure["before"]["queue"]
            and resume_failure["after_enqueue_failure"]["activity"]
            == {"queued": 0, "active": 0}
        )
        checks["resume_after_failure_retries_and_drains"] = (
            resume_failure["retry"]["status"] == 200
            and resume_failure["retry"]["body"]["resume_attempts"] == 3
            and resume_failure["retry"]["terminal"]["status"] == "waiting_review"
            and resume_failure["retry"]["activity"] == {"queued": 0, "active": 0}
        )
        emit(states, "resume_save_failure", **resume_failure)

        concurrent_resume = concurrent_resume_state(
            root / "concurrent-resume", root / "concurrent-resume-state" / "marker"
        )
        resume_statuses = sorted(
            response["status"]
            for response in concurrent_resume["while_held"]["responses"]
        )
        checks["concurrent_resume_registers_exactly_once"] = (
            resume_statuses == [200, 409]
            and len(concurrent_resume["while_held"]["save_observations"]) == 1
            and concurrent_resume["while_held"]["gate"]
            == {"state": "open", "entrants": 0}
            and concurrent_resume["while_held"]["queue"] == 1
            and concurrent_resume["while_held"]["activity"]
            == {"queued": 1, "active": 1}
            and concurrent_resume["while_held"]["runner_calls"] == 2
        )
        checks["concurrent_resume_drains_one_execution"] = (
            concurrent_resume["after_drain"]["target"]["status"] == "waiting_review"
            and concurrent_resume["after_drain"]["target"]["resume_attempts"] == 3
            and concurrent_resume["after_drain"]["queue"] == 0
            and concurrent_resume["after_drain"]["activity"]
            == {"queued": 0, "active": 0}
            and concurrent_resume["after_drain"]["runner_calls"] == 3
        )
        emit(states, "concurrent_resume", **concurrent_resume)

        render_failure = render_save_failure_state(
            root / "render-save-failure", root / "render-save-failure-state" / "marker"
        )
        checks["render_save_failure_restores_exact_truth"] = (
            render_failure["save_observations"][0]["entrants"] == 1
            and render_failure["after_failure"]["status"] == 400
            and render_failure["after_failure"]["gate"]
            == {"state": "open", "entrants": 0}
            and render_failure["after_failure"]["memory"]
            == render_failure["before"]["memory"]
            and render_failure["after_failure"]["disk"] == render_failure["before"]["disk"]
            and render_failure["after_failure"]["starts"] == []
            and render_failure["after_failure"]["activity"] == {"queued": 0, "active": 0}
        )
        checks["render_after_failure_retries_and_drains"] = (
            render_failure["retry"]["status"] == 200
            and render_failure["retry"]["active"] == {"queued": 0, "active": 1}
            and len(render_failure["retry"]["thread_starts"]) == 1
            and render_failure["retry"]["terminal"]["status"] == "done"
            and render_failure["retry"]["activity"] == {"queued": 0, "active": 0}
        )
        emit(states, "render_save_failure", **render_failure)

        cancelled = cancelled_upload_state(
            root / "cancelled-upload-runs", root / "cancelled-upload-state" / "marker"
        )
        checks["cancelled_upload_visible_before_cleanup"] = (
            cancelled["held"]["gate"]["entrants"] == 1
            and len(cancelled["held"]["job_dirs"]) == 1
        )
        checks["cancelled_upload_cleanup_ordered"] = (
            cancelled["abort_observations"]
            == [{"entrants": 1, "job_dir_exists": True, "staging_exists": True}]
            and cancelled["after"]["gate"]["entrants"] == 0
            and cancelled["after"]["job_dirs"] == []
        )
        emit(states, "cancelled_upload", **cancelled)

        terminal = terminal_finalization_state(
            root / "terminal-runs", root / "terminal-state" / "marker"
        )
        checks["terminal_finalization_counted"] = (
            terminal["pending_before_release"] == 1
            and terminal["during_snapshot"]["status"] == "closed"
            and terminal["during_snapshot"]["finalization_status"] == "running"
            and terminal["during_runtime"]["active_live_sessions"] == 1
        )
        checks["terminal_finalization_drained_after_release"] = (
            terminal["released"]
            and terminal["after_snapshot"]["finalization_status"] == "final"
            and terminal["after_runtime"]["active_live_sessions"] == 0
        )
        emit(states, "held_terminal_finalization", **terminal)

        batch = TestClient(batch_wrapped)
        live_local = TestClient(
            live_wrapped,
            base_url="http://127.0.0.1",
            client=("127.0.0.1", 50000),
        )
        live = TestClient(
            live_wrapped,
            base_url="https://moss.test",
            client=("192.168.68.20", 50001),
        )
        pairing_grant = live_local.post("/api/live/pairing-codes")
        pairing_grant.raise_for_status()
        paired = live.post(
            "/api/live/pairings",
            json={
                "device_id": "prototype-device",
                "pairing_payload": pairing_grant.json()["pairing_payload"],
            },
        )
        paired.raise_for_status()
        live_headers = {"Authorization": f"Bearer {paired.json()['device_token']}"}

        first = batch.post(
            "/api/jobs",
            files={"file": ("first.wav", b"first", "audio/wav")},
        )
        first.raise_for_status()
        first_id = first.json()["id"]
        first_terminal = wait_job(batch, first_id)
        render_seed = batch.post(
            "/api/jobs",
            files={"file": ("render-seed.wav", b"render", "audio/wav")},
        )
        render_seed.raise_for_status()
        render_id = render_seed.json()["id"]
        wait_job(batch, render_id)

        class AvailableFfmpeg:
            available = True

        captured_render_threads: list[Any] = []
        original_detect_ffmpeg = jobs_module.detect_ffmpeg
        original_probe_video_size = jobs_module.probe_video_size
        original_burn_ass_subtitles = jobs_module.burn_ass_subtitles
        original_jobs_threading = jobs_module.threading

        class HeldRenderThread:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self._thread = threading.Thread(*args, **kwargs)

            def start(self) -> None:
                captured_render_threads.append(self)

            def run(self) -> None:
                self._thread.run()

        class RenderThreadFactory:
            Thread = HeldRenderThread

        jobs_module.detect_ffmpeg = lambda: AvailableFfmpeg()
        jobs_module.probe_video_size = lambda _path: (1280, 720)
        jobs_module.burn_ass_subtitles = (
            lambda _input, _ass, output: Path(output).write_bytes(b"prototype-mp4")
        )
        jobs_module.threading = RenderThreadFactory()
        try:
            render_started = batch.post(f"/api/jobs/{render_id}/render", json={})
        finally:
            jobs_module.threading = original_jobs_threading
        checks["preadmitted_render_registered"] = (
            render_started.status_code == 200
            and batch_app.state.manager.get_job(render_id).status == "rendering"
            and len(captured_render_threads) == 1
        )
        created_live = live.post("/api/live/sessions", headers=live_headers)
        created_live.raise_for_status()
        live_id = created_live.json()["id"]
        created_abort_live = live.post("/api/live/sessions", headers=live_headers)
        created_abort_live.raise_for_status()
        abort_live_id = created_abort_live.json()["id"]
        emit(
            states,
            "open_with_existing_work",
            batch_gate=batch_gate.snapshot().to_dict(),
            live_gate=live_gate.snapshot().to_dict(),
            jobs=job_counts(batch_app),
            active_live=live_active_count(live_app),
        )

        original_read = server._read_upload_chunk
        upload_read_started = threading.Event()
        release_upload_read = threading.Event()
        first_read = True

        async def held_read(upload: Any) -> bytes:
            nonlocal first_read
            if first_read:
                first_read = False
                upload_read_started.set()
                await asyncio.to_thread(release_upload_read.wait, 10)
            return await original_read(upload)

        held_result: dict[str, Any] = {}

        def post_held_upload() -> None:
            response = batch.post(
                "/api/jobs",
                files={"file": ("held.wav", b"held", "audio/wav")},
            )
            held_result["status"] = response.status_code
            held_result["payload"] = response.json()

        server._read_upload_chunk = held_read
        try:
            upload_thread = threading.Thread(target=post_held_upload, daemon=True)
            upload_thread.start()
            checks["held_upload_reached_body_wait"] = upload_read_started.wait(timeout=5)
            emit(
                states,
                "preadmitted_upload_held",
                batch_gate=batch_gate.snapshot().to_dict(),
                jobs=job_counts(batch_app),
            )

            enable_phase1_creation_quiesce(marker)
            enable_phase1_creation_quiesce(marker)
            checks["marker_parent_0700"] = marker.parent.stat().st_mode & 0o777 == 0o700
            checks["marker_0600"] = marker.stat().st_mode & 0o777 == 0o600
            batch_runtime = batch.get("/api/runtime").json()["phase1_creation"]
            live_runtime_status = live.get("/api/runtime").json()["phase1_creation"]
            checks["two_process_runtime_status_exact"] = (
                batch_runtime
                == {
                    "state": "quiesced",
                    "entrants": 1,
                    "active_jobs": 1,
                    "queued_jobs": 0,
                    "active_live_sessions": 0,
                }
                and live_runtime_status
                == {
                    "state": "quiesced",
                    "entrants": 0,
                    "active_jobs": 0,
                    "queued_jobs": 0,
                    "active_live_sessions": 2,
                }
            )
            emit(
                states,
                "enabled",
                marker_exists=marker.exists(),
                marker_mode=oct(marker.stat().st_mode & 0o777),
                parent_mode=oct(marker.parent.stat().st_mode & 0o777),
                batch_gate=batch_gate.snapshot().to_dict(),
                live_gate=live_gate.snapshot().to_dict(),
                batch_runtime=batch_runtime,
                live_runtime=live_runtime_status,
            )

            refusal_requests = {
                "job_create": lambda: batch.post(
                    "/api/jobs",
                    files={"file": ("blocked.wav", b"blocked", "audio/wav")},
                ),
                "job_rerun": lambda: batch.post(f"/api/jobs/{first_id}/rerun", json={}),
                "job_resume": lambda: batch.post(f"/api/jobs/{first_id}/resume"),
                "job_render": lambda: batch.post(f"/api/jobs/{first_id}/render", json={}),
                "live_create": lambda: live.post("/api/live/sessions", headers=live_headers),
            }
            refusals: dict[str, Any] = {}
            for name, request in refusal_requests.items():
                response = request()
                payload = response.json()
                refusals[name] = {
                    "status": response.status_code,
                    "code": payload.get("failure", {}).get("code"),
                }
                checks[f"{name}_typed_503"] = refusals[name] == {
                    "status": 503,
                    "code": PHASE1_CREATION_QUIESCED,
                }

            heartbeat = live.post(
                f"/api/live/sessions/{live_id}/heartbeat",
                headers=live_headers,
                json=helper_heartbeat_payload(),
            )
            frame = live.post(
                f"/api/live/sessions/{live_id}/frames",
                headers=live_headers,
                json=frame_payload(0, 2),
            )
            snapshot = live.get(
                f"/api/live/sessions/{live_id}/snapshot",
                headers=live_headers,
            )
            events = live.get(
                f"/api/live/sessions/{live_id}/events?since_seq=-1",
                headers=live_headers,
            )
            download = batch.get(f"/api/jobs/{first_id}/download?kind=transcript")
            checks["existing_heartbeat_continues"] = heartbeat.status_code == 200
            checks["existing_frame_continues"] = frame.status_code == 200
            checks["existing_snapshot_continues"] = snapshot.status_code == 200
            checks["existing_events_continue"] = events.status_code == 200
            checks["existing_download_continues"] = download.status_code == 200

            release_upload_read.set()
            upload_thread.join(timeout=5)
            checks["preadmitted_upload_registered"] = held_result.get("status") == 200
            held_id = str(held_result.get("payload", {}).get("id") or "")
            checks["held_runner_started"] = runner.held_started.wait(timeout=5)
            emit(
                states,
                "preadmitted_upload_registered",
                batch_gate=batch_gate.snapshot().to_dict(),
                held_status=held_result.get("status"),
                held_id=held_id,
                jobs=job_counts(batch_app),
            )

            stopped = live.post(
                f"/api/live/sessions/{live_id}/stop",
                headers=live_headers,
                json={"deadline": 1.0},
            )
            aborted = live.post(
                f"/api/live/sessions/{abort_live_id}/abort",
                headers=live_headers,
                json={"reason": "prototype cutover drain"},
            )
            checks["existing_stop_continues"] = stopped.status_code == 200
            checks["existing_abort_continues"] = aborted.status_code == 200
            for render_thread in captured_render_threads:
                render_thread.run()
            runner.release_held.set()
            held_terminal = wait_job(batch, held_id)
            emit(
                states,
                "drained",
                batch_gate=batch_gate.snapshot().to_dict(),
                live_gate=live_gate.snapshot().to_dict(),
                jobs=job_counts(batch_app),
                active_live=live_active_count(live_app),
                held_terminal=held_terminal["status"],
            )
            checks["drained_exactly_zero"] = (
                batch_gate.snapshot().entrants == 0
                and live_gate.snapshot().entrants == 0
                and job_counts(batch_app)["queued"] == 0
                and job_counts(batch_app)["active"] == 0
                and live_active_count(live_app) == 0
            )
            expected_drained_runtime = {
                "state": "quiesced",
                "entrants": 0,
                "active_jobs": 0,
                "queued_jobs": 0,
                "active_live_sessions": 0,
            }
            checks["drained_runtime_status_exact"] = (
                batch.get("/api/runtime").json()["phase1_creation"]
                == expected_drained_runtime
                and live.get("/api/runtime").json()["phase1_creation"]
                == expected_drained_runtime
            )
        finally:
            server._read_upload_chunk = original_read
            release_upload_read.set()
            runner.release_held.set()
            jobs_module.detect_ffmpeg = original_detect_ffmpeg
            jobs_module.probe_video_size = original_probe_video_size
            jobs_module.burn_ass_subtitles = original_burn_ass_subtitles

        reboot_gate = Phase1CreationGate(marker)
        reboot_runner = ProbeRunner()
        reboot_app, reboot_wrapped = make_batch_app(root / "batch-runs", reboot_gate, reboot_runner)
        reboot = TestClient(reboot_wrapped)
        reboot_refused = reboot.post(
            "/api/jobs",
            files={"file": ("restart.wav", b"restart", "audio/wav")},
        )
        checks["reboot_preserves_quiescence"] = (
            reboot_gate.snapshot().state == "quiesced"
            and reboot_refused.status_code == 503
            and reboot_refused.json()["failure"]["code"] == PHASE1_CREATION_QUIESCED
            and reboot.get("/api/runtime").json()["phase1_creation"]["state"]
            == "quiesced"
        )

        disable_phase1_creation_quiesce(marker)
        disable_phase1_creation_quiesce(marker)
        reopened = reboot.post(
            "/api/jobs",
            files={"file": ("reopened.wav", b"reopened", "audio/wav")},
        )
        checks["disable_reopens"] = reopened.status_code == 200
        if reopened.status_code == 200:
            wait_job(reboot, reopened.json()["id"])

        broken_parent = root / "not-a-directory"
        broken_parent.write_text("file", encoding="utf-8")
        error_gate = Phase1CreationGate(broken_parent / "marker")
        error_app, error_wrapped = make_batch_app(root / "error-runs", error_gate, ProbeRunner())
        error_response = TestClient(error_wrapped).post(
            "/api/jobs",
            files={"file": ("error.wav", b"error", "audio/wav")},
        )
        checks["marker_error_fails_closed"] = (
            error_gate.snapshot().state == "error"
            and error_response.status_code == 503
            and error_response.json()["failure"]["code"]
            == PHASE1_CREATION_GATE_UNAVAILABLE
            and TestClient(error_wrapped).get("/api/runtime").json()["phase1_creation"]["state"]
            == "error"
        )
        emit(
            states,
            "restart_disable_and_error",
            reboot_state_before_disable="quiesced",
            reopened_status=reopened.status_code,
            marker_exists=marker.exists(),
            error_gate=error_gate.snapshot().to_dict(),
            error_status=error_response.status_code,
        )

    verdict = all(checks.values()) and len(checks) == 43
    summary = {
        "schema": "moss.phase1-creation-quiesce-prototype.v1",
        "question": (
            "Can one durable marker plus one counted admission scope quiesce two production "
            "Phase-1 app instances without interrupting accepted work?"
        ),
        "hypothesis": (
            "Marker existence rejects new work; entrants keep pre-admitted work visible until "
            "registration; existing control/read paths drain normally."
        ),
        "falsifier": (
            "Any admitted work after quiesced plus entrants zero, invisible pre-admitted work, "
            "an existing continuation blocked by the gate, terminal work hidden as drained, "
            "cancellation releasing admission before its upload transaction is removed, or a "
            "create/resume/render failure leaving undisclosed or contradictory work after "
            "admission reports zero, or concurrent resume registering more than one execution."
        ),
        "checks": checks,
        "states": states,
        "verdict": "PASS" if verdict else "FAIL",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
