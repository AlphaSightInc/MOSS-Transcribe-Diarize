from __future__ import annotations

import asyncio
import inspect
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .live_helper_presence import HelperPresenceSnapshot
from .live_lane_contract import LiveLane
from .live_v2_session import LiveV2SessionTerminalError


class LiveHelperLeaseConfigError(ValueError):
    pass


class LiveHelperTimerHandle(Protocol):
    def cancel(self) -> None:
        ...


class LiveHelperTimer(Protocol):
    def schedule(
        self,
        deadline_monotonic_ns: int,
        callback: Callable[[], None],
    ) -> LiveHelperTimerHandle:
        ...


class _V2SessionRegistry(Protocol):
    def get(self, session_id: str) -> Any:
        ...

    def expire(self, session_id: str, reason: str) -> Any:
        ...


class _SessionReleaseRegistry(Protocol):
    def release(self, session_id: str) -> Any:
        ...


class _AccessRegistry(Protocol):
    def release_session(self, session_id: str) -> Any:
        ...


@dataclass(frozen=True, slots=True)
class LiveHelperLeaseSnapshot:
    session_id: str
    sequence: int
    generation: int
    deadline_monotonic_ns: int


@dataclass(slots=True)
class _LeaseState:
    sequence: int
    generation: int
    deadline_monotonic_ns: int
    timer: LiveHelperTimerHandle


class AsyncioLiveHelperTimer:
    def __init__(self, *, monotonic_ns: Callable[[], int] | None = None) -> None:
        self._monotonic_ns = monotonic_ns or time.monotonic_ns

    def schedule(
        self,
        deadline_monotonic_ns: int,
        callback: Callable[[], None],
    ) -> LiveHelperTimerHandle:
        loop = asyncio.get_running_loop()
        delay = max(0.0, (deadline_monotonic_ns - self._monotonic_ns()) / 1_000_000_000)
        return loop.call_later(delay, callback)


class LiveHelperFailureCoordinator:
    """Lease coordinator at the capture-authorized heartbeat seam."""

    def __init__(
        self,
        *,
        live_helper_lease_seconds: float,
        timer: LiveHelperTimer | None = None,
        monotonic_ns: Callable[[], int] | None = None,
        on_expire: Callable[[str, int], None] | None = None,
        v2_sessions: _V2SessionRegistry | None = None,
        v2_mixers: _SessionReleaseRegistry | None = None,
        helper_presence: _SessionReleaseRegistry | None = None,
        access: _AccessRegistry | None = None,
        abort_mono: Callable[[str, str], Any] | None = None,
    ) -> None:
        self._lease_ns = _positive_lease_ns(live_helper_lease_seconds)
        self._timer = timer or AsyncioLiveHelperTimer(monotonic_ns=monotonic_ns)
        self._on_expire = on_expire or (lambda _session_id, _sequence: None)
        self._v2_sessions = v2_sessions
        self._v2_mixers = v2_mixers
        self._helper_presence = helper_presence
        self._access = access
        self._abort_mono = abort_mono
        self._sessions: dict[str, _LeaseState] = {}
        self._terminal_sessions: set[str] = set()
        self._lock = threading.RLock()

    async def observe(
        self,
        session_id: str,
        heartbeat: HelperPresenceSnapshot,
    ) -> LiveHelperLeaseSnapshot | None:
        _session_id(session_id)
        if not isinstance(heartbeat, HelperPresenceSnapshot):
            raise ValueError("heartbeat must be an accepted helper presence snapshot.")
        failed_lanes = _failed_lanes(heartbeat)
        terminal_reason = _terminal_reason(heartbeat, failed_lanes)
        with self._lock:
            if session_id in self._terminal_sessions:
                return None
            current = self._sessions.get(session_id)
            if current is not None and heartbeat.sequence <= current.sequence:
                return None
            if terminal_reason is not None:
                self._mark_terminal_locked(session_id)
                action = "terminal"
                lease_snapshot = None
            else:
                generation = 1 if current is None else current.generation + 1
                deadline = heartbeat.last_seen_monotonic_ns + self._lease_ns
                if current is not None:
                    current.timer.cancel()
                timer = self._timer.schedule(
                    deadline,
                    lambda: self._expire_if_current(session_id, heartbeat.sequence, generation),
                )
                self._sessions[session_id] = _LeaseState(
                    sequence=heartbeat.sequence,
                    generation=generation,
                    deadline_monotonic_ns=deadline,
                    timer=timer,
                )
                action = "observe"
                lease_snapshot = LiveHelperLeaseSnapshot(
                    session_id=session_id,
                    sequence=heartbeat.sequence,
                    generation=generation,
                    deadline_monotonic_ns=deadline,
                )
        if action == "terminal":
            await self._terminal_failure(session_id, terminal_reason or "helper_failed")
            return None
        for lane, code in failed_lanes.items():
            self._fail_lane(session_id, lane, code)
        return lease_snapshot

    def release(self, session_id: str) -> None:
        _session_id(session_id)
        with self._lock:
            current = self._sessions.pop(session_id, None)
            self._terminal_sessions.add(session_id)
        if current is not None:
            current.timer.cancel()

    def _expire_if_current(self, session_id: str, expected_sequence: int, generation: int) -> None:
        should_expire = False
        with self._lock:
            current = self._sessions.get(session_id)
            if (
                current is None
                or current.sequence != expected_sequence
                or current.generation != generation
                or session_id in self._terminal_sessions
            ):
                return
            self._mark_terminal_locked(session_id)
            should_expire = True
        if should_expire:
            self._on_expire(session_id, expected_sequence)
            self._schedule_terminal_failure(session_id, "helper_lease_expired")

    def _mark_terminal_locked(self, session_id: str) -> None:
        current = self._sessions.pop(session_id, None)
        if current is not None:
            current.timer.cancel()
        self._terminal_sessions.add(session_id)

    def _fail_lane(self, session_id: str, lane: LiveLane, code: str) -> None:
        if self._v2_sessions is None:
            return
        self._v2_sessions.get(session_id).fail_lane(lane, code)

    async def _terminal_failure(self, session_id: str, reason: str) -> None:
        self._expire_v2(session_id, reason)
        await self._abort_mono_runtime(session_id, reason)
        self._release_registries(session_id)

    def _schedule_terminal_failure(self, session_id: str, reason: str) -> None:
        result = self._terminal_failure(session_id, reason)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(result)
        else:
            loop.create_task(result)

    def _expire_v2(self, session_id: str, reason: str) -> None:
        if self._v2_sessions is None:
            return
        try:
            self._v2_sessions.expire(session_id, reason)
        except KeyError:
            return
        except LiveV2SessionTerminalError:
            return

    async def _abort_mono_runtime(self, session_id: str, reason: str) -> None:
        if self._abort_mono is None:
            return
        try:
            result = self._abort_mono(session_id, reason)
            if inspect.isawaitable(result):
                await result
        except KeyError:
            return

    def _release_registries(self, session_id: str) -> None:
        if self._v2_mixers is not None:
            self._v2_mixers.release(session_id)
        if self._helper_presence is not None:
            self._helper_presence.release(session_id)
        if self._access is not None:
            self._access.release_session(session_id)


def _failed_lanes(heartbeat: HelperPresenceSnapshot) -> dict[LiveLane, str]:
    failed: dict[LiveLane, str] = {}
    for lane_name, health in heartbeat.lanes.items():
        if health.state != "failed":
            continue
        if not isinstance(health.failure_code, str) or not health.failure_code:
            raise ValueError("failed helper lane requires failure_code.")
        failed[LiveLane(lane_name)] = health.failure_code
    return failed


def _terminal_reason(
    heartbeat: HelperPresenceSnapshot,
    failed_lanes: dict[LiveLane, str],
) -> str | None:
    if heartbeat.state == "failed":
        return "helper_failed"
    if set(failed_lanes) == set(LiveLane):
        return "helper_all_lanes_failed"
    return None


def _positive_lease_ns(value: float) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise LiveHelperLeaseConfigError("live_helper_lease_seconds must be positive.")
    return int(value * 1_000_000_000)


def _session_id(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("session_id must be a non-empty string.")
