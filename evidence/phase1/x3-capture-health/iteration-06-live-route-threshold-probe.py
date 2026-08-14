#!/usr/bin/env python3
"""Measure server-observed capture-health thresholds through the production routes.

Run from the repository root:
  PYTHONPATH=. .venv/bin/python evidence/phase1/x3-capture-health/iteration-06-live-route-threshold-probe.py \
    --write evidence/phase1/x3-capture-health/iteration-06-live-route-thresholds.json

This is a local FastAPI production-route probe.  It does not claim to be a Chrome run; the
Chrome cadence baseline it uses is named in the rendered result.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import math
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.server import create_app


REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_RATE = 16_000
FRAME_SAMPLES = 8_000
FRAME_INTERVAL_NS = FRAME_SAMPLES * 1_000_000_000 // SAMPLE_RATE
STALE_AFTER_NS = 4 * FRAME_INTERVAL_NS
SUSTAINED_SILENT_SAMPLES = 4 * FRAME_SAMPLES
SUSTAINED_REJECTION_COUNT = 4
ROUTE_STALL_SECONDS = 2.05
LANES = ("microphone", "system")
HEALTHY_RECORDING_STATUS_LINE = "Capturing microphone and shared audio."


def _test_helpers():
    """Use only the deterministic local runtime fixture; routes remain production code."""

    path = REPO_ROOT / "tests" / "test_live_api.py"
    spec = importlib.util.spec_from_file_location("capture_health_test_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load local deterministic route fixture from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _app(*, max_retained_samples: int):
    helpers = _test_helpers()
    runtime = helpers.make_live_runtime(
        max_retained_samples=max_retained_samples,
        max_frame_samples=FRAME_SAMPLES,
        max_queue_depth=128,
        session_ids=("capture-health-probe-a", "capture-health-probe-b"),
    )
    runtime.descriptor = replace(runtime.descriptor, frame_samples=FRAME_SAMPLES)
    scratch = tempfile.TemporaryDirectory(prefix="moss-capture-health-probe-")
    app = create_app(
        model_path="fake-model",
        runs_dir=Path(scratch.name) / "runs",
        live_enabled=True,
        live_runtime_factory=lambda: runtime,
        live_auth_state_path=Path(scratch.name) / "live-auth.json",
        live_server_cert_sha256="ab" * 32,
        live_helper_lease_seconds=30.0,
    )
    app.state.capture_health_probe_scratch = scratch
    return app, helpers


class _AuthorizedClient:
    def __init__(self, app, token: str) -> None:
        self._client = TestClient(
            app,
            base_url="https://moss.lan",
            client=("192.168.68.20", 50000),
        )
        self._headers = {"Authorization": f"Bearer {token}"}

    def get(self, path: str):
        return self._client.get(path, headers=self._headers)

    def post(self, path: str, *, json_body: dict | None = None):
        return self._client.post(path, json=json_body, headers=self._headers)


def _paired_client(app, helpers) -> _AuthorizedClient:
    local = TestClient(
        app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )
    issued = local.post("/api/live/pairing-codes")
    assert issued.status_code == 200, issued.text
    lan = TestClient(
        app,
        base_url="https://moss.lan",
        client=("192.168.68.20", 50001),
    )
    paired = lan.post(
        "/api/live/pairings",
        json={"device_id": "capture-health-probe", "pairing_payload": issued.json()["pairing_payload"]},
    )
    assert paired.status_code == 200, paired.text
    return _AuthorizedClient(app, paired.json()["device_token"])


_PCM_BASE64 = base64.b64encode(b"\0" * FRAME_SAMPLES * 2).decode("ascii")


def _frame(sequence: int, *, lane: str, silent: bool = False) -> dict[str, object]:
    return {
        "lane": lane,
        "sequence": sequence,
        "capture_timestamp_ns": sequence * FRAME_INTERVAL_NS,
        "device_epoch": 0,
        "silent": silent,
        "discontinuity": False,
        "sample_rate": SAMPLE_RATE,
        "sample_count": FRAME_SAMPLES,
        "pcm_base64": _PCM_BASE64,
    }


def _start_session(app, helpers):
    client = _paired_client(app, helpers)
    created = client.post("/api/live/sessions")
    assert created.status_code == 200, created.text
    session_id = created.json()["id"]
    heartbeat = client.post(
        f"/api/live/sessions/{session_id}/heartbeat",
        json_body=helpers.helper_heartbeat_payload(),
    )
    assert heartbeat.status_code == 200, heartbeat.text
    return client, session_id


def _post(client, session_id: str, *, lane: str, sequence: int, silent: bool = False):
    return client.post(
        f"/api/live/sessions/{session_id}/frames",
        json_body=_frame(sequence, lane=lane, silent=silent),
    )


def _observation(app, session_id: str, lane: str):
    from moss_transcribe_diarize.app.live_lane_contract import LiveLane

    return app.state.live_capture_observations.snapshot(session_id).lanes[LiveLane(lane)]


def _assert_unhealthy_snapshot(
    response,
    *,
    capture_phase: str,
    status_line: str,
) -> dict[str, object]:
    """Assert the real snapshot no longer makes the healthy recording claim."""

    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert snapshot["capture_phase"] == capture_phase
    assert snapshot["status_line"] == status_line
    healthy_recording_claim = (
        snapshot["capture_phase"] == "recording"
        and snapshot["status_line"] == HEALTHY_RECORDING_STATUS_LINE
    )
    assert not healthy_recording_claim
    return {
        "snapshot_http_status": response.status_code,
        "capture_phase": snapshot["capture_phase"],
        "status_line": snapshot["status_line"],
        "healthy_recording_claim": healthy_recording_claim,
    }


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * fraction) - 1]


def _normal_cadence_and_stall() -> dict[str, object]:
    app, helpers = _app(max_retained_samples=FRAME_SAMPLES * 16)
    client, session_id = _start_session(app, helpers)
    arrivals: dict[str, list[int]] = {lane: [] for lane in LANES}
    for sequence in range(6):
        for lane in LANES:
            response = _post(client, session_id, lane=lane, sequence=sequence)
            assert response.status_code == 200, response.text
            arrival = _observation(app, session_id, lane).last_server_arrival_monotonic_ns
            assert arrival is not None
            arrivals[lane].append(arrival)
        if sequence < 5:
            time.sleep(FRAME_INTERVAL_NS / 1_000_000_000)

    intervals_ms = {
        lane: [round((right - left) / 1_000_000, 3) for left, right in zip(values, values[1:])]
        for lane, values in arrivals.items()
    }
    flattened = [value for values in intervals_ms.values() for value in values]
    assert flattened and max(flattened) * 1_000_000 < STALE_AFTER_NS
    before_stall = time.monotonic_ns()
    time.sleep(ROUTE_STALL_SECONDS)
    stale_age_ns = time.monotonic_ns() - max(values[-1] for values in arrivals.values())
    assert stale_age_ns >= STALE_AFTER_NS
    snapshot = client.get(f"/api/live/sessions/{session_id}/snapshot")
    stale_status = _assert_unhealthy_snapshot(
        snapshot,
        capture_phase="recording",
        status_line="Microphone audio has stopped arriving. Check capture and try again.",
    )
    status = snapshot.json()
    return {
        "v2_lanes_after_cadence": status["v2_session"]["lanes"],
        "arrival_intervals_ms": intervals_ms,
        "combined_interval_ms": {
            "count": len(flattened),
            "p50": _percentile(flattened, 0.50),
            "p95": _percentile(flattened, 0.95),
            "max": max(flattened),
        },
        "stall": {
            "requested_seconds": ROUTE_STALL_SECONDS,
            "server_observed_age_ms": round(stale_age_ns / 1_000_000, 3),
            "stale_after_ms": STALE_AFTER_NS // 1_000_000,
            "pre_stall_monotonic_ns": before_stall,
            "fused_route_status": stale_status,
        },
    }


def _silence_and_sequence_recovery() -> dict[str, object]:
    app, helpers = _app(max_retained_samples=FRAME_SAMPLES * 16)
    client, session_id = _start_session(app, helpers)
    for sequence in range(SUSTAINED_REJECTION_COUNT):
        microphone = _post(client, session_id, lane="microphone", sequence=sequence, silent=True)
        system = _post(client, session_id, lane="system", sequence=sequence)
        assert microphone.status_code == system.status_code == 200
    silent_before_recovery = _observation(app, session_id, "microphone")
    assert silent_before_recovery.consecutive_silent_samples == SUSTAINED_SILENT_SAMPLES
    silent_status = _assert_unhealthy_snapshot(
        client.get(f"/api/live/sessions/{session_id}/snapshot"),
        capture_phase="recording",
        status_line="No microphone sound is being detected.",
    )

    microphone_recovery = _post(
        client,
        session_id,
        lane="microphone",
        sequence=SUSTAINED_REJECTION_COUNT,
    )
    system_recovery = _post(client, session_id, lane="system", sequence=SUSTAINED_REJECTION_COUNT)
    assert microphone_recovery.status_code == system_recovery.status_code == 200
    silent_after_recovery = _observation(app, session_id, "microphone")
    assert silent_after_recovery.consecutive_silent_samples == 0

    sequence_session = client.post("/api/live/sessions")
    assert sequence_session.status_code == 200, sequence_session.text
    sequence_id = sequence_session.json()["id"]
    heartbeat = client.post(
        f"/api/live/sessions/{sequence_id}/heartbeat",
        json_body=helpers.helper_heartbeat_payload(sequence=1),
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert _post(client, sequence_id, lane="microphone", sequence=0).status_code == 200
    assert _post(client, sequence_id, lane="system", sequence=0).status_code == 200
    rejects = [_post(client, sequence_id, lane="microphone", sequence=2) for _ in range(SUSTAINED_REJECTION_COUNT)]
    assert [response.status_code for response in rejects] == [409] * SUSTAINED_REJECTION_COUNT
    sequence_before_recovery = _observation(app, sequence_id, "microphone")
    assert sequence_before_recovery.consecutive_sequence_rejections == SUSTAINED_REJECTION_COUNT
    sequence_status = _assert_unhealthy_snapshot(
        client.get(f"/api/live/sessions/{sequence_id}/snapshot"),
        capture_phase="recording",
        status_line="Microphone audio frames are out of sequence. Reconnecting capture.",
    )
    accepted = _post(client, sequence_id, lane="microphone", sequence=1)
    assert accepted.status_code == 200, accepted.text
    sequence_after_recovery = _observation(app, sequence_id, "microphone")
    assert sequence_after_recovery.consecutive_sequence_rejections == 0
    return {
        "sustained_silence": {
            "accepted_silent_frames": SUSTAINED_REJECTION_COUNT,
            "consecutive_silent_samples_before_recovery": silent_before_recovery.consecutive_silent_samples,
            "consecutive_silent_samples_after_voiced_route_accept": silent_after_recovery.consecutive_silent_samples,
            "fused_route_status": silent_status,
        },
        "sequence_gap": {
            "rejected_route_statuses": [response.status_code for response in rejects],
            "consecutive_rejections_before_recovery": sequence_before_recovery.consecutive_sequence_rejections,
            "consecutive_rejections_after_correct_route_accept": sequence_after_recovery.consecutive_sequence_rejections,
            "fused_route_status": sequence_status,
        },
    }


def _backpressure_recovery() -> dict[str, object]:
    # The mixer seals a microphone frame from its successor. The first system frame makes both
    # lanes active before snapshotting the refusal; the second advances the frontier and releases
    # the retained microphone frame before the successful retry.
    app, helpers = _app(max_retained_samples=FRAME_SAMPLES * 2)
    client, session_id = _start_session(app, helpers)
    assert _post(client, session_id, lane="microphone", sequence=0).status_code == 200
    assert _post(client, session_id, lane="microphone", sequence=1).status_code == 200
    assert _post(client, session_id, lane="system", sequence=0).status_code == 200
    rejects = [_post(client, session_id, lane="microphone", sequence=2) for _ in range(SUSTAINED_REJECTION_COUNT)]
    assert [response.status_code for response in rejects] == [429] * SUSTAINED_REJECTION_COUNT
    before_recovery = _observation(app, session_id, "microphone")
    assert before_recovery.consecutive_backpressure_rejections == SUSTAINED_REJECTION_COUNT
    backpressure_status = _assert_unhealthy_snapshot(
        client.get(f"/api/live/sessions/{session_id}/snapshot"),
        capture_phase="recording",
        status_line="Server is catching up on microphone audio.",
    )
    # The peer lane lets the production mixer account its retained microphone frame.
    assert _post(client, session_id, lane="system", sequence=0).status_code == 200
    assert _post(client, session_id, lane="system", sequence=1).status_code == 200
    accepted = _post(client, session_id, lane="microphone", sequence=2)
    assert accepted.status_code == 200, accepted.text
    after_recovery = _observation(app, session_id, "microphone")
    assert after_recovery.consecutive_backpressure_rejections == 0
    return {
        "rejected_route_statuses": [response.status_code for response in rejects],
        "consecutive_rejections_before_recovery": before_recovery.consecutive_backpressure_rejections,
        "consecutive_rejections_after_peer_drain_and_route_accept": after_recovery.consecutive_backpressure_rejections,
        "fused_route_status": backpressure_status,
    }


def _lane_accounting_statuses() -> dict[str, object]:
    """Exercise server-only lane accounting and health through the snapshot route."""

    app, helpers = _app(max_retained_samples=FRAME_SAMPLES * 16)
    client, session_id = _start_session(app, helpers)
    assert _post(client, session_id, lane="microphone", sequence=0).status_code == 200
    missing_system = client.get(f"/api/live/sessions/{session_id}/snapshot")
    missing_status = _assert_unhealthy_snapshot(
        missing_system,
        capture_phase="awaiting_audio",
        status_line="Waiting for shared audio to arrive.",
    )
    missing_payload = missing_system.json()
    assert missing_payload["v2_session"]["lanes"]["system"]["accepted_samples"] == 0

    assert _post(client, session_id, lane="system", sequence=0).status_code == 200
    from moss_transcribe_diarize.app.live_lane_contract import LiveLane

    app.state.live_v2_sessions.get(session_id).fail_lane(LiveLane.SYSTEM, "server_lane_failure")
    failed_lane = client.get(f"/api/live/sessions/{session_id}/snapshot")
    failed_status = _assert_unhealthy_snapshot(
        failed_lane,
        capture_phase="recording",
        status_line="Shared audio capture failed. The session is continuing.",
    )
    failed_payload = failed_lane.json()
    assert failed_payload["helper_presence"]["lanes"]["system"]["state"] == "capturing"
    assert failed_payload["v2_session"]["lanes"]["system"]["health"] == "failed"
    return {
        "missing_system_audio": missing_status
        | {"v2_system_accepted_samples": missing_payload["v2_session"]["lanes"]["system"]["accepted_samples"]},
        "server_reported_failed_lane": failed_status
        | {
            "helper_system_state": failed_payload["helper_presence"]["lanes"]["system"]["state"],
            "v2_system_health": failed_payload["v2_session"]["lanes"]["system"]["health"],
            "v2_system_failure_code": failed_payload["v2_session"]["lanes"]["system"]["failure_code"],
        },
    }


def _run_probe() -> dict[str, object]:
    normal = _normal_cadence_and_stall()
    recovery = _silence_and_sequence_recovery()
    backpressure = _backpressure_recovery()
    lane_accounting = _lane_accounting_statuses()
    return {
        "question": (
            "What server-observable cadence, stale-age, silence, and rejection recovery facts "
            "should make the capture-health projection leave the healthy recording claim?"
        ),
        "scope": {
            "route": "local create_app -> authenticated v2 frame/heartbeat/snapshot routes -> LiveCaptureObservationRegistry",
            "not_covered": (
                "This uses a deterministic local runtime and TestClient, not a browser. Chrome 151 "
                "worklet cadence is an already-committed baseline below; terminal readability remains x6-owned."
            ),
        },
        "browser_worklet_baseline": {
            "source": "prototypes/browser-capture-feasibility/NOTES.md",
            "frame_samples": FRAME_SAMPLES,
            "sample_rate": SAMPLE_RATE,
            "frame_interval_ms": FRAME_INTERVAL_NS // 1_000_000,
            "visible_arrival_ms": {"p50": 499.7, "p95": 508.1, "max": 512.4},
            "hidden_arrival_ms": {"p50": 499.7, "p95": 506.5, "max": 510.0},
        },
        "local_production_route_measurement": normal,
        "recovery_measurement": recovery,
        "backpressure_recovery_measurement": backpressure,
        "server_fused_route_status_matrix": {
            "missing_system_audio": lane_accounting["missing_system_audio"],
            "stale_post_frame_arrival": normal["stall"]["fused_route_status"],
            "sustained_silence": recovery["sustained_silence"]["fused_route_status"],
            "sustained_sequence_rejections": recovery["sequence_gap"]["fused_route_status"],
            "sustained_backpressure_rejections": backpressure["fused_route_status"],
            "server_reported_failed_lane": lane_accounting["server_reported_failed_lane"],
        },
        "policy_verdict": {
            "stale_after_server_arrival_ms": STALE_AFTER_NS // 1_000_000,
            "sustained_silence_samples": SUSTAINED_SILENT_SAMPLES,
            "sustained_silence_ms_at_descriptor_geometry": SUSTAINED_SILENT_SAMPLES * 1_000 // SAMPLE_RATE,
            "sustained_sequence_rejections": SUSTAINED_REJECTION_COUNT,
            "sustained_backpressure_rejections": SUSTAINED_REJECTION_COUNT,
            "rationale": (
                "Four descriptor frame periods are 2,000 ms: about 3.9 times the measured hidden-tab "
                "p95 of 506.5 ms, while the route probe demonstrates a real post-frame stall beyond that "
                "age and exact recovery after the next accepted frame. Four 8,000-sample silent frames "
                "are the same 2,000 ms. Four consecutive classified rejections avoid treating one retry "
                "as sustained while remaining far below the PRD's measured 58-rejection wedge."
            ),
            "projection_policy": (
                "Applied in project_live_capture_status with descriptor-derived timing and an injectable "
                "server-monotonic clock; the focused route regression and this raw route-status matrix "
                "cover stale, silence, sequence, backpressure, lane accounting, and accepted-frame recovery."
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()
    result = _run_probe()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write is not None:
        args.write.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
