from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .live_helper_presence import HelperPresenceSnapshot


CapturePhase = Literal["starting", "recording", "failed"]

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
) -> LiveCaptureStatus:
    """Turn helper facts into the only capture judgment exposed to product clients.

    Failure codes intentionally remain an open string vocabulary at the heartbeat parser.
    Known codes get actionable copy here; future native or browser codes use a stable generic
    fallback instead of being rejected or leaked into the UI.
    """

    if presence is None:
        return LiveCaptureStatus("starting", "Waiting for audio capture to start.")

    failed_lanes = [
        lane for lane, health in presence.lanes.items() if health.state == "failed"
    ]
    if presence.state in {"failed", "stopped"} or len(failed_lanes) == len(presence.lanes):
        phase: CapturePhase = "failed"
    elif presence.state in {"starting", "recovering"}:
        phase = "starting"
    else:
        phase = "recording"

    issues = sorted(
        (
            health.state != "failed",
            lane,
            health.failure_code,
        )
        for lane, health in presence.lanes.items()
        if health.failure_code is not None
    )
    if not issues:
        return LiveCaptureStatus(phase, _HELPER_STATUS_LINES[presence.state])

    _degraded, lane, code = issues[0]
    status_line = _FAILURE_STATUS_LINES.get(code)
    if isinstance(status_line, dict):
        status_line = status_line[lane]
    if status_line is None:
        label = "Microphone" if lane == "microphone" else "Shared audio"
        condition = "failed" if presence.lanes[lane].state == "failed" else "is degraded"
        status_line = f"{label} capture {condition}. The session is continuing."
    return LiveCaptureStatus(phase, status_line)
