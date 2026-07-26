from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest

from moss_transcribe_diarize.app.live_auth import CAPTURE_ACTIONS, VIEW_ACTIONS
from moss_transcribe_diarize.app.live_helper_presence import (
    HELPER_HEALTH_SCHEMA,
    HelperHeartbeat,
    HelperPresenceConflict,
    HelperPresenceRegistry,
)

sys.path.insert(0, str(Path(__file__).parent))
from test_live_api import AuthorizedLiveClient, LIVE_AUTH_FINGERPRINT, make_live_runtime  # noqa: E402


# API coverage rejects view authority heartbeat writes.
FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None


def heartbeat_payload(
    *,
    instance_id: str = "boot-a",
    sequence: int = 0,
    sent_monotonic_ns: int = 10,
    state: str = "capturing",
    lane_state: str = "capturing",
    failure_code: str | None = None,
) -> dict:
    lane = {
        "state": lane_state,
        "device_epoch": 0,
        "dropped_frames": 0,
        "discontinuities": 0,
        "failure_code": failure_code,
    }
    return {
        "schema": HELPER_HEALTH_SCHEMA,
        "instance_id": instance_id,
        "sequence": sequence,
        "sent_monotonic_ns": sent_monotonic_ns,
        "helper_version": "0.1.0",
        "state": state,
        "lanes": {"system": lane, "microphone": lane},
    }


def test_versioned_health_parser_rejects_unknown_missing_or_invalid_fields():
    valid = heartbeat_payload()
    parsed = HelperHeartbeat.from_dict(valid)

    assert parsed.to_dict() == valid

    invalid_payloads = [
        valid | {"extra": True},
        {key: value for key, value in valid.items() if key != "schema"},
        valid | {"schema": "moss-live-helper-health.v2"},
        valid | {"sequence": -1},
        valid | {"state": "unknown"},
        valid | {"lanes": {"system": valid["lanes"]["system"]}},
        valid | {"lanes": valid["lanes"] | {"speaker": valid["lanes"]["system"]}},
        valid
        | {
            "lanes": {
                "system": valid["lanes"]["system"] | {"extra": 1},
                "microphone": valid["lanes"]["microphone"],
            }
        },
        valid
        | {
            "lanes": {
                "system": valid["lanes"]["system"] | {"dropped_frames": True},
                "microphone": valid["lanes"]["microphone"],
            }
        },
    ]
    for payload in invalid_payloads:
        with pytest.raises(ValueError):
            HelperHeartbeat.from_dict(payload)


def test_new_sequence_advances_injected_server_last_seen_and_may_skip_values():
    clock = iter((100, 999, 1_000))
    registry = HelperPresenceRegistry(monotonic_ns=lambda: next(clock))

    first = registry.observe("session-a", HelperHeartbeat.from_dict(heartbeat_payload()))
    duplicate = registry.observe("session-a", HelperHeartbeat.from_dict(heartbeat_payload()))
    advanced = registry.observe(
        "session-a",
        HelperHeartbeat.from_dict(
            heartbeat_payload(
                sequence=2,
                sent_monotonic_ns=30,
                state="degraded",
                lane_state="failed",
                failure_code="permission_denied",
            )
        ),
    )

    assert first.last_seen_monotonic_ns == 100
    assert duplicate == first
    assert duplicate.last_seen_monotonic_ns == 100
    assert advanced.sequence == 2
    assert advanced.last_seen_monotonic_ns == 1_000
    assert advanced.state == "degraded"
    assert advanced.lanes["system"].state == "failed"


def test_regression_changed_duplicate_non_advancing_time_and_instance_switch_fail_closed():
    clock = iter((100, 200, 300, 400, 500))
    registry = HelperPresenceRegistry(monotonic_ns=lambda: next(clock))
    first = registry.observe("session-a", HelperHeartbeat.from_dict(heartbeat_payload()))

    rejected_payloads = [
        heartbeat_payload(sequence=0, sent_monotonic_ns=10, state="failed"),
        heartbeat_payload(sequence=0, sent_monotonic_ns=1),
        heartbeat_payload(instance_id="boot-b", sequence=1, sent_monotonic_ns=20),
        heartbeat_payload(sequence=1, sent_monotonic_ns=10),
    ]
    for payload in rejected_payloads:
        with pytest.raises(HelperPresenceConflict):
            registry.observe("session-a", HelperHeartbeat.from_dict(payload))
        assert registry.snapshot("session-a") == first


def test_release_removes_snapshot_without_policy_side_effects():
    registry = HelperPresenceRegistry(monotonic_ns=lambda: 100)
    registry.observe("session-a", HelperHeartbeat.from_dict(heartbeat_payload(state="failed")))

    registry.release("session-a")

    assert registry.snapshot("session-a") is None


def test_heartbeat_is_capture_only_authority():
    assert "heartbeat" in CAPTURE_ACTIONS
    assert "heartbeat" not in VIEW_ACTIONS


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi is not installed")
def test_helper_heartbeat_route_is_capture_owned_and_visible_in_authorized_snapshot():
    from moss_transcribe_diarize.app.server import create_app

    with tempfile.TemporaryDirectory() as tmpdir:
        app = create_app(
            model_path="fake-model",
            runs_dir=tmpdir,
            live_enabled=True,
            live_runtime_factory=lambda: make_live_runtime(),
            live_auth_state_path=Path(tmpdir) / "live-auth.json",
            live_server_cert_sha256=LIVE_AUTH_FINGERPRINT,
            live_helper_lease_seconds=30.0,
        )
        client = _paired_client(app)
        created = client.post("/api/live/sessions")
        assert created.status_code == 200
        session_id = created.json()["id"]
        view_client = AuthorizedLiveClient(app, created.json()["view_token"])
        clock = iter((100, 999, 1_000))
        app.state.live_helper_presence._monotonic_ns = lambda: next(clock)
        app.state.live_helper_failures._timer._monotonic_ns = lambda: 100

        accepted = client.post(
            f"/api/live/sessions/{session_id}/heartbeat",
            json=heartbeat_payload(instance_id="helper-boot-a"),
        )
        duplicate = client.post(
            f"/api/live/sessions/{session_id}/heartbeat",
            json=heartbeat_payload(instance_id="helper-boot-a"),
        )
        advanced = client.post(
            f"/api/live/sessions/{session_id}/heartbeat",
            json=heartbeat_payload(
                instance_id="helper-boot-a",
                sequence=2,
                sent_monotonic_ns=30,
                state="degraded",
            ),
        )
        view_denied = view_client.post(
            f"/api/live/sessions/{session_id}/heartbeat",
            json=heartbeat_payload(
                instance_id="helper-boot-a",
                sequence=3,
                sent_monotonic_ns=40,
            ),
        )
        snapshot = view_client.get(f"/api/live/sessions/{session_id}/snapshot")

        assert accepted.status_code == 200
        assert duplicate.status_code == 200
        assert advanced.status_code == 200
        assert view_denied.status_code == 403
        assert "view authority" in view_denied.json()["detail"]
        assert accepted.json()["helper_presence"]["last_seen_monotonic_ns"] == 100
        assert duplicate.json()["helper_presence"]["last_seen_monotonic_ns"] == 100
        assert advanced.json()["helper_presence"]["sequence"] == 2
        assert advanced.json()["helper_presence"]["last_seen_monotonic_ns"] == 1_000
        assert snapshot.status_code == 200
        assert snapshot.json()["helper_presence"] == advanced.json()["helper_presence"]


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi is not installed")
@pytest.mark.parametrize("terminal_action", ("stop", "abort", "revoke"))
def test_helper_presence_releases_on_terminal_and_revocation_paths(terminal_action: str):
    from fastapi.testclient import TestClient
    from moss_transcribe_diarize.app.server import create_app

    with tempfile.TemporaryDirectory() as tmpdir:
        app = create_app(
            model_path="fake-model",
            runs_dir=tmpdir,
            live_enabled=True,
            live_runtime_factory=lambda: make_live_runtime(session_id=f"{terminal_action}-session"),
            live_auth_state_path=Path(tmpdir) / "live-auth.json",
            live_server_cert_sha256=LIVE_AUTH_FINGERPRINT,
            live_helper_lease_seconds=30.0,
        )
        client = _paired_client(app)
        local = TestClient(
            app,
            base_url="http://127.0.0.1",
            client=("127.0.0.1", 50000),
        )
        session_id = client.post("/api/live/sessions").json()["id"]
        assert (
            client.post(
                f"/api/live/sessions/{session_id}/heartbeat",
                json=heartbeat_payload(instance_id=f"{terminal_action}-helper"),
            ).status_code
            == 200
        )

        if terminal_action == "stop":
            result = client.post(f"/api/live/sessions/{session_id}/stop", json={"deadline": 0.0})
            assert result.status_code == 200
        elif terminal_action == "abort":
            result = client.post(f"/api/live/sessions/{session_id}/abort", json={"reason": "test"})
            assert result.status_code == 200
        else:
            result = local.delete("/api/live/devices/test-device")
            assert result.status_code == 200
            assert session_id in result.json()["session_ids"]

        assert app.state.live_helper_presence.snapshot(session_id) is None


def _paired_client(app) -> AuthorizedLiveClient:
    from fastapi.testclient import TestClient

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
    assert issued.status_code == 200
    paired = lan.post(
        "/api/live/pairings",
        json={"device_id": "test-device", "pairing_payload": issued.json()["pairing_payload"]},
    )
    assert paired.status_code == 200
    return AuthorizedLiveClient(app, paired.json()["device_token"])
