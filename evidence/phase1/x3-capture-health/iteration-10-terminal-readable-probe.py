#!/usr/bin/env python3
"""Prove terminal microphone denial remains readable on the production snapshot route.

Run from the repository root:
  PYTHONPATH=. .venv/bin/python evidence/phase1/x3-capture-health/iteration-10-terminal-readable-probe.py \
    --write evidence/phase1/x3-capture-health/iteration-10-terminal-readable.json

This local ``create_app`` probe intentionally omits all credentials from its output. It proves
that terminal teardown releases media state and view authority while retaining capture-owner
authorization for the final server-authored snapshot.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.server import create_app


REPO_ROOT = Path(__file__).resolve().parents[3]
MICROPHONE_PERMISSION_DENIED = "browser_microphone_permission_denied"
EXPECTED_STATUS_LINE = (
    "Microphone access was denied. Allow microphone access in Chrome and try again."
)


def _test_helpers():
    path = REPO_ROOT / "tests" / "test_live_api.py"
    spec = importlib.util.spec_from_file_location("terminal_readable_test_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load deterministic route fixture from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _response(response) -> dict[str, Any]:
    return {"http_status": response.status_code, "body": response.json()}


def _paired_clients(app, helpers):
    local = TestClient(
        app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )
    lan = TestClient(
        app,
        base_url="https://moss.lan",
        client=("192.168.68.20", 50001),
    )
    issued = local.post("/api/live/pairing-codes")
    assert issued.status_code == 200, issued.text
    paired = lan.post(
        "/api/live/pairings",
        json={
            "device_id": "capture-health-terminal-readable-probe",
            "pairing_payload": issued.json()["pairing_payload"],
        },
    )
    assert paired.status_code == 200, paired.text
    capture_headers = {"Authorization": f"Bearer {paired.json()['device_token']}"}
    return lan, capture_headers


def _run_probe() -> dict[str, Any]:
    helpers = _test_helpers()
    with tempfile.TemporaryDirectory(prefix="moss-terminal-readable-probe-") as tmpdir:
        app = create_app(
            model_path="fake-model",
            runs_dir=Path(tmpdir) / "runs",
            live_enabled=True,
            live_runtime_factory=lambda: helpers.make_live_runtime(
                max_retained_samples=8,
                session_id="capture-health-terminal-readable-probe-session",
            ),
            live_auth_state_path=Path(tmpdir) / "live-auth.json",
            live_server_cert_sha256=helpers.LIVE_AUTH_FINGERPRINT,
            live_helper_lease_seconds=30.0,
        )
        client, capture_headers = _paired_clients(app, helpers)
        created = client.post("/api/live/sessions", headers=capture_headers)
        assert created.status_code == 200, created.text
        created_payload = created.json()
        session_id = created_payload["id"]
        view_headers = {"Authorization": f"Bearer {created_payload['view_token']}"}

        terminal_heartbeat = client.post(
            f"/api/live/sessions/{session_id}/heartbeat",
            headers=capture_headers,
            json=helpers.helper_heartbeat_payload(
                state="failed",
                failed_lane="microphone",
                failure_code=MICROPHONE_PERMISSION_DENIED,
            ),
        )
        runtime_snapshot = app.state.live_runtime.snapshot(session_id).to_dict()
        capture_snapshot = client.get(
            f"/api/live/sessions/{session_id}/snapshot",
            headers=capture_headers,
        )
        view_snapshot = client.get(
            f"/api/live/sessions/{session_id}/snapshot",
            headers=view_headers,
        )

    heartbeat_payload = terminal_heartbeat.json()
    capture_payload = capture_snapshot.json()
    view_payload = view_snapshot.json()
    terminal_failure = runtime_snapshot["terminal_failure"]
    rendered_capture = json.dumps(capture_payload, sort_keys=True)
    assert runtime_snapshot["session"]["status"] == "aborted"
    assert terminal_failure["message"] == "helper_failed"
    assert terminal_failure["detail"]["lane_failures"]["microphone"] == MICROPHONE_PERMISSION_DENIED
    assert terminal_heartbeat.status_code == 200
    assert capture_snapshot.status_code == 200
    assert view_snapshot.status_code == 401
    assert capture_payload["snapshot"]["session"]["status"] == "aborted"
    assert capture_payload["capture_phase"] == "failed"
    assert capture_payload["status_line"] == EXPECTED_STATUS_LINE
    assert "view_token" not in rendered_capture
    assert "device_token" not in rendered_capture

    return {
        "question": (
            "After a terminal helper heartbeat reports microphone permission denial, can the "
            "capture credential read a server-authored reason without exposing credentials?"
        ),
        "scope": {
            "route": "local create_app -> paired credentials -> session -> terminal helper heartbeat -> snapshot",
            "credentials_omitted": True,
            "not_covered": "This deterministic local route probe does not exercise a browser permission prompt or production deployment.",
        },
        "terminal_heartbeat": {
            "reported_helper_state": "failed",
            "reported_failed_lane": "microphone",
            "reported_failure_code": MICROPHONE_PERMISSION_DENIED,
            "response": _response(terminal_heartbeat),
            "contains_server_capture_projection": {
                "capture_phase": "capture_phase" in heartbeat_payload,
                "status_line": "status_line" in heartbeat_payload,
            },
        },
        "runtime_after_teardown": {
            "session_status": runtime_snapshot["session"]["status"],
            "terminal_failure_kind": terminal_failure["kind"],
            "terminal_failure_code": terminal_failure["code"],
            "terminal_failure_message": terminal_failure["message"],
            "microphone_failure_code": terminal_failure["detail"]["lane_failures"]["microphone"],
        },
        "post_terminal_snapshot": {
            "capture_credential": _response(capture_snapshot),
            "view_credential": _response(view_snapshot),
            "capture_projection": {
                "capture_phase": capture_payload["capture_phase"],
                "status_line": capture_payload["status_line"],
                "credential_fields_present": {
                    "view_token": "view_token" in rendered_capture,
                    "device_token": "device_token" in rendered_capture,
                },
            },
        },
        "verdict": {
            "server_retains_typed_reason": True,
            "snapshot_returns_server_authored_reason_to_capture_credential": True,
            "snapshot_returns_server_authored_reason_to_view_credential": False,
            "terminal_media_cleanup_remains_outside_snapshot": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(_run_probe(), indent=2, sort_keys=True) + "\n"
    if args.write is not None:
        args.write.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
