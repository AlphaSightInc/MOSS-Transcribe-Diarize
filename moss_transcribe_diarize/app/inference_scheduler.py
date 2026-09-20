"""Bounded Live-priority arbitration at the replaceable decoder seam."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Literal, TypeVar


InferenceKind = Literal["live", "background"]
InferenceOwnerClass = Literal["live", "file", "terminal"]
_T = TypeVar("_T")


class InferenceDispatchCancelled(RuntimeError):
    """Queued background work lost its owning Meeting before decoder dispatch."""


@dataclass(frozen=True, slots=True)
class InferenceDispatchSnapshot:
    running_calls: int
    running_background_calls: int
    waiting_live_calls: int
    waiting_background_calls: int


@dataclass(frozen=True, slots=True)
class InferenceDispatchTiming:
    """Content-free lifecycle of one decoder-window submission."""

    owner_kind: InferenceKind
    owner_key: str
    window_index: int
    accepted_monotonic_ns: int
    wait_started_monotonic_ns: int
    started_monotonic_ns: int | None
    ended_monotonic_ns: int | None


@dataclass(slots=True)
class _Waiter:
    key: str


@dataclass(slots=True)
class _DispatchTimingState:
    owner_kind: InferenceKind
    owner_key: str
    window_index: int
    accepted_monotonic_ns: int
    wait_started_monotonic_ns: int
    started_monotonic_ns: int | None = None
    ended_monotonic_ns: int | None = None


class InferenceDispatchScheduler:
    """Two-slot decoder gate: Live first, at most one background call.

    Calls already running are non-preemptible. File/URL windowing crosses this interface once
    per decoder window, so it yields between windows. Live may consume both slots; background
    may consume only one, leaving one slot available when Live arrives later.
    """

    def __init__(
        self,
        *,
        max_calls: int = 2,
        max_background_calls: int = 1,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        if not isinstance(max_calls, int) or isinstance(max_calls, bool) or max_calls <= 0:
            raise ValueError("max_calls must be a positive integer.")
        if (
            not isinstance(max_background_calls, int)
            or isinstance(max_background_calls, bool)
            or max_background_calls < 0
            or max_background_calls > max_calls
        ):
            raise ValueError("max_background_calls must be between zero and max_calls.")
        self._max_calls = max_calls
        self._max_background_calls = max_background_calls
        self._condition = threading.Condition()
        self._live_waiters: deque[_Waiter] = deque()
        self._background_waiters: deque[_Waiter] = deque()
        self._cancelled_background_keys: set[str] = set()
        self._running_calls = 0
        self._running_background_calls = 0
        self._monotonic_ns = monotonic_ns
        self._owner_window_counts: dict[tuple[InferenceKind, str], int] = {}
        self._owner_classes: dict[tuple[InferenceKind, str], InferenceOwnerClass] = {}
        self._dispatch_timings: list[_DispatchTimingState] = []

    def run_live(
        self,
        key: str,
        call: Callable[[], _T],
        *,
        on_wait: Callable[[], None] | None = None,
        on_start: Callable[[], None] | None = None,
    ) -> _T:
        return self._run(
            "live", key, call, owner_class="live", on_wait=on_wait, on_start=on_start
        )

    def run_background(
        self,
        key: str,
        call: Callable[[], _T],
        *,
        owner_class: Literal["file", "terminal"] = "terminal",
        on_wait: Callable[[], None] | None = None,
        on_start: Callable[[], None] | None = None,
    ) -> _T:
        if owner_class not in {"file", "terminal"}:
            raise ValueError("background inference owner class must be file or terminal.")
        return self._run(
            "background",
            key,
            call,
            owner_class=owner_class,
            on_wait=on_wait,
            on_start=on_start,
        )

    def cancel_background(self, key: str) -> bool:
        if not key:
            raise ValueError("background dispatch key must be non-empty.")
        with self._condition:
            waiting = any(waiter.key == key for waiter in self._background_waiters)
            self._cancelled_background_keys.add(key)
            self._condition.notify_all()
            return waiting

    def snapshot(self) -> InferenceDispatchSnapshot:
        with self._condition:
            return InferenceDispatchSnapshot(
                running_calls=self._running_calls,
                running_background_calls=self._running_background_calls,
                waiting_live_calls=len(self._live_waiters),
                waiting_background_calls=len(self._background_waiters),
            )

    def dispatch_timings(self) -> tuple[InferenceDispatchTiming, ...]:
        with self._condition:
            return tuple(
                InferenceDispatchTiming(
                    owner_kind=timing.owner_kind,
                    owner_key=timing.owner_key,
                    window_index=timing.window_index,
                    accepted_monotonic_ns=timing.accepted_monotonic_ns,
                    wait_started_monotonic_ns=timing.wait_started_monotonic_ns,
                    started_monotonic_ns=timing.started_monotonic_ns,
                    ended_monotonic_ns=timing.ended_monotonic_ns,
                )
                for timing in self._dispatch_timings
            )

    def stage_clock_summary(
        self,
    ) -> dict[str, object]:
        """Project content-free decoder stages on the server monotonic clock.

        Each owner reports its first acceptance-to-dispatch duration plus cumulative
        queue-wait and service durations. Background owner class is retained when the
        call enters arbitration; terminal wait overlap with another terminal owner's
        service is reported both per owner and in the aggregate.
        """

        with self._condition:
            owner_classes = dict(self._owner_classes)
            timings = tuple(
                InferenceDispatchTiming(
                    owner_kind=timing.owner_kind,
                    owner_key=timing.owner_key,
                    window_index=timing.window_index,
                    accepted_monotonic_ns=timing.accepted_monotonic_ns,
                    wait_started_monotonic_ns=timing.wait_started_monotonic_ns,
                    started_monotonic_ns=timing.started_monotonic_ns,
                    ended_monotonic_ns=timing.ended_monotonic_ns,
                )
                for timing in self._dispatch_timings
            )
        grouped: dict[tuple[InferenceKind, str], list[InferenceDispatchTiming]] = {}
        for timing in timings:
            grouped.setdefault((timing.owner_kind, timing.owner_key), []).append(timing)

        terminal_services = {
            owner: tuple(
                (row.started_monotonic_ns, row.ended_monotonic_ns)
                for row in rows
                if row.started_monotonic_ns is not None
                and row.ended_monotonic_ns is not None
            )
            for owner, rows in grouped.items()
            if owner_classes[owner] == "terminal"
        }
        owners: list[dict[str, object]] = []
        for owner, rows in grouped.items():
            kind, key = owner
            started = [row for row in rows if row.started_monotonic_ns is not None]
            completed = [row for row in started if row.ended_monotonic_ns is not None]
            owner_class = owner_classes[owner]
            contention_ns = 0
            if owner_class == "terminal":
                other_services = tuple(
                    interval
                    for other, intervals in terminal_services.items()
                    if other != owner
                    for interval in intervals
                )
                contention_ns = sum(
                    _covered_ns(
                        row.wait_started_monotonic_ns,
                        row.started_monotonic_ns,
                        other_services,
                    )
                    for row in started
                    if row.started_monotonic_ns is not None
                )
            first_started = min(
                (row.started_monotonic_ns for row in started),
                default=None,
            )
            owners.append(
                {
                    "owner_kind": kind,
                    "owner_key": key,
                    "owner_class": owner_class,
                    "window_count": len(rows),
                    "started_count": len(started),
                    "completed_count": len(completed),
                    "acceptance_to_first_dispatch_ms": _elapsed_ms(
                        min(row.accepted_monotonic_ns for row in rows),
                        first_started,
                    ),
                    "queue_wait_ms": (
                        None
                        if not started
                        else sum(
                            max(0, row.started_monotonic_ns - row.wait_started_monotonic_ns)
                            for row in started
                            if row.started_monotonic_ns is not None
                        )
                        / 1_000_000
                    ),
                    "service_ms": (
                        None
                        if not completed
                        else sum(
                            max(0, row.ended_monotonic_ns - row.started_monotonic_ns)
                            for row in completed
                            if row.started_monotonic_ns is not None
                            and row.ended_monotonic_ns is not None
                        )
                        / 1_000_000
                    ),
                    "terminal_contention_ms": contention_ns / 1_000_000,
                }
            )
        return {
            "clock": "server_monotonic",
            "owners": owners,
            "terminal_vs_terminal_contention_ms": sum(
                float(owner["terminal_contention_ms"]) for owner in owners
            ),
            "completed_windows": sum(
                timing.ended_monotonic_ns is not None for timing in timings
            ),
            "full_denominator": len(timings),
        }

    def _run(
        self,
        kind: InferenceKind,
        key: str,
        call: Callable[[], _T],
        *,
        owner_class: InferenceOwnerClass,
        on_wait: Callable[[], None] | None,
        on_start: Callable[[], None] | None,
    ) -> _T:
        if not key:
            raise ValueError("inference dispatch key must be non-empty.")
        accepted_ns = self._monotonic_ns()
        with self._condition:
            owner = (kind, key)
            self._owner_classes.setdefault(owner, owner_class)
            window_index = self._owner_window_counts.get(owner, 0)
            self._owner_window_counts[owner] = window_index + 1
            timing = _DispatchTimingState(
                owner_kind=kind,
                owner_key=key,
                window_index=window_index,
                accepted_monotonic_ns=accepted_ns,
                wait_started_monotonic_ns=self._monotonic_ns(),
            )
            self._dispatch_timings.append(timing)
        if on_wait is not None:
            on_wait()
        waiter = _Waiter(key)
        queue = self._live_waiters if kind == "live" else self._background_waiters
        with self._condition:
            queue.append(waiter)
            while True:
                if kind == "background" and key in self._cancelled_background_keys:
                    queue.remove(waiter)
                    self._condition.notify_all()
                    raise InferenceDispatchCancelled("background inference was cancelled before dispatch.")
                first = queue and queue[0] is waiter
                has_capacity = self._running_calls < self._max_calls
                if kind == "live":
                    eligible = first and has_capacity
                else:
                    eligible = (
                        first
                        and has_capacity
                        and not self._live_waiters
                        and self._running_background_calls < self._max_background_calls
                    )
                if eligible:
                    queue.popleft()
                    self._running_calls += 1
                    if kind == "background":
                        self._running_background_calls += 1
                    break
                self._condition.wait()
        try:
            with self._condition:
                timing.started_monotonic_ns = self._monotonic_ns()
            if on_start is not None:
                on_start()
            return call()
        finally:
            with self._condition:
                timing.ended_monotonic_ns = self._monotonic_ns()
                self._running_calls -= 1
                if kind == "background":
                    self._running_background_calls -= 1
                self._condition.notify_all()


class ScheduledInferenceRunner:
    """Runner adapter that makes one decoder call through shared arbitration."""

    def __init__(
        self,
        delegate: Any,
        scheduler: InferenceDispatchScheduler,
        *,
        kind: InferenceKind,
    ) -> None:
        if kind not in {"live", "background"}:
            raise ValueError("inference kind must be live or background.")
        if not hasattr(delegate, "transcribe"):
            raise ValueError("scheduled inference delegate must expose transcribe().")
        self.delegate = delegate
        self.scheduler = scheduler
        self.kind = kind
        self.model_path = str(getattr(delegate, "model_path", ""))

    @property
    def is_loaded(self) -> bool:
        return bool(getattr(self.delegate, "is_loaded", True))

    def runtime_info(self) -> dict[str, Any]:
        runtime = getattr(self.delegate, "runtime_info", None)
        return runtime() if callable(runtime) else {"path": self.model_path}

    def with_kind(self, kind: InferenceKind) -> ScheduledInferenceRunner:
        return ScheduledInferenceRunner(self.delegate, self.scheduler, kind=kind)

    def transcribe(self, audio_path: Any, **kwargs: Any) -> Any:
        key = kwargs.pop("_dispatch_key", None)
        explicit_key = key is not None
        on_wait = kwargs.pop("_dispatch_on_wait", None)
        on_start = kwargs.pop("_dispatch_on_start", None)
        if key is None:
            key = f"{self.kind}:{threading.get_ident()}"
        call = lambda: self.delegate.transcribe(audio_path, **kwargs)
        if self.kind == "live":
            return self.scheduler.run_live(
                str(key), call, on_wait=on_wait, on_start=on_start
            )
        return self.scheduler.run_background(
            str(key),
            call,
            owner_class="file" if explicit_key else "terminal",
            on_wait=on_wait,
            on_start=on_start,
        )


def _elapsed_ms(start_ns: int, end_ns: int | None) -> float | None:
    if end_ns is None:
        return None
    return max(0, end_ns - start_ns) / 1_000_000


def _covered_ns(
    start_ns: int,
    end_ns: int,
    intervals: tuple[tuple[int, int], ...],
) -> int:
    covered = sorted(
        (max(start_ns, left), min(end_ns, right))
        for left, right in intervals
        if left < end_ns and right > start_ns
    )
    if not covered:
        return 0
    total = 0
    left, right = covered[0]
    for next_left, next_right in covered[1:]:
        if next_left <= right:
            right = max(right, next_right)
        else:
            total += right - left
            left, right = next_left, next_right
    return total + right - left


__all__ = [
    "InferenceDispatchCancelled",
    "InferenceDispatchScheduler",
    "InferenceDispatchSnapshot",
    "InferenceDispatchTiming",
    "ScheduledInferenceRunner",
]
