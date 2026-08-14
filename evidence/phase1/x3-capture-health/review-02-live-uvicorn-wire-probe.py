#!/usr/bin/env python3
"""Adversarial review probe: the same five scenarios over a real uvicorn socket, not TestClient.

Run from the repository root:
  PYTHONPATH=. .venv/bin/python evidence/phase1/x3-capture-health/review-02-live-uvicorn-wire-probe.py \
    --write evidence/phase1/x3-capture-health/review-02-live-uvicorn-wire.json

``review-01`` proves the wiring through the ASGI stack with ``TestClient``. This one removes the
last doubt that anything about it is an in-process artifact: it starts its *own* uvicorn on a
private-network address with TLS, and drives the routes with ``httpx`` over a real socket. It
starts nothing on, and sends nothing to, any deployed MOSS host.

TLS and a non-loopback peer are not optional decoration -- ``LiveAccessRegistry`` refuses a
pairing exchange from a loopback peer and refuses any non-loopback peer without TLS, so a live
wire proof has to be a real HTTPS listener on a real private address.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import ipaddress
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
HEALTHY_LINE = "Capturing microphone and shared audio."
FINGERPRINT = "ab" * 32
FRAME_SAMPLES = 1_000
SAMPLE_RATE = 16_000
STALE_AFTER_SECONDS = 4 * FRAME_SAMPLES / SAMPLE_RATE
STALL_SECONDS = STALE_AFTER_SECONDS + 0.2
SEQUENCE_REJECT_COUNT = 58
SILENT_FRAME_COUNT = 260
SILENT_FRAME_SAMPLES = 16
SESSION_IDS = (
    "wire-control",
    "wire-missing-system",
    "wire-stale",
    "wire-silent",
    "wire-sequence",
    "wire-server-lane-failed",
    "wire-terminal-denied",
)


def app_factory():
    """Built in the uvicorn child process. Reuses review-01's deterministic runtime."""

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "x3_review_scenarios",
        str(REPO_ROOT / "evidence/phase1/x3-capture-health/review-01-five-scenario-route-probe.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from moss_transcribe_diarize.app.server import create_app

    state_dir = Path(os.environ["X3_WIRE_STATE_DIR"])
    return create_app(
        model_path="fake-model",
        runs_dir=state_dir / "runs",
        live_enabled=True,
        live_runtime_factory=lambda: module._runtime(SESSION_IDS),
        live_auth_state_path=state_dir / "live-auth.json",
        live_server_cert_sha256=FINGERPRINT,
        live_helper_lease_seconds=30.0,
    )


def _private_address() -> str:
    """Any private, non-loopback address this host actually owns."""

    candidates: list[str] = []
    # No DNS is assumed: the UDP-connect trick needs no resolver, and `ifconfig` needs no
    # network at all.
    with contextlib.suppress(OSError):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("192.0.2.1", 9))
        candidates.append(probe.getsockname()[0])
        probe.close()
    with contextlib.suppress(OSError, socket.gaierror):
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.append(info[4][0])
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        rendered = subprocess.run(
            ["ifconfig"], capture_output=True, text=True, check=True
        ).stdout
        for line in rendered.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[0] == "inet":
                candidates.append(fields[1])
    for candidate in candidates:
        with contextlib.suppress(ValueError):
            address = ipaddress.ip_address(candidate)
        if not isinstance(address, ipaddress.IPv4Address):
            continue
        if address.is_private and not address.is_loopback and not address.is_link_local:
            return candidate
    raise RuntimeError(f"no private non-loopback address found among {candidates}")


def _free_port(address: str) -> int:
    with socket.socket() as sock:
        sock.bind((address, 0))
        return sock.getsockname()[1]


def _self_signed(directory: Path, address: str) -> tuple[Path, Path]:
    key = directory / "wire-probe.key"
    cert = directory / "wire-probe.crt"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "1",
            "-subj", "/CN=moss-x3-wire-probe",
            "-addext", f"subjectAltName=IP:{address}",
        ],
        check=True,
        capture_output=True,
    )
    return key, cert


def _frame_body(sequence: int, *, lane: str, silent: bool = False, samples: int = FRAME_SAMPLES) -> dict[str, Any]:
    return {
        "lane": lane,
        "sequence": sequence,
        "capture_timestamp_ns": sequence * samples * 1_000_000_000 // SAMPLE_RATE,
        "device_epoch": 0,
        "silent": silent,
        "discontinuity": False,
        "sample_rate": SAMPLE_RATE,
        "sample_count": samples,
        "pcm_base64": base64.b64encode(b"\0" * samples * 2).decode("ascii"),
    }


def _heartbeat_body(
    *,
    sequence: int,
    state: str = "capturing",
    failed_lane: str | None = None,
    failure_code: str | None = None,
) -> dict[str, Any]:
    from moss_transcribe_diarize.app.live_helper_presence import HELPER_HEALTH_SCHEMA

    lane = {
        "state": "capturing",
        "device_epoch": 0,
        "dropped_frames": 0,
        "discontinuities": 0,
        "failure_code": None,
    }
    lanes = {"system": dict(lane), "microphone": dict(lane)}
    if failed_lane is not None:
        lanes[failed_lane]["state"] = "failed"
        lanes[failed_lane]["failure_code"] = failure_code
    return {
        "schema": HELPER_HEALTH_SCHEMA,
        "instance_id": "helper-wire",
        "sequence": sequence,
        "sent_monotonic_ns": 10 + sequence,
        "helper_version": "0.1.0",
        "state": state,
        "lanes": lanes,
    }


class _Wire:
    def __init__(self, base_url: str, loopback_url: str) -> None:
        import httpx

        self._client = httpx.Client(base_url=base_url, verify=False, timeout=30.0)
        self._loopback = httpx.Client(base_url=loopback_url, verify=False, timeout=30.0)
        issued = self._loopback.post("/api/live/pairing-codes")
        assert issued.status_code == 200, issued.text
        paired = self._client.post(
            "/api/live/pairings",
            json={
                "device_id": "x3-wire-probe",
                "pairing_payload": issued.json()["pairing_payload"],
            },
        )
        assert paired.status_code == 200, paired.text
        self.capture = {"Authorization": f"Bearer {paired.json()['device_token']}"}

    def start(self, *, heartbeat_sequence: int) -> str:
        created = self._client.post("/api/live/sessions", headers=self.capture)
        assert created.status_code == 200, created.text
        session_id = created.json()["id"]
        beat = self._client.post(
            f"/api/live/sessions/{session_id}/heartbeat",
            headers=self.capture,
            json=_heartbeat_body(sequence=heartbeat_sequence),
        )
        assert beat.status_code == 200, beat.text
        return session_id

    def frame(self, session_id: str, **kwargs):
        return self._client.post(
            f"/api/live/sessions/{session_id}/frames",
            headers=self.capture,
            json=_frame_body(**kwargs),
        )

    def heartbeat(self, session_id: str, **kwargs):
        return self._client.post(
            f"/api/live/sessions/{session_id}/heartbeat",
            headers=self.capture,
            json=_heartbeat_body(**kwargs),
        )

    def snapshot(self, session_id: str, *, headers: dict[str, str] | None = None, since_version: int | None = None):
        path = f"/api/live/sessions/{session_id}/snapshot"
        if since_version is not None:
            path += f"?since_version={since_version}"
        return self._client.get(path, headers=self.capture if headers is None else headers)

    def close(self) -> None:
        self._client.close()
        self._loopback.close()


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
    }


def _scenarios(wire: _Wire) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    control = wire.start(heartbeat_sequence=0)
    assert wire.frame(control, lane="microphone", sequence=0).status_code == 200
    assert wire.frame(control, lane="system", sequence=0).status_code == 200
    rows.append(_row("0-healthy-control", wire.snapshot(control), request=f"GET /api/live/sessions/{control}/snapshot"))

    missing = wire.start(heartbeat_sequence=1)
    assert wire.frame(missing, lane="microphone", sequence=0).status_code == 200
    rows.append(
        _row(
            "1-system-lane-never-sent-a-frame",
            wire.snapshot(missing),
            request=f"GET /api/live/sessions/{missing}/snapshot",
        )
    )

    stale = wire.start(heartbeat_sequence=2)
    assert wire.frame(stale, lane="microphone", sequence=0).status_code == 200
    assert wire.frame(stale, lane="system", sequence=0).status_code == 200
    time.sleep(STALL_SECONDS)
    rows.append(
        _row(
            "2-one-frame-each-then-nothing",
            wire.snapshot(stale),
            request=f"GET /api/live/sessions/{stale}/snapshot after a {STALL_SECONDS:.2f}s wall-clock stall",
        )
    )

    silent = wire.start(heartbeat_sequence=3)
    for sequence in range(SILENT_FRAME_COUNT):
        assert wire.frame(
            silent, lane="microphone", sequence=sequence, silent=True, samples=SILENT_FRAME_SAMPLES
        ).status_code == 200
        assert wire.frame(
            silent, lane="system", sequence=sequence, samples=SILENT_FRAME_SAMPLES
        ).status_code == 200
    rows.append(
        _row(
            "3-sustained-silent-microphone-frames",
            wire.snapshot(silent),
            request=f"GET /api/live/sessions/{silent}/snapshot after {SILENT_FRAME_COUNT} silent=true microphone frames",
        )
    )

    wedged = wire.start(heartbeat_sequence=4)
    assert wire.frame(wedged, lane="microphone", sequence=0).status_code == 200
    assert wire.frame(wedged, lane="system", sequence=0).status_code == 200
    rejects = [
        wire.frame(wedged, lane="microphone", sequence=2).status_code
        for _ in range(SEQUENCE_REJECT_COUNT)
    ]
    assert rejects == [409] * SEQUENCE_REJECT_COUNT, rejects
    rows.append(
        _row(
            "4-sequence-gap-58-consecutive-rejects",
            wire.snapshot(wedged),
            request=f"GET /api/live/sessions/{wedged}/snapshot after {SEQUENCE_REJECT_COUNT} out-of-sequence rejects",
        )
    )

    # Scenario 5 over the wire: the server's own lane health goes "failed" when the helper
    # reports that lane failed while the session continues on its peer -- the same
    # v2 lane-health fact the projection previously ignored, reached without in-process access.
    server_failed = wire.start(heartbeat_sequence=5)
    assert wire.frame(server_failed, lane="microphone", sequence=0).status_code == 200
    assert wire.frame(server_failed, lane="system", sequence=0).status_code == 200
    beat = wire.heartbeat(
        server_failed,
        sequence=6,
        failed_lane="system",
        failure_code="browser_surface_audio_missing",
    )
    assert beat.status_code == 200, beat.text
    row = _row(
        "5-server-lane-health-failed",
        wire.snapshot(server_failed),
        request=f"GET /api/live/sessions/{server_failed}/snapshot after the system lane failed server-side",
    )
    body = wire.snapshot(server_failed).json()
    row["v2_system_health"] = body["v2_session"]["lanes"]["system"]["health"]
    rows.append(row)

    denied = wire.start(heartbeat_sequence=7)
    terminal = wire.heartbeat(
        denied,
        sequence=8,
        state="failed",
        failed_lane="microphone",
        failure_code="browser_microphone_permission_denied",
    )
    assert terminal.status_code == 200, terminal.text
    first = wire.snapshot(denied)
    rows.append(
        _row(
            "6-microphone-denied-terminal",
            first,
            request=f"GET /api/live/sessions/{denied}/snapshot after a terminal mic-denied heartbeat",
        )
    )
    version = first.json()["snapshot"]["session"]["version"]
    rows.append(
        _row(
            "7-terminal-repoll-with-since-version",
            wire.snapshot(denied, since_version=version),
            request=f"GET /api/live/sessions/{denied}/snapshot?since_version={version}",
        )
    )
    return rows


def _checks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {row["scenario"]: row for row in rows}
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    check(
        "control-still-reports-healthy",
        by_name["0-healthy-control"]["claims_healthy_recording"],
        "a fusion that never emits the healthy line is not a fix",
    )
    for name in (
        "1-system-lane-never-sent-a-frame",
        "2-one-frame-each-then-nothing",
        "3-sustained-silent-microphone-frames",
        "4-sequence-gap-58-consecutive-rejects",
        "5-server-lane-health-failed",
    ):
        row = by_name[name]
        check(
            f"{name}-drops-healthy-claim",
            row["http_status"] == 200 and not row["claims_healthy_recording"],
            f"http={row['http_status']} phase={row['capture_phase']} line={row['status_line']!r}",
        )
    for name in ("6-microphone-denied-terminal", "7-terminal-repoll-with-since-version"):
        row = by_name[name]
        check(
            f"{name}-yields-a-readable-reason",
            row["http_status"] == 200
            and row["capture_phase"] == "failed"
            and "Microphone access was denied" in (row["status_line"] or ""),
            f"http={row['http_status']} phase={row['capture_phase']} line={row['status_line']!r}",
        )
    return checks


def _run() -> dict[str, Any]:
    import httpx

    address = _private_address()
    port = _free_port(address)
    with tempfile.TemporaryDirectory(prefix="moss-x3-wire-") as raw:
        state_dir = Path(raw)
        key, cert = _self_signed(state_dir, address)
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import importlib.util, uvicorn;"
                    f"spec = importlib.util.spec_from_file_location('x3wire', {str(Path(__file__).resolve())!r});"
                    "module = importlib.util.module_from_spec(spec);"
                    "spec.loader.exec_module(module);"
                    # Bound to every interface on purpose: pairing codes must be minted by a
                    # loopback peer and then exchanged by a non-loopback TLS peer, so one
                    # listener has to answer on both 127.0.0.1 and the private address.
                    f"uvicorn.run(module.app_factory, factory=True, host='0.0.0.0', port={port},"
                    f" ssl_keyfile={str(key)!r}, ssl_certfile={str(cert)!r}, log_level='warning')"
                ),
            ],
            cwd=str(REPO_ROOT),
            env=dict(os.environ, PYTHONPATH=str(REPO_ROOT), X3_WIRE_STATE_DIR=str(state_dir)),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        base_url = f"https://{address}:{port}"
        loopback_url = f"https://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 60.0
            while True:
                if child.poll() is not None:
                    raise RuntimeError(f"uvicorn exited early:\n{child.stdout.read()}")
                try:
                    probe = httpx.get(f"{base_url}/api/live/descriptor", verify=False, timeout=5.0)
                    if probe.status_code in {200, 400, 403}:
                        break
                except Exception:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("uvicorn did not become reachable")
                time.sleep(0.2)
            wire = _Wire(base_url, loopback_url)
            try:
                rows = _scenarios(wire)
            finally:
                wire.close()
        finally:
            child.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                child.wait(timeout=15)
            if child.poll() is None:
                child.kill()

    checks = _checks(rows)
    return {
        "question": (
            "Over a real TLS socket served by our own uvicorn -- no TestClient -- does each PRD "
            "capture scenario stop claiming healthy recording, does a healthy session still claim "
            "it, and does a microphone-denied session stay readable across a since_version poll?"
        ),
        "scope": {
            "transport": f"httpx over TLS to a locally started uvicorn on {address}:{port}",
            "server": "our own process; no request is issued to any deployed MOSS host",
            "not_covered": (
                "no browser, no permission prompt, no deployed host, self-signed certificate with "
                "verification disabled on the client side"
            ),
        },
        "wire_rows": rows,
        "checks": checks,
        "all_checks_passed": all(item["passed"] for item in checks),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()
    result = _run()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write is not None:
        args.write.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    failed = [item for item in result["checks"] if not item["passed"]]
    if failed:
        raise SystemExit(
            "FAILED CHECKS:\n" + "\n".join(f"  {i['check']}: {i['detail']}" for i in failed)
        )


if __name__ == "__main__":
    main()
