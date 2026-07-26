from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from .live_helper_presence import HelperPresenceSnapshot


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
    ) -> None:
        self._lease_ns = _positive_lease_ns(live_helper_lease_seconds)
        self._timer = timer or AsyncioLiveHelperTimer(monotonic_ns=monotonic_ns)
        self._on_expire = on_expire or (lambda _session_id, _sequence: None)
        self._sessions: dict[str, _LeaseState] = {}
        self._lock = threading.RLock()

    def observe(
        self,
        session_id: str,
        heartbeat: HelperPresenceSnapshot,
    ) -> LiveHelperLeaseSnapshot | None:
        _session_id(session_id)
        if not isinstance(heartbeat, HelperPresenceSnapshot):
            raise ValueError("heartbeat must be an accepted helper presence snapshot.")
        with self._lock:
            current = self._sessions.get(session_id)
            if current is not None and heartbeat.sequence <= current.sequence:
                return None
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
            return LiveHelperLeaseSnapshot(
                session_id=session_id,
                sequence=heartbeat.sequence,
                generation=generation,
                deadline_monotonic_ns=deadline,
            )

    def release(self, session_id: str) -> None:
        _session_id(session_id)
        with self._lock:
            current = self._sessions.pop(session_id, None)
        if current is not None:
            current.timer.cancel()

    def _expire_if_current(self, session_id: str, expected_sequence: int, generation: int) -> None:
        with self._lock:
            current = self._sessions.get(session_id)
            if (
                current is None
                or current.sequence != expected_sequence
                or current.generation != generation
            ):
                return
            self._sessions.pop(session_id, None)
        self._on_expire(session_id, expected_sequence)


def _positive_lease_ns(value: float) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise LiveHelperLeaseConfigError("live_helper_lease_seconds must be positive.")
    return int(value * 1_000_000_000)


def _session_id(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("session_id must be a non-empty string.")
