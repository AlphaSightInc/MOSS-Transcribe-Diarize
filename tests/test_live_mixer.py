from __future__ import annotations

import math
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


def _values_frame(
    lane: LiveLane,
    sequence: int,
    timestamp_ns: int,
    rate: int,
    values: tuple[int, ...],
    *,
    silent: bool = False,
    discontinuity: bool = False,
) -> LiveV2Frame:
    pcm = b"".join(struct.pack("<h", value) for value in values)
    return LiveV2Frame(
        lane=lane,
        sequence=sequence,
        capture_timestamp_ns=timestamp_ns,
        device_epoch=0,
        silent=silent,
        discontinuity=discontinuity,
        sample_rate=rate,
        sample_count=len(values),
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
    def __init__(self, *, reject: bool = False, next_sequence: int = 0):
        self.reject = reject
        self.next_sequence = next_sequence
        self.frames = []

    def snapshot(self, _session_id: str):
        return SimpleNamespace(
            session=SimpleNamespace(
                next_frame_sequence=self.next_sequence + len(self.frames),
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


def _pcm_values(pcm: bytes) -> tuple[int, ...]:
    return tuple(value[0] for value in struct.iter_unpack("<h", pcm))


def _encoded_sample(source_value: float) -> int:
    gain = 10 ** (-6 / 20)
    return int((source_value / 32768.0) * gain * 32767.0)


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


def test_mixer_uses_successor_capture_anchor_instead_of_nominal_sample_rate():
    source = LiveV2Session(max_retained_samples=20_000)
    system_values = tuple(index * 40 for index in range(480))
    source.accept(_values_frame(LiveLane.SYSTEM, 0, 0, 48_000, system_values))
    source.accept(_frame(LiveLane.SYSTEM, 1, 20_000_000, 48_000, 480, 0))
    source.accept(
        _frame(
            LiveLane.MICROPHONE,
            0,
            0,
            44_100,
            441,
            30_000,
            silent=True,
        )
    )
    source.accept(
        _frame(
            LiveLane.MICROPHONE,
            1,
            20_000_000,
            44_100,
            441,
            30_000,
            silent=True,
        )
    )

    result = LiveCompatibilityMixer().admit_available(
        "session-1",
        source,
        _Runtime(next_sequence=7),
        final=False,
    )

    assert result is not None
    assert result.frame.sequence == 7
    values = _pcm_values(result.frame.pcm)
    assert result.frame.sample_count == 320
    assert values[0] == 0
    assert values[160] == _encoded_sample(system_values[240])
    assert values[160] != _encoded_sample(system_values[-1])


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


def test_mixer_preserves_whole_source_frame_until_entire_interval_is_admitted():
    source = LiveV2Session(max_retained_samples=20_000)
    source.accept(_frame(LiveLane.SYSTEM, 0, 0, 48_000, 480, 8_192))
    source.accept(_frame(LiveLane.SYSTEM, 1, 20_000_000, 48_000, 480, 8_192))
    source.accept(_frame(LiveLane.MICROPHONE, 0, 0, 44_100, 441, 8_192))
    source.accept(_frame(LiveLane.MICROPHONE, 1, 10_000_000, 44_100, 441, 8_192))

    result = LiveCompatibilityMixer().admit_available(
        "session-1",
        source,
        _Runtime(),
        final=False,
    )

    assert result is not None
    assert result.frame.sample_count == 160
    assert result.diagnostics.source_watermarks == {LiveLane.MICROPHONE: 0}
    snapshot = source.snapshot().to_dict()["lanes"]
    assert snapshot["system"]["accounted_samples"] == 0
    assert snapshot["system"]["retained_samples"] == 960
    assert snapshot["microphone"]["accounted_samples"] == 441
    assert snapshot["microphone"]["retained_samples"] == 441


def test_mixer_zero_fills_discontinuity_gap_and_reports_gap_samples():
    source = LiveV2Session(max_retained_samples=20_000)
    source.accept(_frame(LiveLane.SYSTEM, 0, 0, 48_000, 480, 8_192))
    source.accept(
        _frame(
            LiveLane.SYSTEM,
            1,
            20_000_000,
            48_000,
            480,
            8_192,
            discontinuity=True,
        )
    )
    source.accept(_frame(LiveLane.SYSTEM, 2, 30_000_000, 48_000, 480, 8_192))
    source.accept(_frame(LiveLane.MICROPHONE, 0, 0, 44_100, 441, 0, silent=True))
    source.accept(_frame(LiveLane.MICROPHONE, 1, 30_000_000, 44_100, 441, 0, silent=True))

    result = LiveCompatibilityMixer().admit_available(
        "session-1",
        source,
        _Runtime(),
        final=False,
    )

    assert result is not None
    assert result.frame.sample_count == 480
    assert result.diagnostics.gap_samples[LiveLane.SYSTEM] == 160
    assert max(abs(value) for value in _pcm_values(result.frame.pcm)[160:320]) == 0


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


def test_limiter_uses_registered_tanh_curve_above_098_not_hard_clip():
    source = LiveV2Session(max_retained_samples=20_000)
    for lane in (LiveLane.SYSTEM, LiveLane.MICROPHONE):
        source.accept(_frame(lane, 0, 0, 16_000, 160, 32_767))
        source.accept(_frame(lane, 1, 10_000_000, 16_000, 160, 32_767))

    result = LiveCompatibilityMixer().admit_available(
        "session-1",
        source,
        _Runtime(),
        final=False,
    )

    assert result is not None
    mixed = (32_767 / 32768.0) * (10 ** (-6 / 20)) * 2
    expected = int(
        (
            0.98
            + 0.02 * math.tanh((abs(mixed) - 0.98) / 0.02)
        )
        * 32767.0
    )
    assert result.diagnostics.overlap_samples == result.frame.sample_count
    assert result.diagnostics.limited_samples == result.frame.sample_count
    assert set(_pcm_values(result.frame.pcm)) == {expected}
    assert expected not in {int(0.98 * 32767.0), 32767}


def test_final_flush_zero_fills_bounded_tail_to_latest_sealed_frontier():
    source = LiveV2Session(max_retained_samples=20_000)
    source.accept(_frame(LiveLane.SYSTEM, 0, 0, 48_000, 480, 8_192))
    source.accept(_frame(LiveLane.MICROPHONE, 0, 0, 44_100, 882, 0, silent=True))

    result = LiveCompatibilityMixer().admit_available(
        "session-1",
        source,
        _Runtime(),
        final=True,
    )

    assert result is not None
    assert result.frame.sample_count == 320
    assert result.diagnostics.gap_samples[LiveLane.SYSTEM] == 160
    assert max(abs(value) for value in _pcm_values(result.frame.pcm)[160:]) == 0


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
