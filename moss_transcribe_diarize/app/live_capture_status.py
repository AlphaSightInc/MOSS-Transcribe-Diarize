from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .live_helper_presence import HelperPresenceSnapshot
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


def project_live_capture_status(
    presence: HelperPresenceSnapshot | None,
    *,
    v2_session: LiveV2SessionSnapshot | None = None,
) -> LiveCaptureStatus:
    """Fuse helper and v2 server facts into the client-facing capture judgment.

    Failure codes intentionally remain an open string vocabulary at the heartbeat parser.
    Known codes get actionable copy here; future native or browser codes use a stable generic
    fallback instead of being rejected or leaked into the UI.
    """

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
