#!/usr/bin/env python3
"""PROTOTYPE ONLY: falsify the Phase-1 creation-quiesce state model.

One command:

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
      prototypes/phase1-creation-quiesce/probe.py

The probe runs two production ``create_app`` instances through the absorbed admission
semantics. The first recorded verdict preceded production; this retained bench now prevents
the measured state ordering from drifting.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
import time
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
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

from moss_transcribe_diarize.app import server  # noqa: E402
from moss_transcribe_diarize.app import jobs as jobs_module  # noqa: E402
from moss_transcribe_diarize.app.jobs import ACTIVE_STATES  # noqa: E402
from moss_transcribe_diarize.app.model_runner import TranscriptionResult  # noqa: E402
from moss_transcribe_diarize.app.live_service_runtime import (  # noqa: E402
    active_live_session_count,
)
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


def main() -> int:
    states: list[dict[str, Any]] = []
    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="moss-phase1-quiesce-prototype-") as temporary:
        root = Path(temporary)
        marker = root / "host-state" / "phase1-creation-quiesced"
        batch_gate = Phase1CreationGate(marker)
        live_gate = Phase1CreationGate(marker)
        runner = ProbeRunner()
        batch_app, batch_wrapped = make_batch_app(root / "batch-runs", batch_gate, runner)
        live_app, live_wrapped = make_live_app(root / "live-runs", live_gate)

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

    verdict = all(checks.values()) and len(checks) == 24
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
            "or an existing continuation blocked by the gate."
        ),
        "checks": checks,
        "states": states,
        "verdict": "PASS" if verdict else "FAIL",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
