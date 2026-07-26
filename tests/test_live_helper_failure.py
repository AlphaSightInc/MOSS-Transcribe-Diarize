from __future__ import annotations

import pytest

from moss_transcribe_diarize.app.live_helper_failure import (
    LiveHelperFailureCoordinator,
    LiveHelperLeaseConfigError,
)
from moss_transcribe_diarize.app.live_helper_presence import (
    HELPER_HEALTH_SCHEMA,
    HelperHeartbeat,
    HelperPresenceRegistry,
)


class FakeTimerHandle:
    def __init__(self, callback):
        self.callback = callback
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        self.callback()


class FakeTimer:
    def __init__(self) -> None:
        self.scheduled: list[tuple[int, FakeTimerHandle]] = []

    def schedule(self, deadline_monotonic_ns: int, callback) -> FakeTimerHandle:
        handle = FakeTimerHandle(callback)
        self.scheduled.append((deadline_monotonic_ns, handle))
        return handle


def heartbeat_payload(
    *,
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
        "instance_id": "helper-a",
        "sequence": sequence,
        "sent_monotonic_ns": sent_monotonic_ns,
        "helper_version": "0.1.0",
        "state": state,
        "lanes": {"system": lane, "microphone": lane},
    }


def test_live_helper_lease_requires_positive_explicit_value():
    for value in (None, 0, -1, True, "1"):
        with pytest.raises(LiveHelperLeaseConfigError):
            LiveHelperFailureCoordinator(live_helper_lease_seconds=value)


def test_muted_alive_duplicate_heartbeat_does_not_renew_lease():
    presence = HelperPresenceRegistry(monotonic_ns=iter((100, 999)).__next__)
    timer = FakeTimer()
    coordinator = LiveHelperFailureCoordinator(live_helper_lease_seconds=0.4, timer=timer)

    first = presence.observe("session-a", HelperHeartbeat.from_dict(heartbeat_payload()))
    duplicate = presence.observe("session-a", HelperHeartbeat.from_dict(heartbeat_payload()))
    first_lease = coordinator.observe("session-a", first)
    duplicate_lease = coordinator.observe("session-a", duplicate)

    assert first_lease is not None
    assert first_lease.deadline_monotonic_ns == 400_000_100
    assert duplicate_lease is None
    assert len(timer.scheduled) == 1
    assert not timer.scheduled[0][1].cancelled


def test_degraded_and_recovering_health_renew_without_lifecycle_mutation():
    expired: list[tuple[str, int]] = []
    presence = HelperPresenceRegistry(monotonic_ns=iter((100, 200, 300)).__next__)
    timer = FakeTimer()
    coordinator = LiveHelperFailureCoordinator(
        live_helper_lease_seconds=0.4,
        timer=timer,
        on_expire=lambda session_id, sequence: expired.append((session_id, sequence)),
    )

    snapshots = [
        presence.observe("session-a", HelperHeartbeat.from_dict(heartbeat_payload())),
        presence.observe(
            "session-a",
            HelperHeartbeat.from_dict(
                heartbeat_payload(sequence=1, sent_monotonic_ns=20, state="degraded")
            ),
        ),
        presence.observe(
            "session-a",
            HelperHeartbeat.from_dict(
                heartbeat_payload(sequence=2, sent_monotonic_ns=30, state="recovering")
            ),
        ),
    ]

    leases = [coordinator.observe("session-a", snapshot) for snapshot in snapshots]

    assert expired == []
    assert [lease.sequence for lease in leases if lease is not None] == [0, 1, 2]
    assert len(timer.scheduled) == 3
    assert [handle.cancelled for _, handle in timer.scheduled] == [True, True, False]


def test_stale_lease_callback_after_renewal_is_noop():
    expired: list[tuple[str, int]] = []
    presence = HelperPresenceRegistry(monotonic_ns=iter((100, 200)).__next__)
    timer = FakeTimer()
    coordinator = LiveHelperFailureCoordinator(
        live_helper_lease_seconds=0.4,
        timer=timer,
        on_expire=lambda session_id, sequence: expired.append((session_id, sequence)),
    )

    first = presence.observe("session-a", HelperHeartbeat.from_dict(heartbeat_payload()))
    second = presence.observe(
        "session-a",
        HelperHeartbeat.from_dict(heartbeat_payload(sequence=1, sent_monotonic_ns=20)),
    )
    coordinator.observe("session-a", first)
    coordinator.observe("session-a", second)
    timer.scheduled[0][1].fire()
    timer.scheduled[1][1].fire()

    assert timer.scheduled[0][1].cancelled
    assert expired == [("session-a", 1)]


def test_helper_lease_expiry_is_cancelled_by_release():
    expired: list[tuple[str, int]] = []
    presence = HelperPresenceRegistry(monotonic_ns=lambda: 100)
    timer = FakeTimer()
    coordinator = LiveHelperFailureCoordinator(
        live_helper_lease_seconds=0.4,
        timer=timer,
        on_expire=lambda session_id, sequence: expired.append((session_id, sequence)),
    )

    snapshot = presence.observe("session-a", HelperHeartbeat.from_dict(heartbeat_payload()))
    coordinator.observe("session-a", snapshot)
    coordinator.release("session-a")
    timer.scheduled[0][1].fire()

    assert timer.scheduled[0][1].cancelled
    assert expired == []
