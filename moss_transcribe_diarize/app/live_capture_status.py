from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Literal, Mapping

from .live_helper_presence import HelperPresenceSnapshot
from .live_lane_contract import LiveLane, LiveV2Frame
from .live_v2_session import LiveV2SessionSnapshot


CapturePhase = Literal["starting", "awaiting_audio", "recording", "failed"]

_FAILURE_STATUS_LINES: dict[str, str | dict[str, str]] = {
    "browser_microphone_permission_denied": (
        "Microphone access was denied. Allow microphone access in Chrome and try again."
    ),
    "browser_capture_request_rejected": (
        "Screen sharing did not start. Choose a tab or screen and try again."
    ),
    "browser_surface_audio_missing": (
        "The shared surface has no audio. Choose a Chrome tab and enable Share tab audio."
    ),
    "browser_track_ended": {
        "microphone": "Microphone audio stopped. Continuing with shared audio.",
        "system": "Shared audio stopped. Continuing with microphone audio.",
    },
    "browser_audio_context_suspended": (
        "Audio capture was suspended. Return to this tab and resume capture."
    ),
    "browser_sustained_clipping": {
        "microphone": "Microphone audio is too loud and may sound distorted.",
        "system": "Shared audio is too loud and may sound distorted.",
    },
    "browser_microphone_silent": (
        "No microphone sound was detected. In Chrome, open Settings > Privacy and security > "
        "Site settings > Microphone and select the correct default input."
    ),
}
BROWSER_CAPTURE_FAILURE_CODES = frozenset(_FAILURE_STATUS_LINES)

_HELPER_STATUS_LINES = {
    "starting": "Starting audio capture.",
    "capturing": "Capturing microphone and shared audio.",
    "degraded": "Audio capture is degraded, but the session is continuing.",
    "recovering": "Audio capture is recovering.",
    "failed": "Audio capture failed.",
    "stopped": "Audio capture stopped.",
}


@dataclass(frozen=True, slots=True)
class LiveCaptureStatus:
    capture_phase: CapturePhase
    status_line: str

    def to_dict(self) -> dict[str, str]:
        return {
            "capture_phase": self.capture_phase,
            "status_line": self.status_line,
        }


@dataclass(frozen=True, slots=True)
class LiveCaptureLaneObservation:
    """Server-measured facts that survive v2 frame accounting."""

    last_server_arrival_monotonic_ns: int | None
    consecutive_silent_samples: int
    consecutive_sequence_rejections: int
    consecutive_backpressure_rejections: int
    last_rejection_monotonic_ns: int | None


@dataclass(frozen=True, slots=True)
class LiveCaptureObservationSnapshot:
    """Immutable session observation copy for the status projection."""

    lanes: Mapping[LiveLane, LiveCaptureLaneObservation]


@dataclass(slots=True)
class _LiveCaptureLaneObservation:
    last_server_arrival_monotonic_ns: int | None = None
    consecutive_silent_samples: int = 0
    consecutive_sequence_rejections: int = 0
    consecutive_backpressure_rejections: int = 0
    last_rejection_monotonic_ns: int | None = None


class LiveCaptureObservationRegistry:
    """Session-scoped metadata recorded after classified v2 ingress outcomes.

    This intentionally retains no PCM, client clock, or frame object. Threshold policy remains
    separate: the projection receives the immutable snapshot now, while a measured later change
    decides which ages or counts warrant a user-facing state.
    """

    def __init__(self, *, monotonic_ns: Callable[[], int] | None = None) -> None:
        self._monotonic_ns = monotonic_ns or time.monotonic_ns
        self._sessions: dict[str, dict[LiveLane, _LiveCaptureLaneObservation]] = {}
        self._lock = threading.RLock()

    def __contains__(self, session_id: object) -> bool:
        return isinstance(session_id, str) and self.contains(session_id)

    def contains(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._sessions

    def create(self, session_id: str) -> None:
        _capture_session_id(session_id)
        with self._lock:
            if session_id in self._sessions:
                raise ValueError(f"capture observation session {session_id} already exists.")
            self._sessions[session_id] = {
                lane: _LiveCaptureLaneObservation() for lane in LiveLane
            }

    def release(self, session_id: str) -> LiveCaptureObservationSnapshot | None:
        _capture_session_id(session_id)
        with self._lock:
            lanes = self._sessions.pop(session_id, None)
            return None if lanes is None else self._snapshot_locked(lanes)

    def snapshot(self, session_id: str) -> LiveCaptureObservationSnapshot:
        _capture_session_id(session_id)
        with self._lock:
            try:
                return self._snapshot_locked(self._sessions[session_id])
            except KeyError as exc:
                raise KeyError(session_id) from exc

    def observe_accepted(self, session_id: str, frame: LiveV2Frame) -> LiveCaptureObservationSnapshot:
        if not isinstance(frame, LiveV2Frame):
            raise ValueError("frame must be a LiveV2Frame.")
        with self._lock:
            lane = self._lane_locked(session_id, frame.lane)
            lane.last_server_arrival_monotonic_ns = self._now_monotonic_ns()
            if frame.silent:
                lane.consecutive_silent_samples += frame.sample_count
            else:
                lane.consecutive_silent_samples = 0
            lane.consecutive_sequence_rejections = 0
            lane.consecutive_backpressure_rejections = 0
            return self._snapshot_locked(self._sessions[session_id])

    def observe_sequence_rejection(
        self,
        session_id: str,
        lane: LiveLane,
    ) -> LiveCaptureObservationSnapshot:
        with self._lock:
            observation = self._lane_locked(session_id, lane)
            observation.consecutive_sequence_rejections += 1
            observation.last_rejection_monotonic_ns = self._now_monotonic_ns()
            return self._snapshot_locked(self._sessions[session_id])

    def observe_backpressure_rejection(
        self,
        session_id: str,
        lane: LiveLane,
    ) -> LiveCaptureObservationSnapshot:
        with self._lock:
            observation = self._lane_locked(session_id, lane)
            observation.consecutive_backpressure_rejections += 1
            observation.last_rejection_monotonic_ns = self._now_monotonic_ns()
            return self._snapshot_locked(self._sessions[session_id])

    def _lane_locked(
        self,
        session_id: str,
        lane: LiveLane,
    ) -> _LiveCaptureLaneObservation:
        _capture_session_id(session_id)
        if not isinstance(lane, LiveLane):
            raise ValueError("lane must be a canonical v2 live lane.")
        try:
            return self._sessions[session_id][lane]
        except KeyError as exc:
            raise KeyError(session_id) from exc

    def _now_monotonic_ns(self) -> int:
        value = self._monotonic_ns()
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("monotonic_ns must return a non-negative integer.")
        return value

    @staticmethod
    def _snapshot_locked(
        lanes: Mapping[LiveLane, _LiveCaptureLaneObservation],
    ) -> LiveCaptureObservationSnapshot:
        return LiveCaptureObservationSnapshot(
            lanes=MappingProxyType(
                {
                    lane: LiveCaptureLaneObservation(
                        last_server_arrival_monotonic_ns=observation.last_server_arrival_monotonic_ns,
                        consecutive_silent_samples=observation.consecutive_silent_samples,
                        consecutive_sequence_rejections=observation.consecutive_sequence_rejections,
                        consecutive_backpressure_rejections=observation.consecutive_backpressure_rejections,
                        last_rejection_monotonic_ns=observation.last_rejection_monotonic_ns,
                    )
                    for lane, observation in lanes.items()
                }
            )
        )


def project_live_capture_status(
    presence: HelperPresenceSnapshot | None,
    *,
    v2_session: LiveV2SessionSnapshot | None = None,
    observations: LiveCaptureObservationSnapshot | None = None,
) -> LiveCaptureStatus:
    """Fuse helper and v2 server facts into the client-facing capture judgment.

    Failure codes intentionally remain an open string vocabulary at the heartbeat parser.
    Known codes get actionable copy here; future native or browser codes use a stable generic
    fallback instead of being rejected or leaked into the UI.
    """

    # Observation thresholds are deliberately not selected yet. Accept the immutable
    # server-side snapshot at the projection seam so the later policy cannot regress to a
    # client clock or retained frames.
    del observations

    if presence is None:
        return LiveCaptureStatus("starting", "Waiting for audio capture to start.")

    failed_lanes = {
        lane for lane, health in presence.lanes.items() if health.state == "failed"
    }
    issues = {
        lane: (health.state, health.failure_code)
        for lane, health in presence.lanes.items()
        if health.failure_code is not None
    }
    awaiting_lanes: list[str] = []
    if v2_session is not None:
        for lane, snapshot in v2_session.lanes.items():
            lane_name = lane.value
            if snapshot.health == "failed":
                failed_lanes.add(lane_name)
                reported = issues.get(lane_name)
                issues[lane_name] = (
                    "failed",
                    snapshot.failure_code if reported is None else reported[1],
                )
            elif snapshot.accepted_samples == 0:
                awaiting_lanes.append(lane_name)

    if (
        presence.state in {"failed", "stopped"}
        or v2_session is not None and v2_session.status == "failed"
        or len(failed_lanes) == len(presence.lanes)
    ):
        phase: CapturePhase = "failed"
    elif presence.state in {"starting", "recovering"}:
        phase = "starting"
    elif awaiting_lanes:
        phase = "awaiting_audio"
    else:
        phase = "recording"

    sorted_issues = sorted(
        (state != "failed", lane, code) for lane, (state, code) in issues.items()
    )
    if not sorted_issues:
        if phase == "awaiting_audio":
            if len(awaiting_lanes) == 1:
                lane = awaiting_lanes[0]
                label = "microphone audio" if lane == "microphone" else "shared audio"
                return LiveCaptureStatus(phase, f"Waiting for {label} to arrive.")
            return LiveCaptureStatus(phase, "Waiting for microphone and shared audio to arrive.")
        return LiveCaptureStatus(phase, _HELPER_STATUS_LINES[presence.state])

    not_failed, lane, code = sorted_issues[0]
    status_line = _FAILURE_STATUS_LINES.get(code)
    if isinstance(status_line, dict):
        status_line = status_line[lane]
    if status_line is None:
        label = "Microphone" if lane == "microphone" else "Shared audio"
        condition = "is degraded" if not_failed else "failed"
        status_line = f"{label} capture {condition}. The session is continuing."
    return LiveCaptureStatus(phase, status_line)


def _capture_session_id(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("session_id must be a non-empty string.")
