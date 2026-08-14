from __future__ import annotations

import pytest

from moss_transcribe_diarize.app.live_capture_status import (
    BROWSER_CAPTURE_FAILURE_CODES,
    LiveCaptureObservationRegistry,
    project_live_capture_status,
)
from moss_transcribe_diarize.app.live_helper_presence import (
    HELPER_HEALTH_SCHEMA,
    HelperHeartbeat,
    HelperPresenceRegistry,
)
from moss_transcribe_diarize.app.live_lane_contract import LiveLane, LiveV2Frame


def _observation_frame(*, sequence: int, silent: bool, sample_count: int) -> LiveV2Frame:
    return LiveV2Frame(
        lane=LiveLane.MICROPHONE,
        sequence=sequence,
        capture_timestamp_ns=0,
        device_epoch=0,
        silent=silent,
        discontinuity=False,
        sample_rate=1,
        sample_count=sample_count,
        pcm=b"\0\0" * sample_count,
    )


def _presence(
    *,
    state: str = "capturing",
    lane: str | None = None,
    lane_state: str = "capturing",
    failure_code: str | None = None,
):
    lanes = {
        name: {
            "state": "capturing",
            "device_epoch": 0,
            "dropped_frames": 0,
            "discontinuities": 0,
            "failure_code": None,
        }
        for name in ("system", "microphone")
    }
    if lane is not None:
        lanes[lane]["state"] = lane_state
        lanes[lane]["failure_code"] = failure_code
    heartbeat = HelperHeartbeat.from_dict(
        {
            "schema": HELPER_HEALTH_SCHEMA,
            "instance_id": "capture-status-test",
            "sequence": 1,
            "sent_monotonic_ns": 1,
            "helper_version": "test",
            "state": state,
            "lanes": lanes,
        }
    )
    return HelperPresenceRegistry(monotonic_ns=lambda: 100).observe("session", heartbeat)


def test_projection_uses_reference_compatible_phases_and_server_owned_healthy_copy():
    assert project_live_capture_status(None).to_dict() == {
        "capture_phase": "starting",
        "status_line": "Waiting for audio capture to start.",
    }
    assert project_live_capture_status(_presence()).to_dict() == {
        "capture_phase": "recording",
        "status_line": "Capturing microphone and shared audio.",
    }


@pytest.mark.parametrize(
    ("code", "lane", "lane_state", "overall_state", "expected_text"),
    (
        (
            "browser_microphone_permission_denied",
            "microphone",
            "failed",
            "failed",
            "Allow microphone access in Chrome",
        ),
        (
            "browser_capture_request_rejected",
            "system",
            "failed",
            "failed",
            "Screen sharing did not start",
        ),
        (
            "browser_surface_audio_missing",
            "system",
            "failed",
            "failed",
            "enable Share tab audio",
        ),
        (
            "browser_track_ended",
            "system",
            "failed",
            "capturing",
            "Continuing with microphone audio",
        ),
        (
            "browser_audio_context_suspended",
            "system",
            "degraded",
            "degraded",
            "Return to this tab",
        ),
        (
            "browser_sustained_clipping",
            "microphone",
            "degraded",
            "degraded",
            "too loud",
        ),
        (
            "browser_microphone_silent",
            "microphone",
            "failed",
            "failed",
            "Settings > Privacy and security > Site settings > Microphone",
        ),
    ),
)
def test_every_browser_fact_gets_server_owned_actionable_copy(
    code: str,
    lane: str,
    lane_state: str,
    overall_state: str,
    expected_text: str,
):
    status = project_live_capture_status(
        _presence(
            state=overall_state,
            lane=lane,
            lane_state=lane_state,
            failure_code=code,
        )
    )

    assert code in BROWSER_CAPTURE_FAILURE_CODES
    assert expected_text in status.status_line


def test_single_failed_lane_keeps_recording_and_unknown_codes_use_additive_fallback():
    status = project_live_capture_status(
        _presence(
            state="capturing",
            lane="system",
            lane_state="failed",
            failure_code="future_helper_fact",
        )
    )

    assert status.to_dict() == {
        "capture_phase": "recording",
        "status_line": "Shared audio capture failed. The session is continuing.",
    }


def test_observation_registry_resets_transient_counters_only_after_accepted_audio():
    clock_values = iter((10, 20, 30, 40))
    registry = LiveCaptureObservationRegistry(monotonic_ns=lambda: next(clock_values))
    registry.create("session")

    registry.observe_accepted(
        "session",
        _observation_frame(sequence=0, silent=True, sample_count=3),
    )
    registry.observe_sequence_rejection("session", LiveLane.MICROPHONE)
    registry.observe_backpressure_rejection("session", LiveLane.MICROPHONE)
    before_recovery = registry.snapshot("session").lanes[LiveLane.MICROPHONE]

    assert before_recovery.last_server_arrival_monotonic_ns == 10
    assert before_recovery.consecutive_silent_samples == 3
    assert before_recovery.consecutive_sequence_rejections == 1
    assert before_recovery.consecutive_backpressure_rejections == 1
    assert before_recovery.last_rejection_monotonic_ns == 30

    registry.observe_accepted(
        "session",
        _observation_frame(sequence=1, silent=False, sample_count=5),
    )
    recovered = registry.snapshot("session").lanes[LiveLane.MICROPHONE]

    assert recovered.last_server_arrival_monotonic_ns == 40
    assert recovered.consecutive_silent_samples == 0
    assert recovered.consecutive_sequence_rejections == 0
    assert recovered.consecutive_backpressure_rejections == 0
    assert recovered.last_rejection_monotonic_ns == 30

    registry.release("session")
    assert "session" not in registry
    with pytest.raises(KeyError):
        registry.snapshot("session")
