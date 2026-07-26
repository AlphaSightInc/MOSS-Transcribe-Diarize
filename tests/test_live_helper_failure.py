from __future__ import annotations

import asyncio

import pytest

from moss_transcribe_diarize.app.live_lane_contract import LiveLane
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
    failed_lane: str | None = None,
    failure_code: str | None = None,
) -> dict:
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
        "instance_id": "helper-a",
        "sequence": sequence,
        "sent_monotonic_ns": sent_monotonic_ns,
        "helper_version": "0.1.0",
        "state": state,
        "lanes": lanes,
    }


def observe(coordinator, session_id, snapshot):
    return asyncio.run(coordinator.observe(session_id, snapshot))


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
    first_lease = observe(coordinator, "session-a", first)
    duplicate_lease = observe(coordinator, "session-a", duplicate)

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

    leases = [observe(coordinator, "session-a", snapshot) for snapshot in snapshots]

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
    observe(coordinator, "session-a", first)
    observe(coordinator, "session-a", second)
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
    observe(coordinator, "session-a", snapshot)
    coordinator.release("session-a")
    timer.scheduled[0][1].fire()

    assert timer.scheduled[0][1].cancelled
    assert expired == []


class FakeV2Session:
    def __init__(self) -> None:
        self.failed_lanes: list[tuple[LiveLane, str]] = []

    def fail_lane(self, lane: LiveLane, code: str):
        self.failed_lanes.append((lane, code))


class FakeV2Sessions:
    def __init__(self) -> None:
        self.session = FakeV2Session()
        self.expired: list[tuple[str, str]] = []

    def get(self, session_id: str):
        assert session_id == "session-a"
        return self.session

    def expire(self, session_id: str, reason: str):
        self.expired.append((session_id, reason))


class FakeReleaseRegistry:
    def __init__(self) -> None:
        self.released: list[str] = []

    def release(self, session_id: str):
        self.released.append(session_id)


class FakeAccess:
    def __init__(self) -> None:
        self.released: list[str] = []

    def release_session(self, session_id: str):
        self.released.append(session_id)


def test_explicit_failed_lane_requires_stable_non_empty_code():
    with pytest.raises(ValueError, match="failure_code"):
        HelperHeartbeat.from_dict(
            heartbeat_payload(failed_lane="microphone", failure_code=None)
        )
    with pytest.raises(ValueError, match="non-empty"):
        HelperHeartbeat.from_dict(
            heartbeat_payload(failed_lane="microphone", failure_code="")
        )


def test_explicit_failed_lane_calls_fail_lane_once_and_keeps_peer_timer_live():
    presence = HelperPresenceRegistry(monotonic_ns=lambda: 100)
    timer = FakeTimer()
    v2_sessions = FakeV2Sessions()
    coordinator = LiveHelperFailureCoordinator(
        live_helper_lease_seconds=0.4,
        timer=timer,
        v2_sessions=v2_sessions,
    )
    snapshot = presence.observe(
        "session-a",
        HelperHeartbeat.from_dict(
            heartbeat_payload(failed_lane="microphone", failure_code="permission_denied")
        ),
    )

    lease = observe(coordinator, "session-a", snapshot)

    assert lease is not None
    assert len(timer.scheduled) == 1
    assert not timer.scheduled[0][1].cancelled
    assert v2_sessions.expired == []
    assert v2_sessions.session.failed_lanes == [
        (LiveLane.MICROPHONE, "permission_denied")
    ]


def test_helper_lease_expiry_expires_v2_aborts_mono_and_releases_registries_once():
    presence = HelperPresenceRegistry(monotonic_ns=lambda: 100)
    timer = FakeTimer()
    v2_sessions = FakeV2Sessions()
    v2_mixers = FakeReleaseRegistry()
    helper_presence = FakeReleaseRegistry()
    access = FakeAccess()
    aborted: list[tuple[str, str]] = []
    coordinator = LiveHelperFailureCoordinator(
        live_helper_lease_seconds=0.4,
        timer=timer,
        v2_sessions=v2_sessions,
        v2_mixers=v2_mixers,
        helper_presence=helper_presence,
        access=access,
        abort_mono=lambda session_id, reason: aborted.append((session_id, reason)),
    )
    snapshot = presence.observe("session-a", HelperHeartbeat.from_dict(heartbeat_payload()))

    observe(coordinator, "session-a", snapshot)
    timer.scheduled[0][1].fire()
    timer.scheduled[0][1].fire()

    assert v2_sessions.expired == [("session-a", "helper_lease_expired")]
    assert aborted == [("session-a", "helper_lease_expired")]
    assert v2_mixers.released == ["session-a"]
    assert helper_presence.released == ["session-a"]
    assert access.released == ["session-a"]


def test_helper_failed_and_all_lanes_failed_are_terminal_without_renewing_timer():
    for payload, reason in (
        (heartbeat_payload(state="failed"), "helper_failed"),
        (
            heartbeat_payload(
                lane_state="failed",
                failure_code="device_unavailable",
            ),
            "helper_all_lanes_failed",
        ),
    ):
        presence = HelperPresenceRegistry(monotonic_ns=lambda: 100)
        timer = FakeTimer()
        v2_sessions = FakeV2Sessions()
        aborted: list[tuple[str, str]] = []
        coordinator = LiveHelperFailureCoordinator(
            live_helper_lease_seconds=0.4,
            timer=timer,
            v2_sessions=v2_sessions,
            abort_mono=lambda session_id, reason: aborted.append((session_id, reason)),
        )
        snapshot = presence.observe("session-a", HelperHeartbeat.from_dict(payload))

        lease = observe(coordinator, "session-a", snapshot)

        assert lease is None
        assert timer.scheduled == []
        assert v2_sessions.expired == [("session-a", reason)]
        assert aborted == [("session-a", reason)]
