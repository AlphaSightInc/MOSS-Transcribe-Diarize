#!/usr/bin/env python3
"""Adversarial review probe: drive the five PRD capture-health scenarios through the real route.

Run from the repository root:
  PYTHONPATH=. .venv/bin/python evidence/phase1/x3-capture-health/review-01-five-scenario-route-probe.py \
    --write evidence/phase1/x3-capture-health/review-01-five-scenario-route.json

Deliberately self-contained: it imports nothing from ``tests/`` so the *same* file runs
unchanged against ``dev`` (where it reproduces the defect) and against this branch (where it
must pass).  Every row is the body of a real ``GET /api/live/sessions/{id}/snapshot`` issued
over the ASGI stack through the authenticated production route -- not a direct call into
``project_live_capture_status``.

Scenario 0 is a healthy control.  It exists so the other assertions can fail: an implementation
that simply never emitted the healthy line would pass scenarios 1-5 and fail scenario 0.

``--observe-only`` records the same rows without asserting, which is how the pre-branch (dev)
reproduction is captured.
"""

from __future__ import annotations

import argparse
import base64
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.live_endpoint import (
    EndpointPolicy,
    EndpointPolicyConfig,
    SpeechObservation,
)
from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_helper_presence import HELPER_HEALTH_SCHEMA
from moss_transcribe_diarize.app.live_lane_contract import LiveLane
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceRuntime,
    hash_config,
)
from moss_transcribe_diarize.app.live_session import (
    LIVE_SAMPLE_RATE,
    AudioFrame,
    FrozenSpan,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
)
from moss_transcribe_diarize.app.server import create_app


HEALTHY_LINE = "Capturing microphone and shared audio."
FINGERPRINT = "ab" * 32
FRAME_SAMPLES = 1_000
# The projection's own policy is descriptor-derived: four frame periods.
STALE_AFTER_SECONDS = 4 * FRAME_SAMPLES / LIVE_SAMPLE_RATE
STALL_SECONDS = STALE_AFTER_SECONDS + 0.15
SILENT_FRAME_COUNT = 1_000
SILENT_FRAME_SAMPLES = 16
SEQUENCE_REJECT_COUNT = 58


class _SpeechProvider:
    def observe(self, *, frame: AudioFrame, start_sample: int, end_sample: int):
        del frame
        return (
            SpeechObservation(
                start_sample=start_sample, end_sample=end_sample, speech_present=False
            ),
        )


class _Decoder:
    max_samples = 4000

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        del pcm
        return InferenceTranscript(f"[0][S01]decoded[{span.sample_count / LIVE_SAMPLE_RATE:g}]")


class _Identity:
    def prepare(self, *, span, pcm, transcript, base_snapshot):
        del pcm, transcript
        return LiveIdentityPreparation(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            base_snapshot_version=base_snapshot.version,
            proposed_snapshot=LiveIdentitySnapshot(
                version=base_snapshot.version + 1,
                canonical_speakers=base_snapshot.canonical_speakers or ("speaker-0001",),
            ),
            relabeled_transcript="[0][S01]stable[1]",
        )


def _runtime(session_ids: tuple[str, ...]) -> LiveServiceRuntime:
    descriptor = LiveServiceDescriptor(
        source_revision="eda5e69faf0e0251383029295f7e8875a2a1a4f6",
        provider_name="review-fake",
        provider_revision="review-revision",
        provider_manifest_hash=hash_config({"label": "provider"}),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={
                "min_speech_samples": 1,
                "min_silence_samples": 1,
                "hard_cap_samples": 4000,
            },
            identity_config={"max_speakers": 2},
            decoder_config={"max_samples": 4000},
        ),
        bounds=LiveServiceBounds(
            max_frame_samples=LIVE_SAMPLE_RATE,
            max_queue_depth=256,
            max_retained_samples=LIVE_SAMPLE_RATE * 8,
            max_identity_speakers=2,
            max_events=64,
            hard_cap_samples=4000,
        ),
        frame_samples=FRAME_SAMPLES,
    )
    ids = iter(session_ids)
    return LiveServiceRuntime(
        descriptor=descriptor,
        endpoint_policy_factory=lambda: EndpointPolicy(
            EndpointPolicyConfig(
                min_speech_samples=1, min_silence_samples=1, hard_cap_samples=4000
            )
        ),
        speech_provider_factory=_SpeechProvider,
        decoder_factory=_Decoder,
        identity_preparer_factory=_Identity,
        session_id_factory=lambda: next(ids),
    )


class _Harness:
    """One local FastAPI app plus a paired capture credential, over the real routes."""

    def __init__(self, tmpdir: Path, session_ids: tuple[str, ...]) -> None:
        self.app = create_app(
            model_path="fake-model",
            runs_dir=tmpdir / "runs",
            live_enabled=True,
            live_runtime_factory=lambda: _runtime(session_ids),
            live_auth_state_path=tmpdir / "live-auth.json",
            live_server_cert_sha256=FINGERPRINT,
            live_helper_lease_seconds=30.0,
        )
        loopback = TestClient(self.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
        self._lan = TestClient(
            self.app, base_url="https://moss.lan", client=("192.168.68.20", 50001)
        )
        issued = loopback.post("/api/live/pairing-codes")
        assert issued.status_code == 200, issued.text
        paired = self._lan.post(
            "/api/live/pairings",
            json={
                "device_id": "review-probe-device",
                "pairing_payload": issued.json()["pairing_payload"],
            },
        )
        assert paired.status_code == 200, paired.text
        self._capture = {"Authorization": f"Bearer {paired.json()['device_token']}"}

    def start(self, *, heartbeat_sequence: int) -> tuple[str, dict[str, str]]:
        created = self._lan.post("/api/live/sessions", headers=self._capture)
        assert created.status_code == 200, created.text
        payload = created.json()
        self.heartbeat(payload["id"], sequence=heartbeat_sequence)
        return payload["id"], {"Authorization": f"Bearer {payload['view_token']}"}

    def heartbeat(self, session_id: str, **kwargs):
        return self._lan.post(
            f"/api/live/sessions/{session_id}/heartbeat",
            headers=self._capture,
            json=_heartbeat(**kwargs),
        )

    def frame(self, session_id: str, *, lane: str, sequence: int, silent: bool = False, samples: int = FRAME_SAMPLES):
        return self._lan.post(
            f"/api/live/sessions/{session_id}/frames",
            headers=self._capture,
            json={
                "lane": lane,
                "sequence": sequence,
                "capture_timestamp_ns": sequence * samples * 1_000_000_000 // LIVE_SAMPLE_RATE,
                "device_epoch": 0,
                "silent": silent,
                "discontinuity": False,
                "sample_rate": LIVE_SAMPLE_RATE,
                "sample_count": samples,
                "pcm_base64": base64.b64encode(b"\0" * samples * 2).decode("ascii"),
            },
        )

    def snapshot(self, session_id: str, *, headers: dict[str, str] | None = None, since_version: int | None = None):
        path = f"/api/live/sessions/{session_id}/snapshot"
        if since_version is not None:
            path = f"{path}?since_version={since_version}"
        return self._lan.get(path, headers=self._capture if headers is None else headers)


def _heartbeat(
    *,
    sequence: int = 0,
    state: str = "capturing",
    lane_state: str = "capturing",
    failed_lane: str | None = None,
    failure_code: str | None = None,
) -> dict[str, Any]:
    lane = {
        "state": lane_state,
        "device_epoch": 0,
        "dropped_frames": 0,
        "discontinuities": 0,
        "failure_code": failure_code if lane_state == "failed" else None,
    }
    lanes = {"system": dict(lane), "microphone": dict(lane)}
    if failed_lane is not None:
        lanes[failed_lane]["state"] = "failed"
        lanes[failed_lane]["failure_code"] = failure_code
    return {
        "schema": HELPER_HEALTH_SCHEMA,
        "instance_id": "helper-review",
        "sequence": sequence,
        "sent_monotonic_ns": 10 + sequence,
        "helper_version": "0.1.0",
        "state": state,
        "lanes": lanes,
    }


def _row(name: str, response, *, request: str) -> dict[str, Any]:
    body = response.json()
    phase = body.get("capture_phase")
    line = body.get("status_line")
    return {
        "scenario": name,
        "request": request,
        "http_status": response.status_code,
        "capture_phase": phase,
        "status_line": line,
        "claims_healthy_recording": phase == "recording" and line == HEALTHY_LINE,
        "server_reason_readable": isinstance(line, str) and bool(line),
        "response_body": body,
    }


def _scenarios() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="moss-x3-review-") as raw:
        tmpdir = Path(raw)
        harness = _Harness(
            tmpdir,
            (
                "review-control",
                "review-missing-system",
                "review-stale",
                "review-silent",
                "review-sequence",
                "review-server-lane-failed",
                "review-terminal-denied",
            ),
        )

        # Scenario 0 -- healthy control. Both lanes fresh, voiced, no rejections.
        control, _ = harness.start(heartbeat_sequence=0)
        assert harness.frame(control, lane="microphone", sequence=0).status_code == 200
        assert harness.frame(control, lane="system", sequence=0).status_code == 200
        rows.append(
            _row(
                "0-healthy-control",
                harness.snapshot(control),
                request=f"GET /api/live/sessions/{control}/snapshot after one voiced frame on each lane",
            )
        )

        # Scenario 1 -- mic sending, system lane never sent a single frame.
        missing, _ = harness.start(heartbeat_sequence=1)
        assert harness.frame(missing, lane="microphone", sequence=0).status_code == 200
        rows.append(
            _row(
                "1-system-lane-never-sent-a-frame",
                harness.snapshot(missing),
                request=f"GET /api/live/sessions/{missing}/snapshot after 1 microphone frame and 0 system frames",
            )
        )

        # Scenario 2 -- one frame each, then nothing ever again. Real wall-clock stall.
        stale, _ = harness.start(heartbeat_sequence=2)
        assert harness.frame(stale, lane="microphone", sequence=0).status_code == 200
        assert harness.frame(stale, lane="system", sequence=0).status_code == 200
        time.sleep(STALL_SECONDS)
        rows.append(
            _row(
                "2-one-frame-each-then-nothing",
                harness.snapshot(stale),
                request=(
                    f"GET /api/live/sessions/{stale}/snapshot {STALL_SECONDS:.2f}s after the last "
                    f"frame (descriptor stale-after is {STALE_AFTER_SECONDS:.2f}s)"
                ),
            )
        )

        # Scenario 3 -- 1000 frames all silent=True.
        silent, _ = harness.start(heartbeat_sequence=3)
        for sequence in range(SILENT_FRAME_COUNT):
            assert (
                harness.frame(
                    silent,
                    lane="microphone",
                    sequence=sequence,
                    silent=True,
                    samples=SILENT_FRAME_SAMPLES,
                ).status_code
                == 200
            )
            assert (
                harness.frame(
                    silent, lane="system", sequence=sequence, samples=SILENT_FRAME_SAMPLES
                ).status_code
                == 200
            )
        rows.append(
            _row(
                "3-thousand-silent-microphone-frames",
                harness.snapshot(silent),
                request=(
                    f"GET /api/live/sessions/{silent}/snapshot after {SILENT_FRAME_COUNT} "
                    "microphone frames with silent=true"
                ),
            )
        )

        # Scenario 4 -- a lane wedged at a sequence gap with 58 consecutive rejects.
        wedged, _ = harness.start(heartbeat_sequence=4)
        assert harness.frame(wedged, lane="microphone", sequence=0).status_code == 200
        assert harness.frame(wedged, lane="system", sequence=0).status_code == 200
        reject_statuses = [
            harness.frame(wedged, lane="microphone", sequence=2).status_code
            for _ in range(SEQUENCE_REJECT_COUNT)
        ]
        assert reject_statuses == [409] * SEQUENCE_REJECT_COUNT, reject_statuses
        rows.append(
            _row(
                "4-sequence-gap-58-consecutive-rejects",
                harness.snapshot(wedged),
                request=(
                    f"GET /api/live/sessions/{wedged}/snapshot after {SEQUENCE_REJECT_COUNT} "
                    "consecutive out-of-sequence microphone rejects"
                ),
            )
        )

        # Scenario 5 -- the server's own lane health is "failed" in the snapshot it receives.
        failed, _ = harness.start(heartbeat_sequence=5)
        assert harness.frame(failed, lane="microphone", sequence=0).status_code == 200
        assert harness.frame(failed, lane="system", sequence=0).status_code == 200
        harness.app.state.live_v2_sessions.get(failed).fail_lane(
            LiveLane.SYSTEM, "server_lane_failure"
        )
        row = _row(
            "5-server-lane-health-failed",
            harness.snapshot(failed),
            request=f"GET /api/live/sessions/{failed}/snapshot after the server marked the system lane failed",
        )
        row["v2_system_health"] = row["response_body"]["v2_session"]["lanes"]["system"]["health"]
        row["helper_system_state"] = row["response_body"]["helper_presence"]["lanes"]["system"]["state"]
        rows.append(row)

        # Scenario 6 -- microphone permission denied: a terminal helper failure.
        denied, view_headers = harness.start(heartbeat_sequence=6)
        terminal = harness.heartbeat(
            denied,
            sequence=7,
            state="failed",
            failed_lane="microphone",
            failure_code="browser_microphone_permission_denied",
        )
        assert terminal.status_code == 200, terminal.text
        capture_row = _row(
            "6-microphone-denied-terminal-capture-credential",
            harness.snapshot(denied),
            request=f"GET /api/live/sessions/{denied}/snapshot (capture credential) after a terminal mic-denied heartbeat",
        )
        rows.append(capture_row)
        view = harness.snapshot(denied, headers=view_headers)
        rows.append(
            _row(
                "6b-microphone-denied-terminal-view-credential",
                view,
                request=f"GET /api/live/sessions/{denied}/snapshot (view credential) after the same terminal heartbeat",
            )
        )

        # Scenario 7 -- the same terminal session re-polled with since_version, which is what a
        # polling client actually sends on its next tick.
        version = capture_row["response_body"].get("snapshot", {})
        version = version.get("session", {}).get("version") if isinstance(version, dict) else None
        if version is not None:
            rows.append(
                _row(
                    "7-terminal-repoll-with-since-version",
                    harness.snapshot(denied, since_version=version),
                    request=f"GET /api/live/sessions/{denied}/snapshot?since_version={version} (the polling client's next tick)",
                )
            )
    return rows


def _assertions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {row["scenario"]: row for row in rows}
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    control = by_name["0-healthy-control"]
    check(
        "control-still-reports-healthy",
        control["claims_healthy_recording"],
        "a fusion that never emits the healthy line is not a fix; the control must keep it",
    )
    for name in (
        "1-system-lane-never-sent-a-frame",
        "2-one-frame-each-then-nothing",
        "3-thousand-silent-microphone-frames",
        "4-sequence-gap-58-consecutive-rejects",
        "5-server-lane-health-failed",
    ):
        row = by_name[name]
        check(
            f"{name}-drops-healthy-claim",
            row["http_status"] == 200 and not row["claims_healthy_recording"],
            f"http={row['http_status']} phase={row['capture_phase']} line={row['status_line']!r}",
        )
    denied = by_name["6-microphone-denied-terminal-capture-credential"]
    check(
        "microphone-denied-yields-a-readable-reason",
        denied["http_status"] == 200
        and denied["capture_phase"] == "failed"
        and "Microphone access was denied" in (denied["status_line"] or ""),
        f"http={denied['http_status']} phase={denied['capture_phase']} line={denied['status_line']!r}",
    )
    repoll = by_name.get("7-terminal-repoll-with-since-version")
    if repoll is not None:
        check(
            "terminal-reason-survives-a-since-version-repoll",
            repoll["http_status"] == 200
            and repoll["capture_phase"] == "failed"
            and "Microphone access was denied" in (repoll["status_line"] or ""),
            f"http={repoll['http_status']} phase={repoll['capture_phase']} line={repoll['status_line']!r}",
        )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", type=Path)
    parser.add_argument("--observe-only", action="store_true")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    rows = _scenarios()
    checks = _assertions(rows)
    result = {
        "question": (
            "Through the real authenticated /snapshot route, does each of the five PRD capture "
            "scenarios stop claiming healthy recording, does a healthy session still claim it, "
            "and does a microphone-denied session yield a readable server reason?"
        ),
        "label": args.label,
        "scope": {
            "route": "local create_app -> paired capture credential -> HTTP /sessions, /frames, /heartbeat, /snapshot",
            "not_a_unit_call": "no scenario calls project_live_capture_status directly",
            "not_covered": "no browser, no permission prompt, no deployed host, single process",
        },
        "policy_inputs": {
            "descriptor_frame_samples": FRAME_SAMPLES,
            "sample_rate": LIVE_SAMPLE_RATE,
            "stale_after_seconds": STALE_AFTER_SECONDS,
            "wall_clock_stall_seconds": STALL_SECONDS,
            "silent_frames_posted": SILENT_FRAME_COUNT,
            "consecutive_sequence_rejects": SEQUENCE_REJECT_COUNT,
        },
        "route_rows": rows,
        "checks": checks,
        "all_checks_passed": all(item["passed"] for item in checks),
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write is not None:
        args.write.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if not args.observe_only:
        failed = [item for item in checks if not item["passed"]]
        if failed:
            raise SystemExit(
                "FAILED CHECKS:\n"
                + "\n".join(f"  {item['check']}: {item['detail']}" for item in failed)
            )


if __name__ == "__main__":
    main()
