"""Bounded Live-priority arbitration at the replaceable decoder seam."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Literal, TypeVar


InferenceKind = Literal["live", "background"]
_T = TypeVar("_T")


class InferenceDispatchCancelled(RuntimeError):
    """Queued background work lost its owning Meeting before decoder dispatch."""


@dataclass(frozen=True, slots=True)
class InferenceDispatchSnapshot:
    running_calls: int
    running_background_calls: int
    waiting_live_calls: int
    waiting_background_calls: int


@dataclass(slots=True)
class _Waiter:
    key: str


class InferenceDispatchScheduler:
    """Two-slot decoder gate: Live first, at most one background call.

    Calls already running are non-preemptible. File/URL windowing crosses this interface once
    per decoder window, so it yields between windows. Live may consume both slots; background
    may consume only one, leaving one slot available when Live arrives later.
    """

    def __init__(self, *, max_calls: int = 2, max_background_calls: int = 1) -> None:
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

    def run_live(
        self,
        key: str,
        call: Callable[[], _T],
        *,
        on_wait: Callable[[], None] | None = None,
        on_start: Callable[[], None] | None = None,
    ) -> _T:
        return self._run("live", key, call, on_wait=on_wait, on_start=on_start)

    def run_background(
        self,
        key: str,
        call: Callable[[], _T],
        *,
        on_wait: Callable[[], None] | None = None,
        on_start: Callable[[], None] | None = None,
    ) -> _T:
        return self._run("background", key, call, on_wait=on_wait, on_start=on_start)

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

    def _run(
        self,
        kind: InferenceKind,
        key: str,
        call: Callable[[], _T],
        *,
        on_wait: Callable[[], None] | None,
        on_start: Callable[[], None] | None,
    ) -> _T:
        if not key:
            raise ValueError("inference dispatch key must be non-empty.")
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
            if on_start is not None:
                on_start()
            return call()
        finally:
            with self._condition:
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
            str(key), call, on_wait=on_wait, on_start=on_start
        )


__all__ = [
    "InferenceDispatchCancelled",
    "InferenceDispatchScheduler",
    "InferenceDispatchSnapshot",
    "ScheduledInferenceRunner",
]
