from __future__ import annotations

import pytest

from moss_transcribe_diarize.app.live_helper_presence import (
    HELPER_HEALTH_SCHEMA,
    HelperHeartbeat,
    HelperPresenceConflict,
    HelperPresenceRegistry,
)


# API coverage rejects view authority heartbeat writes.


def heartbeat_payload(
    *,
    instance_id: str = "boot-a",
    sequence: int = 0,
    sent_monotonic_ns: int = 10,
    state: str = "capturing",
    lane_state: str = "capturing",
) -> dict:
    lane = {
        "state": lane_state,
        "device_epoch": 0,
        "dropped_frames": 0,
        "discontinuities": 0,
        "failure_code": None,
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
            heartbeat_payload(sequence=2, sent_monotonic_ns=30, state="degraded", lane_state="failed")
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
