#!/usr/bin/env python3
"""Deterministic A3 lifecycle-ownership prototype."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field


class LifecycleViolation(RuntimeError):
    pass


class CurrentClosingClosedControl:
    """Current shape: close revokes viewing before an asynchronous revision."""

    def run(self) -> dict[str, object]:
        state_path = ["active", "closing", "closed"]
        view_authority = False
        revision_published = True
        return {
            "failed_invariant": "terminal_revision_visible",
            "invariant_passed": view_authority or not revision_published,
            "revision_published": revision_published,
            "state_path": state_path,
            "view_authority_at_revision": view_authority,
        }


class OneThreadPerSessionControl:
    """Bad control: each stopped session starts its own CPU finalizer."""

    def run(self, *, session_count: int) -> dict[str, object]:
        return {
            "failed_invariant": "bounded_single_cpu_finalizer",
            "invariant_passed": session_count <= 1,
            "max_cpu_finalizers": session_count,
            "queue_owner_count": 0,
        }


class EarlyTapeReleaseControl:
    """Bad control: release the only lease before the queued reader starts."""

    def run(self) -> dict[str, object]:
        lease_count = 1
        lease_count -= 1
        ttl_zero_reaped = lease_count == 0
        return {
            "failed_invariant": "tape_read_lease_held",
            "invariant_passed": lease_count == 1,
            "lease_count_at_finalizer_start": lease_count,
            "ttl_zero_reaped_before_read": ttl_zero_reaped,
        }


@dataclass
class _Meeting:
    meeting_id: str
    state: str = "active"
    capture_authority: bool = True
    captured_frames: int = 0
    events: list[dict[str, object]] = field(default_factory=list)
    fallback_reason: str | None = None
    l2_started: bool = False
    result_source: str = "live_l1"
    tape_lease_acquires: int = 0
    tape_lease_count: int = 0
    tape_lease_releases: int = 0
    tape_reaped: bool = False
    tape_sealed: bool = False
    view_authority: bool = True


class LifecyclePrototype:
    def __init__(self, *, queue_capacity: int) -> None:
        self.queue_capacity = queue_capacity
        self._meetings: dict[str, _Meeting] = {}
        self._queue: list[str] = []
        self._active_finalizer: str | None = None
        self._live_captures_during_finalizer = 0
        self._max_cpu_finalizers = 0

    def start(self, meeting_id: str) -> dict[str, object]:
        self._meetings[meeting_id] = _Meeting(meeting_id)
        return self.snapshot(meeting_id)

    def begin_stop(self, meeting_id: str) -> dict[str, object]:
        meeting = self._meetings[meeting_id]
        meeting.state = "closing"
        return self.snapshot(meeting_id)

    def acknowledge_stop(self, meeting_id: str) -> dict[str, object]:
        meeting = self._meetings[meeting_id]
        if len(self._queue) >= self.queue_capacity:
            raise LifecycleViolation("finalizer_queue_full")
        meeting.capture_authority = False
        meeting.state = "finalizing"
        meeting.tape_sealed = True
        meeting.tape_lease_count = 1
        meeting.tape_lease_acquires = 1
        self._queue.append(meeting_id)
        return self.snapshot(meeting_id)

    def capture(self, meeting_id: str, frame: bytes) -> dict[str, object]:
        del frame
        meeting = self._meetings[meeting_id]
        if not meeting.capture_authority:
            raise LifecycleViolation("capture_authority_closed")
        meeting.captured_frames += 1
        if self._active_finalizer is not None:
            self._live_captures_during_finalizer += 1
        return self.snapshot(meeting_id)

    def abort(self, meeting_id: str) -> dict[str, object]:
        meeting = self._meetings[meeting_id]
        if self._active_finalizer == meeting_id:
            raise LifecycleViolation("abort_after_l2_started")
        if meeting_id in self._queue:
            self._queue.remove(meeting_id)
            meeting.tape_lease_count = 0
            meeting.tape_lease_releases += 1
        meeting.capture_authority = False
        meeting.result_source = "l1"
        meeting.state = "aborted"
        return self.snapshot(meeting_id)

    def view(self, meeting_id: str) -> dict[str, object]:
        return self.snapshot(meeting_id)

    def view_events(
        self, meeting_id: str, *, after_sequence: int
    ) -> list[dict[str, object]]:
        meeting = self._meetings[meeting_id]
        return [
            dict(event)
            for event in meeting.events
            if int(event["sequence"]) > after_sequence
        ]

    def start_next_finalizer(self) -> dict[str, object]:
        if self._active_finalizer is not None:
            raise LifecycleViolation("cpu_finalizer_already_active")
        if not self._queue:
            raise LifecycleViolation("finalizer_queue_empty")
        self._active_finalizer = self._queue.pop(0)
        self._max_cpu_finalizers = max(self._max_cpu_finalizers, 1)
        self._meetings[self._active_finalizer].l2_started = True
        return self.snapshot(self._active_finalizer)

    def scheduler_snapshot(self) -> dict[str, int]:
        return {
            "active_cpu_finalizers": int(self._active_finalizer is not None),
            "max_cpu_finalizers": self._max_cpu_finalizers,
            "queue_capacity": self.queue_capacity,
            "queue_depth": len(self._queue),
            "queue_owner_count": 1,
        }

    def responsiveness_snapshot(self) -> dict[str, int]:
        return {
            "active_cpu_finalizers": int(self._active_finalizer is not None),
            "live_captures_during_finalizer": self._live_captures_during_finalizer,
        }

    def reap_ttl_zero(self) -> list[str]:
        reaped = []
        for meeting in self._meetings.values():
            if (
                meeting.tape_sealed
                and meeting.tape_lease_count == 0
                and not meeting.tape_reaped
            ):
                meeting.tape_reaped = True
                reaped.append(meeting.meeting_id)
        return sorted(reaped)

    def finish_active_finalizer(self, outcome: str) -> dict[str, object]:
        if self._active_finalizer is None:
            raise LifecycleViolation("no_active_finalizer")
        meeting = self._meetings[self._active_finalizer]
        failures = {"timeout", "cancelled", "shutdown", "degraded_tape", "exception"}
        if outcome not in {"success", *failures}:
            raise LifecycleViolation("unsupported_finalizer_outcome")
        if outcome == "success":
            meeting.state = "closed"
            meeting.result_source = "l2"
            event_type = "identity_revision_final"
        else:
            meeting.state = "failed"
            meeting.result_source = "l1"
            meeting.fallback_reason = outcome
            event_type = "identity_finalization_failed"
        meeting.events.append({"sequence": len(meeting.events) + 1, "type": event_type})
        meeting.tape_lease_count = 0
        meeting.tape_lease_releases = 1
        self._active_finalizer = None
        return self.snapshot(meeting.meeting_id)

    def execute_active_finalizer(
        self, work: Callable[[], str]
    ) -> dict[str, object]:
        try:
            outcome = work()
        except Exception:
            outcome = "exception"
        return self.finish_active_finalizer(outcome)

    def snapshot(self, meeting_id: str) -> dict[str, object]:
        meeting = self._meetings[meeting_id]
        return {
            "capture_authority": meeting.capture_authority,
            "captured_frames": meeting.captured_frames,
            "fallback_reason": meeting.fallback_reason,
            "l2_started": meeting.l2_started,
            "meeting_id": meeting.meeting_id,
            "result_source": meeting.result_source,
            "state": meeting.state,
            "tape_lease_acquires": meeting.tape_lease_acquires,
            "tape_lease_count": meeting.tape_lease_count,
            "tape_lease_releases": meeting.tape_lease_releases,
            "tape_reaped": meeting.tape_reaped,
            "tape_sealed": meeting.tape_sealed,
            "view_authority": meeting.view_authority,
        }
