from __future__ import annotations

import struct
from types import SimpleNamespace

import pytest

from moss_transcribe_diarize.app.live_lane_contract import LiveLane, LiveV2Frame
from moss_transcribe_diarize.app.live_mixer import (
    LiveCompatibilityMixer,
    LiveCompatibilityMixerRegistry,
    LiveMixIntegrityError,
    LiveMixSourceMissingError,
)
from moss_transcribe_diarize.app.live_v2_session import LiveV2Session


def _frame(
    lane: LiveLane,
    sequence: int,
    timestamp_ns: int,
    rate: int,
    count: int,
    value: int,
    *,
    silent: bool = False,
    discontinuity: bool = False,
) -> LiveV2Frame:
    pcm = b"".join(struct.pack("<h", value) for _ in range(count))
    return LiveV2Frame(
        lane=lane,
        sequence=sequence,
        capture_timestamp_ns=timestamp_ns,
        device_epoch=0,
        silent=silent,
        discontinuity=discontinuity,
        sample_rate=rate,
        sample_count=count,
        pcm=pcm,
    )


def _source_pair(*, microphone_silent: bool = False) -> LiveV2Session:
    source = LiveV2Session(max_retained_samples=20_000)
    source.accept(_frame(LiveLane.SYSTEM, 0, 0, 48_000, 480, 8_192))
    source.accept(_frame(LiveLane.SYSTEM, 1, 10_000_000, 48_000, 480, 8_192))
    source.accept(
        _frame(
            LiveLane.MICROPHONE,
            0,
            0,
            44_100,
            441,
            30_000 if microphone_silent else 8_192,
            silent=microphone_silent,
        )
    )
    source.accept(
        _frame(
            LiveLane.MICROPHONE,
            1,
            10_000_000,
            44_100,
            441,
            30_000 if microphone_silent else 8_192,
            silent=microphone_silent,
        )
    )
    return source


class _Runtime:
    def __init__(self, *, reject: bool = False):
        self.reject = reject
        self.frames = []

    def snapshot(self, _session_id: str):
        return SimpleNamespace(
            session=SimpleNamespace(
                next_frame_sequence=len(self.frames),
                version=len(self.frames),
            )
        )

    def accept_frame(self, _session_id: str, frame):
        if self.reject:
            raise RuntimeError("reject mono admission")
        self.frames.append(frame)
        return SimpleNamespace(
            queued_item_ids=(42,),
            snapshot=self.snapshot(_session_id),
        )


def test_mixer_emits_16k_mono_from_capture_timestamp_anchors_and_accounts_after_admission():
    source = _source_pair()
    runtime = _Runtime()

    result = LiveCompatibilityMixer().admit_available(
        "session-1",
        source,
        runtime,
        final=False,
    )

    assert result is not None
    assert result.frame.sequence == 0
    assert result.frame.sample_rate == 16_000
    assert result.frame.sample_count in {159, 160}
    assert len(result.frame.pcm) == result.frame.sample_count * 2
    assert result.queued_item_ids == (42,)
    assert result.diagnostics.source_watermarks == {
        LiveLane.SYSTEM: 0,
        LiveLane.MICROPHONE: 0,
    }
    snapshot = source.snapshot().to_dict()["lanes"]
    assert snapshot["system"]["accounted_samples"] == 480
    assert snapshot["microphone"]["accounted_samples"] == 441
    assert [item.frame.sequence for item in source.retained_frames(LiveLane.SYSTEM)] == [1]
    assert [item.frame.sequence for item in source.retained_frames(LiveLane.MICROPHONE)] == [1]


def test_mixer_rolls_back_source_and_cursor_when_mono_admission_rejects_then_retries_once():
    source = _source_pair()
    mixer = LiveCompatibilityMixer()
    before = (
        source.snapshot().to_dict(),
        source.retained_frames(),
    )

    with pytest.raises(RuntimeError, match="reject mono admission"):
        mixer.admit_available("session-1", source, _Runtime(reject=True), final=False)

    assert (source.snapshot().to_dict(), source.retained_frames()) == before
    retry_runtime = _Runtime()
    retry = mixer.admit_available("session-1", source, retry_runtime, final=False)
    assert retry is not None
    assert retry.frame.sequence == 0
    assert retry_runtime.frames == [retry.frame]


def test_silent_flag_ignores_nonzero_pcm_before_overlap_mix():
    result = LiveCompatibilityMixer().admit_available(
        "session-1",
        _source_pair(microphone_silent=True),
        _Runtime(),
        final=False,
    )

    assert result is not None
    peak = max(abs(value[0]) for value in struct.iter_unpack("<h", result.frame.pcm))
    assert 3_900 <= peak <= 4_300
    assert result.diagnostics.silent_samples[LiveLane.MICROPHONE] == result.frame.sample_count


def test_final_missing_source_fails_typed_without_mutating_source():
    source = LiveV2Session(max_retained_samples=20_000)
    source.accept(_frame(LiveLane.SYSTEM, 0, 0, 48_000, 480, 8_192))
    before = source.snapshot().to_dict()

    with pytest.raises(LiveMixSourceMissingError):
        LiveCompatibilityMixer().admit_available("session-1", source, _Runtime(), final=True)

    assert source.snapshot().to_dict() == before


def test_non_advancing_continuous_clock_fails_before_downstream_admission():
    source = LiveV2Session(max_retained_samples=20_000)
    source.accept(_frame(LiveLane.SYSTEM, 0, 1_000, 48_000, 480, 1))
    source.accept(_frame(LiveLane.SYSTEM, 1, 1_000, 48_000, 480, 1))
    source.accept(_frame(LiveLane.MICROPHONE, 0, 0, 44_100, 441, 1))
    source.accept(_frame(LiveLane.MICROPHONE, 1, 10_000_000, 44_100, 441, 1))
    runtime = _Runtime()

    with pytest.raises(LiveMixIntegrityError, match="must advance"):
        LiveCompatibilityMixer().admit_available("session-1", source, runtime, final=False)

    assert runtime.frames == []


def test_registry_create_get_release_is_exact():
    registry = LiveCompatibilityMixerRegistry()
    created = registry.create("session-1")

    assert registry.get("session-1") is created
    assert registry.release("session-1") is created
    with pytest.raises(KeyError):
        registry.get("session-1")
