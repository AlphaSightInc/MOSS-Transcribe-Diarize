from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Mapping

from .live_ingest import LiveLaneIngress, RetainedLiveV2Frame
from .live_lane_contract import LiveLane, LiveV2Ack, LiveV2Frame


class LiveV2AccountingError(ValueError):
    pass


class LiveV2SessionTerminalError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LiveV2LaneSnapshot:
    lane: LiveLane
    next_sequence: int
    accepted_samples: int
    accounted_samples: int
    failed_samples: int
    retained_samples: int
    current_device_epoch: int | None
    pruned_through_sequence: int
    health: str
    failure_code: str | None

    def to_dict(self) -> dict[str, int | str | None]:
        return {
            "lane": self.lane.value,
            "next_sequence": self.next_sequence,
            "accepted_samples": self.accepted_samples,
            "accounted_samples": self.accounted_samples,
            "failed_samples": self.failed_samples,
            "retained_samples": self.retained_samples,
            "current_device_epoch": self.current_device_epoch,
            "pruned_through_sequence": self.pruned_through_sequence,
            "health": self.health,
            "failure_code": self.failure_code,
        }


@dataclass(frozen=True, slots=True)
class LiveV2SessionSnapshot:
    status: str
    lanes: Mapping[LiveLane, LiveV2LaneSnapshot]
    terminal_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "lanes": {
                lane.value: snapshot.to_dict()
                for lane, snapshot in self.lanes.items()
            },
        }


@dataclass(slots=True)
class _LaneLifecycle:
    accounted_samples: int = 0
    failed_samples: int = 0
    health: str = "active"
    failure_code: str | None = None


class LiveV2Session:
    """In-process lifecycle authority for source-labelled v2 lane ingress."""

    def __init__(self, *, max_retained_samples: int):
        self._ingress = LiveLaneIngress(max_retained_samples=max_retained_samples)
        self._lanes = {lane: _LaneLifecycle() for lane in LiveLane}
        self._status = "active"
        self._terminal_reason: str | None = None
        self._lock = threading.RLock()

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    def accept(self, frame: LiveV2Frame) -> LiveV2Ack:
        if not isinstance(frame, LiveV2Frame):
            raise ValueError("frame must be LiveV2Frame.")
        with self._lock:
            self._ensure_accepting()
            lifecycle = self._lanes[frame.lane]
            if lifecycle.health != "active":
                raise LiveV2SessionTerminalError(
                    f"v2 {frame.lane.value} lane is {lifecycle.health}."
                )
            return self._ingress.accept(frame)

    def snapshot(self) -> LiveV2SessionSnapshot:
        with self._lock:
            return self._snapshot_locked()

    def retained_frames(self, lane: LiveLane | None = None) -> tuple[RetainedLiveV2Frame, ...]:
        with self._lock:
            return self._ingress.retained_frames(lane)

    def account_through(self, watermarks: Mapping[LiveLane, int]) -> LiveV2SessionSnapshot:
        if not isinstance(watermarks, Mapping) or not watermarks:
            raise LiveV2AccountingError("watermarks must be a non-empty mapping.")
        with self._lock:
            self._ensure_not_terminal()
            plan: dict[LiveLane, tuple[RetainedLiveV2Frame, ...]] = {}
            for lane, through_sequence in watermarks.items():
                lane = _assert_lane(lane)
                _non_negative_int(through_sequence, "through_sequence")
                if self._lanes[lane].health != "active":
                    raise LiveV2AccountingError(f"v2 {lane.value} lane is not accountable.")
                plan[lane] = self._accountable_prefix(lane, through_sequence)

            for lane, through_sequence in watermarks.items():
                lane = _assert_lane(lane)
                released = self._ingress.release_retained_prefix(lane, through_sequence)
                if released != plan[lane]:
                    raise LiveV2AccountingError("retained frame prefix changed during accounting.")
                self._lanes[lane].accounted_samples += sum(
                    retained.frame.sample_count for retained in released
                )
            return self._snapshot_locked()

    def fail_lane(self, lane: LiveLane, code: str) -> LiveV2SessionSnapshot:
        lane = _assert_lane(lane)
        if not isinstance(code, str) or not code:
            raise ValueError("failure code must be a non-empty string.")
        with self._lock:
            self._ensure_not_terminal()
            lifecycle = self._lanes[lane]
            if lifecycle.health == "failed":
                if lifecycle.failure_code != code:
                    raise LiveV2AccountingError(f"v2 {lane.value} lane already failed.")
                return self._snapshot_locked()
            retained = self._ingress.retained_frames(lane)
            if retained:
                self._ingress.release_retained_prefix(lane, retained[-1].frame.sequence)
            lifecycle.failed_samples += sum(item.frame.sample_count for item in retained)
            lifecycle.health = "failed"
            lifecycle.failure_code = code
            return self._snapshot_locked()

    async def stop(self, deadline: float) -> LiveV2SessionSnapshot:
        if not isinstance(deadline, (int, float)) or isinstance(deadline, bool):
            raise ValueError("deadline must be numeric.")
        with self._lock:
            self._ensure_not_terminal()
            if self._has_failed_lane_locked():
                self._status = "failed"
                self._terminal_reason = self._first_failure_code_locked()
                return self._snapshot_locked()
            if self._is_clean_locked():
                self._status = "closed"
                return self._snapshot_locked()
            self._status = "closing"
            return self._snapshot_locked()

    def abort(self, reason: str = "aborted") -> LiveV2SessionSnapshot:
        if not isinstance(reason, str) or not reason:
            raise ValueError("abort reason must be a non-empty string.")
        with self._lock:
            self._ensure_not_terminal()
            self._release_all_retained_locked()
            self._status = "aborted"
            self._terminal_reason = reason
            return self._snapshot_locked()

    def expire(self, reason: str) -> LiveV2SessionSnapshot:
        if not isinstance(reason, str) or not reason:
            raise ValueError("expiry reason must be a non-empty string.")
        with self._lock:
            self._ensure_not_terminal()
            for lane in LiveLane:
                lifecycle = self._lanes[lane]
                retained = self._ingress.retained_frames(lane)
                if retained:
                    self._ingress.release_retained_prefix(lane, retained[-1].frame.sequence)
                lifecycle.failed_samples += sum(item.frame.sample_count for item in retained)
                if lifecycle.failed_samples:
                    lifecycle.health = "failed"
                    lifecycle.failure_code = lifecycle.failure_code or reason
            self._status = "failed"
            self._terminal_reason = reason
            return self._snapshot_locked()

    def _accountable_prefix(
        self,
        lane: LiveLane,
        through_sequence: int,
    ) -> tuple[RetainedLiveV2Frame, ...]:
        retained = self._ingress.retained_frames(lane)
        if not retained:
            raise LiveV2AccountingError(f"v2 {lane.value} lane has no retained frames.")
        first_sequence = retained[0].frame.sequence
        if through_sequence < first_sequence:
            raise LiveV2AccountingError(f"v2 {lane.value} accounting watermark regressed.")
        selected: list[RetainedLiveV2Frame] = []
        expected = first_sequence
        for frame in retained:
            if frame.frame.sequence != expected:
                raise LiveV2AccountingError(f"v2 {lane.value} retained frames are gapped.")
            if frame.frame.sequence > through_sequence:
                break
            selected.append(frame)
            expected += 1
        if not selected or selected[-1].frame.sequence != through_sequence:
            raise LiveV2AccountingError(f"v2 {lane.value} accounting watermark is not retained.")
        return tuple(selected)

    def _release_all_retained_locked(self) -> None:
        for lane in LiveLane:
            retained = self._ingress.retained_frames(lane)
            if retained:
                self._ingress.release_retained_prefix(lane, retained[-1].frame.sequence)

    def _ensure_accepting(self) -> None:
        if self._status != "active":
            raise LiveV2SessionTerminalError(f"v2 session is {self._status}.")

    def _ensure_not_terminal(self) -> None:
        if self._status in {"closed", "failed", "aborted"}:
            raise LiveV2SessionTerminalError(f"v2 session is {self._status}.")

    def _has_failed_lane_locked(self) -> bool:
        return any(lane.health == "failed" or lane.failed_samples for lane in self._lanes.values())

    def _first_failure_code_locked(self) -> str | None:
        for lane in LiveLane:
            failure_code = self._lanes[lane].failure_code
            if failure_code is not None:
                return failure_code
        return None

    def _is_clean_locked(self) -> bool:
        for lane in LiveLane:
            ingress = self._ingress.snapshot(lane)
            lifecycle = self._lanes[lane]
            if ingress.accepted_samples != lifecycle.accounted_samples:
                return False
            if lifecycle.failed_samples or ingress.retained_samples:
                return False
        return True

    def _snapshot_locked(self) -> LiveV2SessionSnapshot:
        lanes = {}
        for lane in LiveLane:
            ingress = self._ingress.snapshot(lane)
            lifecycle = self._lanes[lane]
            lanes[lane] = LiveV2LaneSnapshot(
                lane=lane,
                next_sequence=ingress.next_sequence,
                accepted_samples=ingress.accepted_samples,
                accounted_samples=lifecycle.accounted_samples,
                failed_samples=lifecycle.failed_samples,
                retained_samples=ingress.retained_samples,
                current_device_epoch=ingress.current_device_epoch,
                pruned_through_sequence=ingress.pruned_through_sequence,
                health=lifecycle.health,
                failure_code=lifecycle.failure_code,
            )
        return LiveV2SessionSnapshot(
            status=self._status,
            lanes=lanes,
            terminal_reason=self._terminal_reason,
        )


class LiveV2SessionRegistry:
    def __init__(self, *, max_retained_samples: int):
        _positive_int(max_retained_samples, "max_retained_samples")
        self._max_retained_samples = max_retained_samples
        self._sessions: dict[str, LiveV2Session] = {}
        self._lock = threading.RLock()

    def __contains__(self, session_id: object) -> bool:
        return isinstance(session_id, str) and self.contains(session_id)

    def contains(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._sessions

    def create(self, session_id: str) -> LiveV2Session:
        _session_id(session_id)
        with self._lock:
            if session_id in self._sessions:
                raise ValueError(f"v2 session {session_id} already exists.")
            session = LiveV2Session(max_retained_samples=self._max_retained_samples)
            self._sessions[session_id] = session
            return session

    def get(self, session_id: str) -> LiveV2Session:
        _session_id(session_id)
        with self._lock:
            try:
                return self._sessions[session_id]
            except KeyError as exc:
                raise KeyError(session_id) from exc

    def release(self, session_id: str) -> LiveV2Session | None:
        _session_id(session_id)
        with self._lock:
            return self._sessions.pop(session_id, None)

    def expire(self, session_id: str, reason: str) -> LiveV2SessionSnapshot:
        _session_id(session_id)
        with self._lock:
            session = self.get(session_id)
            snapshot = session.expire(reason)
            self._sessions.pop(session_id, None)
            return snapshot


def _assert_lane(value: LiveLane) -> LiveLane:
    if not isinstance(value, LiveLane):
        raise ValueError("lane must be a canonical v2 live lane.")
    return value


def _session_id(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("session_id must be a non-empty string.")


def _non_negative_int(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer.")
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")


def _positive_int(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer.")
    if value <= 0:
        raise ValueError(f"{name} must be positive.")
