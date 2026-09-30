from __future__ import annotations

import pytest

from moss_transcribe_diarize.app.live_capture_status import (
    BROWSER_CAPTURE_FAILURE_CODES,
    LiveCaptureHealthPolicy,
    LiveCaptureObservationRegistry,
    project_live_capture_status,
)
from moss_transcribe_diarize.app.live_v2_session import LiveV2Session
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


def test_projection_uses_reference_compatible_phases_and_says_nothing_when_healthy():
    # Q6: progress states are carried by the browser's pill and buttons, never by a line.
    assert project_live_capture_status(None).to_dict() == {
        "capture_phase": "starting",
        "status_line": "",
    }
    assert project_live_capture_status(_presence()).to_dict() == {
        "capture_phase": "recording",
        "status_line": "",
    }
    for state in ("starting", "recovering", "degraded"):
        assert project_live_capture_status(_presence(state=state)).status_line == ""


@pytest.mark.parametrize(
    ("session_status", "lane_failures", "expected_phase", "expected_line"),
    (
        ("closed", None, "stopped", ""),
        ("aborted", None, "failed", ""),
        ("failed", None, "failed", ""),
        (
            "closed",
            {"microphone": "browser_track_ended"},
            "failed",
            "Microphone stopped.",
        ),
        (
            "failed",
            {"system": "browser_track_ended"},
            "failed",
            "Shared audio stopped.",
        ),
    ),
)
def test_terminal_session_state_precedes_nonterminal_capture_facts(
    session_status: str,
    lane_failures: dict[str, str] | None,
    expected_phase: str,
    expected_line: str,
):
    status = project_live_capture_status(
        _presence(),
        terminal_session_status=session_status,
        terminal_lane_failures=lane_failures,
    )

    assert status.to_dict() == {
        "capture_phase": expected_phase,
        "status_line": expected_line,
    }


@pytest.mark.parametrize(
    ("code", "lane", "lane_state", "overall_state", "expected_text"),
    (
        (
            "browser_microphone_permission_denied",
            "microphone",
            "failed",
            "failed",
            "Microphone blocked — allow it in Chrome site settings.",
        ),
        (
            "browser_capture_request_rejected",
            "system",
            "failed",
            "failed",
            "Sharing did not start.",
        ),
        (
            "browser_surface_audio_missing",
            "system",
            "failed",
            "failed",
            "No audio in that share — choose a tab and turn on Share tab audio.",
        ),
        (
            "browser_track_ended",
            "system",
            "failed",
            "capturing",
            "Shared audio stopped — stop and start a new recording to include it.",
        ),
        (
            "browser_audio_context_suspended",
            "system",
            "degraded",
            "degraded",
            "Audio paused by the browser — stop and start a new recording.",
        ),
        (
            "browser_sustained_clipping",
            "microphone",
            "degraded",
            "degraded",
            "Microphone too loud — lower it.",
        ),
        (
            "browser_microphone_silent",
            "microphone",
            "failed",
            "failed",
            "No microphone sound — check the input in Chrome site settings.",
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
    assert status.status_line == expected_text


def test_status_copy_never_carries_raw_codes_or_the_doubled_audio_label():
    for code in BROWSER_CAPTURE_FAILURE_CODES:
        for lane in ("microphone", "system"):
            for session_status in (None, "closed"):
                line = project_live_capture_status(
                    _presence(state="capturing", lane=lane, lane_state="failed", failure_code=code),
                    terminal_session_status=session_status,
                    terminal_lane_failures=None if session_status is None else {lane: code},
                ).status_line
                assert "_" not in line and "audio audio" not in line, (code, lane, line)


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
        "status_line": "Shared audio stopped — stop and start a new recording to include it.",
    }
    degraded = project_live_capture_status(
        _presence(state="capturing", lane="system", lane_state="degraded",
                  failure_code="future_helper_fact")
    )
    assert degraded.status_line == ""


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


@pytest.mark.parametrize(
    ("condition", "expected_line"),
    (
        ("sequence", "Reconnecting — keep this tab open."),
        ("stale", "Reconnecting — keep this tab open."),
        ("backpressure", ""),
        ("silence", ""),
    ),
)
def test_server_observations_map_to_k4_or_nothing(condition: str, expected_line: str):
    clock = [0]
    registry = LiveCaptureObservationRegistry(monotonic_ns=lambda: clock[0])
    registry.create("session")
    v2 = LiveV2Session(max_retained_samples=1_000)
    for lane in LiveLane:
        frame = LiveV2Frame(
            lane=lane, sequence=0, capture_timestamp_ns=0, device_epoch=0,
            silent=condition == "silence" and lane == LiveLane.SYSTEM, discontinuity=False,
            sample_rate=4, sample_count=16, pcm=b"\1\0" * 16,
        )
        v2.accept(frame)
        registry.observe_accepted("session", frame)
    for _ in range(4):
        if condition == "sequence":
            registry.observe_sequence_rejection("session", LiveLane.MICROPHONE)
        if condition == "backpressure":
            registry.observe_backpressure_rejection("session", LiveLane.MICROPHONE)
    now = 10_000_000_000 if condition == "stale" else 0

    status = project_live_capture_status(
        _presence(),
        v2_session=v2.snapshot(),
        observations=registry.snapshot("session"),
        policy=LiveCaptureHealthPolicy(frame_samples=4, sample_rate=4),
        monotonic_ns=lambda: now,
    )

    assert status.to_dict() == {"capture_phase": "recording", "status_line": expected_line}
