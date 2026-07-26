from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from test_live_api import (
    LIVE_AUTH_FINGERPRINT,
    helper_heartbeat_payload,
    make_live_runtime,
    v2_frame_payload,
)


@dataclass(frozen=True, slots=True)
class HttpExchangeReport:
    action: str
    status_code: int


@dataclass(frozen=True, slots=True)
class AckReport:
    lane: str
    sequence: int
    start_sample: int
    end_sample: int
    accepted_samples: int
    retained_samples: int


@dataclass(frozen=True, slots=True)
class HelperLaneReport:
    lane: str
    state: str
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class LaneReport:
    lane: str
    next_sequence: int
    accepted_samples: int
    accounted_samples: int
    failed_samples: int
    retained_samples: int
    health: str
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class EventReport:
    seq: int
    kind: str
    snapshot_version: int


@dataclass(frozen=True, slots=True)
class CLIProbeReport:
    action: str
    return_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class LocalIntegrationReplayReport:
    session_created: bool
    transcript_lines: tuple[str, ...]
    helper_state: str
    helper_sequence: int
    helper_lanes: tuple[HelperLaneReport, ...]
    lanes: tuple[LaneReport, ...]
    exact_duplicate_ack: AckReport
    changed_payload_duplicate_ack: AckReport
    replay_counter_unchanged: bool
    system_continuation_ack: AckReport
    view_snapshot_status: str
    events: tuple[EventReport, ...]
    stop_deadline: float
    stop_status_code: int
    terminal_v2_status: str
    terminal_reason: str | None
    authority_redaction_checked: bool
    exchanges: tuple[HttpExchangeReport, ...]
    cli_probes: tuple[CLIProbeReport, ...]


class _BearerJsonClient:
    def __init__(self, app, *, token: str):
        self._client = TestClient(
            app,
            base_url="https://moss.lan",
            client=("192.168.68.20", 50000),
        )
        self._headers = {"Authorization": f"Bearer {token}"}

    def get(self, path: str):
        return self._client.get(path, headers=self._headers)

    def post(self, path: str, payload: dict[str, Any] | None = None):
        return self._client.post(path, json=payload or {}, headers=self._headers)


class _CaptureAdapter:
    def __init__(self, client: _BearerJsonClient, session_id: str):
        self._client = client
        self._session_id = session_id

    def frame(self, payload: dict[str, Any]):
        return self._client.post(f"/api/live/sessions/{self._session_id}/frames", payload)

    def heartbeat(self, payload: dict[str, Any]):
        return self._client.post(f"/api/live/sessions/{self._session_id}/heartbeat", payload)


class _PortalViewAdapter:
    def __init__(self, client: _BearerJsonClient, session_id: str):
        self._client = client
        self._session_id = session_id

    def snapshot(self, *, since_version: int = 0):
        return self._client.get(
            f"/api/live/sessions/{self._session_id}/snapshot?since_version={since_version}"
        )

    def events(self, *, since_seq: int = 0):
        return self._client.get(
            f"/api/live/sessions/{self._session_id}/events?since_seq={since_seq}"
        )

    def stop(self, *, deadline: float):
        return self._client.post(
            f"/api/live/sessions/{self._session_id}/stop",
            {"deadline": deadline},
        )


class LocalIntegrationReplay:
    """Test-only scenario driver whose seam is authenticated JSON/HTTP."""

    def __init__(self, *, tmpdir: str | Path):
        from moss_transcribe_diarize.app.server import create_app

        self._tmpdir = Path(tmpdir)
        self._app = create_app(
            model_path="fake-model",
            runs_dir=tmpdir,
            live_enabled=True,
            live_runtime_factory=lambda: make_live_runtime(
                max_retained_samples=16000,
                speech=(True, True, True),
                session_id="integration-session",
            ),
            live_auth_state_path=Path(tmpdir) / "live-auth.json",
            live_server_cert_sha256=LIVE_AUTH_FINGERPRINT,
            live_helper_lease_seconds=30.0,
        )
        self._exchanges: list[HttpExchangeReport] = []

    def run(self) -> LocalIntegrationReplayReport:
        capture_client, view_client, session_id, secrets = self._pair_and_create()
        capture = _CaptureAdapter(capture_client, session_id)
        portal = _PortalViewAdapter(view_client, session_id)

        self._record("heartbeat:capture", capture.heartbeat(helper_heartbeat_payload(sequence=0)))

        system_zero = v2_frame_payload(0, 4000, lane="system", capture_timestamp_ns=0)
        system_ack = self._json(
            self._record("frame:system:0", capture.frame(system_zero)),
        )["ack"]
        exact_duplicate_ack = self._json(
            self._record("frame:system:0:exact-replay", capture.frame(system_zero)),
        )["ack"]
        changed_duplicate = dict(system_zero)
        changed_duplicate["silent"] = True
        changed_duplicate_ack = self._json(
            self._record("frame:system:0:changed-replay", capture.frame(changed_duplicate)),
        )["ack"]
        microphone_zero = v2_frame_payload(0, 4000, lane="microphone", capture_timestamp_ns=0)
        self._record("frame:microphone:0", capture.frame(microphone_zero))
        self._record(
            "heartbeat:capture:advance",
            capture.heartbeat(helper_heartbeat_payload(sequence=1, sent_monotonic_ns=20)),
        )
        self._record(
            "frame:system:1",
            capture.frame(v2_frame_payload(1, 4000, lane="system", capture_timestamp_ns=250_000_000)),
        )
        self._record(
            "frame:microphone:1",
            capture.frame(v2_frame_payload(1, 4000, lane="microphone", capture_timestamp_ns=250_000_000)),
        )

        transcript_snapshot = self._wait_for_transcript(portal)
        events_response = self._record("view:events", portal.events(since_seq=0))
        events = self._json(events_response)["events"]

        self._record(
            "heartbeat:microphone-failed",
            capture.heartbeat(
                helper_heartbeat_payload(
                    sequence=2,
                    sent_monotonic_ns=30,
                    failed_lane="microphone",
                    failure_code="permission_denied",
                )
            ),
        )
        failed_snapshot_response = self._record("view:snapshot:failed-lane", portal.snapshot())
        failed_snapshot = self._json(failed_snapshot_response)

        continuation = self._json(
            self._record(
                "frame:system:2",
                capture.frame(v2_frame_payload(2, 4000, lane="system", capture_timestamp_ns=500_000_000)),
            )
        )["ack"]

        stop_response = self._record("view:stop", portal.stop(deadline=5.0))
        stopped = self._json(stop_response)
        cli_probes = self._run_cli_probes()
        report = LocalIntegrationReplayReport(
            session_created=True,
            transcript_lines=_transcript_lines(transcript_snapshot),
            helper_state=failed_snapshot["helper_presence"]["state"],
            helper_sequence=failed_snapshot["helper_presence"]["sequence"],
            helper_lanes=_helper_lanes(failed_snapshot["helper_presence"]),
            lanes=_lanes(failed_snapshot["v2_session"]),
            exact_duplicate_ack=_ack(exact_duplicate_ack),
            changed_payload_duplicate_ack=_ack(changed_duplicate_ack),
            replay_counter_unchanged=(
                exact_duplicate_ack == system_ack
                and changed_duplicate_ack == system_ack
                and failed_snapshot["v2_session"]["lanes"]["system"]["next_sequence"] == 2
            ),
            system_continuation_ack=_ack(continuation),
            view_snapshot_status=failed_snapshot["snapshot"]["session"]["status"],
            events=tuple(_event(event) for event in events),
            stop_deadline=5.0,
            stop_status_code=stop_response.status_code,
            terminal_v2_status=stopped["v2_session"]["status"],
            terminal_reason=stopped["v2_session"]["terminal_reason"],
            authority_redaction_checked=False,
            exchanges=tuple(self._exchanges),
            cli_probes=cli_probes,
        )
        return _with_redaction_check(report, secrets)

    def _pair_and_create(self):
        local = TestClient(
            self._app,
            base_url="http://127.0.0.1",
            client=("127.0.0.1", 50000),
        )
        lan = TestClient(
            self._app,
            base_url="https://moss.lan",
            client=("192.168.68.20", 50001),
        )
        issued = local.post("/api/live/pairing-codes")
        if issued.status_code != 200:
            raise AssertionError(f"pairing code failed: {issued.status_code}")
        pairing_payload = issued.json()["pairing_payload"]
        paired = lan.post(
            "/api/live/pairings",
            json={"device_id": "integration-device", "pairing_payload": pairing_payload},
        )
        if paired.status_code != 200:
            raise AssertionError(f"pairing exchange failed: {paired.status_code}")
        device_token = paired.json()["device_token"]
        capture_client = _BearerJsonClient(self._app, token=device_token)
        created = capture_client.post("/api/live/sessions")
        if created.status_code != 200:
            raise AssertionError(f"create session failed: {created.status_code}")
        payload = created.json()
        view_token = payload["view_token"]
        return (
            capture_client,
            _BearerJsonClient(self._app, token=view_token),
            payload["id"],
            (pairing_payload, device_token, view_token, payload["id"]),
        )

    def _wait_for_transcript(self, portal: _PortalViewAdapter) -> dict[str, Any]:
        deadline = time.monotonic() + 2.0
        latest: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            response = self._record("view:snapshot:transcript", portal.snapshot())
            latest = self._json(response)
            session = latest["snapshot"]["session"]
            if session.get("committed"):
                return latest
            time.sleep(0.02)
        raise AssertionError(f"transcript did not commit: {latest}")

    def _record(self, action: str, response):
        if response.status_code >= 400 and action != "view:stop":
            raise AssertionError(f"{action} failed: {response.status_code} {response.text}")
        self._exchanges.append(HttpExchangeReport(action=action, status_code=response.status_code))
        return response

    @staticmethod
    def _json(exchange: HttpExchangeReport | Any) -> dict[str, Any]:
        if isinstance(exchange, HttpExchangeReport):
            raise TypeError("response object required, not report")
        return exchange.json()

    def _run_cli_probes(self) -> tuple[CLIProbeReport, ...]:
        executable = _mtd_capture_executable()
        missing_socket = self._tmpdir / "missing-control.sock"
        env = os.environ.copy()
        env.pop("MOSS_CAPTURE_APP_URL", None)
        env.pop("MOSS_CAPTURE_SKIP_LAUNCH", None)
        env["MOSS_CAPTURE_CONTROL_SOCKET"] = str(missing_socket)

        return (
            _run_cli_probe(executable, (), env=env, action="cli:usage"),
            _run_cli_probe(executable, ("status",), env=env, action="cli:missing-app-socket-status"),
        )


def _ack(payload: dict[str, Any]) -> AckReport:
    return AckReport(
        lane=payload["lane"],
        sequence=payload["sequence"],
        start_sample=payload["start_sample"],
        end_sample=payload["end_sample"],
        accepted_samples=payload["accepted_samples"],
        retained_samples=payload["retained_samples"],
    )


def _event(payload: dict[str, Any]) -> EventReport:
    return EventReport(
        seq=payload["seq"],
        kind=payload["kind"],
        snapshot_version=payload["snapshot_version"],
    )


def _helper_lanes(payload: dict[str, Any]) -> tuple[HelperLaneReport, ...]:
    return tuple(
        HelperLaneReport(
            lane=lane,
            state=lane_payload["state"],
            failure_code=lane_payload["failure_code"],
        )
        for lane, lane_payload in sorted(payload["lanes"].items())
    )


def _lanes(payload: dict[str, Any]) -> tuple[LaneReport, ...]:
    return tuple(
        LaneReport(
            lane=lane,
            next_sequence=lane_payload["next_sequence"],
            accepted_samples=lane_payload["accepted_samples"],
            accounted_samples=lane_payload["accounted_samples"],
            failed_samples=lane_payload["failed_samples"],
            retained_samples=lane_payload["retained_samples"],
            health=lane_payload["health"],
            failure_code=lane_payload["failure_code"],
        )
        for lane, lane_payload in sorted(payload["lanes"].items())
    )


def _transcript_lines(payload: dict[str, Any]) -> tuple[str, ...]:
    session = payload["snapshot"]["session"]
    return tuple(item["transcript"] for item in session.get("committed", ()))


def _with_redaction_check(
    report: LocalIntegrationReplayReport,
    secrets: tuple[str, ...],
) -> LocalIntegrationReplayReport:
    encoded = json.dumps(asdict(report), sort_keys=True)
    for secret in secrets:
        if secret in encoded:
            raise AssertionError("local integration replay report leaked authority.")
    return LocalIntegrationReplayReport(
        session_created=report.session_created,
        transcript_lines=report.transcript_lines,
        helper_state=report.helper_state,
        helper_sequence=report.helper_sequence,
        helper_lanes=report.helper_lanes,
        lanes=report.lanes,
        exact_duplicate_ack=report.exact_duplicate_ack,
        changed_payload_duplicate_ack=report.changed_payload_duplicate_ack,
        replay_counter_unchanged=report.replay_counter_unchanged,
        system_continuation_ack=report.system_continuation_ack,
        view_snapshot_status=report.view_snapshot_status,
        events=report.events,
        stop_deadline=report.stop_deadline,
        stop_status_code=report.stop_status_code,
        terminal_v2_status=report.terminal_v2_status,
        terminal_reason=report.terminal_reason,
        authority_redaction_checked=True,
        exchanges=report.exchanges,
        cli_probes=report.cli_probes,
    )


def _mtd_capture_executable() -> Path:
    root = Path(os.environ.get("MOSS_TARGET_REPO", Path(__file__).resolve().parents[1]))
    executable = root / "macos" / "MOSSCapture" / ".build" / "debug" / "mtd-capture"
    if not executable.exists():
        raise AssertionError(
            "mtd-capture executable missing; run "
            "`swift build --package-path macos/MOSSCapture --product mtd-capture` first"
        )
    return executable


def _run_cli_probe(
    executable: Path,
    arguments: tuple[str, ...],
    *,
    env: dict[str, str],
    action: str,
) -> CLIProbeReport:
    completed = subprocess.run(
        (str(executable), *arguments),
        check=False,
        capture_output=True,
        env=env,
        text=True,
        timeout=5,
    )
    return CLIProbeReport(
        action=action,
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
