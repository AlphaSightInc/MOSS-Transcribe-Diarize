from __future__ import annotations

import asyncio
import math
import struct
from types import SimpleNamespace

import pytest

from moss_transcribe_diarize.app.live_lane_contract import LiveLane, LiveV2Frame
from moss_transcribe_diarize.app.live_mixer import (
    LiveCompatibilityMixer,
    LiveCompatibilityMixerRegistry,
    LiveMixIntegrityError,
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

    def accept_frame(
        self,
        _session_id: str,
        frame,
        *,
        retryable_queue_backpressure: bool = False,
    ):
        assert retryable_queue_backpressure is True
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


def test_failed_lane_contributes_silence_while_sealed_peer_admits_and_accounts():
    source = LiveV2Session(max_retained_samples=20_000)
    source.accept(_frame(LiveLane.SYSTEM, 0, 0, 48_000, 480, 8_192))
    source.accept(_frame(LiveLane.SYSTEM, 1, 10_000_000, 48_000, 480, 8_192))
    source.fail_lane(LiveLane.MICROPHONE, "windows_device_invalidated")

    result = LiveCompatibilityMixer().admit_available(
        "session-1",
        source,
        _Runtime(),
        final=False,
    )

    assert result is not None
    assert set(_pcm_values(result.frame.pcm)) == {_encoded_sample(8_192)}
    assert result.diagnostics.overlap_samples == 0
    assert result.diagnostics.source_watermarks == {LiveLane.SYSTEM: 0}
    assert result.diagnostics.silent_samples[LiveLane.MICROPHONE] == result.frame.sample_count
    lanes = source.snapshot().to_dict()["lanes"]
    assert lanes["system"]["accounted_samples"] == 480
    assert lanes["microphone"]["health"] == "failed"
    assert lanes["microphone"]["accounted_samples"] == 0
    assert lanes["microphone"]["failure_code"] == "windows_device_invalidated"

    stopped = asyncio.run(source.stop(0.0)).to_dict()
    assert stopped["status"] == "failed"
    assert stopped["terminal_reason"] == "windows_device_invalidated"


def test_failed_lane_admission_rejection_rolls_back_peer_accounting_and_cursor():
    source = LiveV2Session(max_retained_samples=20_000)
    source.accept(_frame(LiveLane.SYSTEM, 0, 0, 48_000, 480, 8_192))
    source.accept(_frame(LiveLane.SYSTEM, 1, 10_000_000, 48_000, 480, 8_192))
    source.fail_lane(LiveLane.MICROPHONE, "windows_device_invalidated")
    mixer = LiveCompatibilityMixer()
    before = (
        source.snapshot().to_dict(),
        source.retained_frames(),
    )

    with pytest.raises(RuntimeError, match="reject mono admission"):
        mixer.admit_available("session-1", source, _Runtime(reject=True), final=False)

    assert (source.snapshot().to_dict(), source.retained_frames()) == before
    retry = mixer.admit_available("session-1", source, _Runtime(), final=False)
    assert retry is not None
    assert retry.diagnostics.source_watermarks == {LiveLane.SYSTEM: 0}


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


def test_stalled_active_lane_is_gap_sealed_in_bounded_chunks_and_can_resume():
    source = LiveV2Session(max_retained_samples=20_000)
    mixer = LiveCompatibilityMixer(max_output_samples=160)
    runtime = _Runtime()
    for sequence in range(2):
        timestamp_ns = sequence * 10_000_000
        source.accept(
            _frame(LiveLane.SYSTEM, sequence, timestamp_ns, 16_000, 160, 8_192)
        )
        source.accept(
            _frame(LiveLane.MICROPHONE, sequence, timestamp_ns, 16_000, 160, 4_096)
        )

    first = mixer.admit_available("session-1", source, runtime, final=False)
    assert first is not None
    assert first.frame.sample_count == 160

    stalled_results = []
    for sequence in range(2, 8):
        source.accept(
            _frame(
                LiveLane.SYSTEM,
                sequence,
                sequence * 10_000_000,
                16_000,
                160,
                8_192,
            )
        )
        result = mixer.admit_available("session-1", source, runtime, final=False)
        if result is not None:
            stalled_results.append(result)

    assert stalled_results
    assert all(result.frame.sample_count <= 160 for result in stalled_results)
    assert any(
        result.diagnostics.gap_samples[LiveLane.MICROPHONE] > 0
        for result in stalled_results
    )
    stalled_snapshot = source.snapshot().to_dict()["lanes"]
    assert stalled_snapshot["system"]["retained_samples"] < 20_000

    source.accept(
        _frame(
            LiveLane.MICROPHONE,
            2,
            80_000_000,
            16_000,
            160,
            4_096,
            discontinuity=True,
        )
    )
    mixer.admit_available("session-1", source, runtime, final=False)
    source.accept(
        _frame(
            LiveLane.MICROPHONE,
            3,
            90_000_000,
            16_000,
            160,
            4_096,
        )
    )
    mixer.admit_available("session-1", source, runtime, final=False)
    source.accept(
        _frame(LiveLane.SYSTEM, 8, 80_000_000, 16_000, 160, 8_192)
    )
    mixer.admit_available("session-1", source, runtime, final=False)
    source.accept(
        _frame(LiveLane.SYSTEM, 9, 90_000_000, 16_000, 160, 8_192)
    )
    recovered = mixer.admit_available("session-1", source, runtime, final=False)

    assert recovered is not None
    assert recovered.frame.sample_count <= 160
    assert recovered.diagnostics.silent_samples[LiveLane.MICROPHONE] == 0
    assert recovered.diagnostics.gap_samples[LiveLane.MICROPHONE] == 0


def test_final_flush_drains_a_one_lane_backlog_in_bounded_chunks():
    source = LiveV2Session(max_retained_samples=20_000)
    source.accept(_frame(LiveLane.MICROPHONE, 0, 0, 16_000, 160, 0, silent=True))
    for sequence in range(8):
        source.accept(
            _frame(
                LiveLane.SYSTEM,
                sequence,
                sequence * 10_000_000,
                16_000,
                160,
                8_192,
            )
        )
    mixer = LiveCompatibilityMixer(max_output_samples=160)
    runtime = _Runtime()
    chunks = []

    while source.snapshot().to_dict()["lanes"]["system"]["retained_samples"]:
        result = mixer.admit_available("session-1", source, runtime, final=True)
        assert result is not None
        chunks.append(result)

    assert len(chunks) == 8
    assert all(result.frame.sample_count == 160 for result in chunks)
    assert sum(
        result.diagnostics.gap_samples[LiveLane.MICROPHONE]
        for result in chunks
    ) == 7 * 160
    assert source.snapshot().to_dict()["lanes"]["system"]["accounted_samples"] == 8 * 160


def test_final_missing_source_is_gap_sealed_without_mutating_absent_lane():
    source = LiveV2Session(max_retained_samples=20_000)
    source.accept(_frame(LiveLane.SYSTEM, 0, 0, 48_000, 480, 8_192))

    assert LiveCompatibilityMixer().admit_available(
        "session-1",
        source,
        _Runtime(),
        final=False,
    ) is None

    result = LiveCompatibilityMixer().admit_available(
        "session-1", source, _Runtime(), final=True
    )

    assert result is not None
    assert result.frame.sample_count == 160
    assert result.diagnostics.gap_samples[LiveLane.MICROPHONE] == 160
    assert source.snapshot().to_dict()["lanes"]["microphone"]["accounted_samples"] == 0


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


def test_partial_timestamp_stretched_frame_waits_for_complete_source_accounting():
    # A supported timestamp interval is slightly longer than its nominal samples.
    # The first bounded output chunk cannot yet account for either whole lane frame.
    source = LiveV2Session(max_retained_samples=960_000)
    for lane in (LiveLane.SYSTEM, LiveLane.MICROPHONE):
        source.accept(_frame(lane, 0, 0, 16_000, 8_000, 8_192))
        source.accept(_frame(lane, 1, 500_500_000, 16_000, 8_000, 8_192))
    before = source.snapshot().to_dict()
    runtime = _Runtime()
    mixer = LiveCompatibilityMixer(max_output_samples=8_000)

    first = mixer.admit_available('session-1', source, runtime)
    assert first is not None and first.frame.sample_count == 8_000
    assert first.diagnostics.source_watermarks == {}
    assert source.snapshot().to_dict() == before

    remainder = mixer.admit_available('session-1', source, runtime)
    assert remainder is not None and remainder.frame.sample_count == 8
    assert remainder.diagnostics.source_watermarks == {LiveLane.SYSTEM: 0, LiveLane.MICROPHONE: 0}
    assert [f.sequence for f in runtime.frames] == [0, 1]
    for lane in ('system', 'microphone'):
        assert source.snapshot().to_dict()['lanes'][lane]['accounted_samples'] == 8_000

    final = mixer.admit_available('session-1', source, runtime, final=True)
    assert final is not None and final.frame.sample_count == 8_000
    assert mixer.admit_available('session-1', source, runtime, final=True) is None
    assert [f.sequence for f in runtime.frames] == [0, 1, 2]


@pytest.mark.parametrize('audible_lane', [LiveLane.SYSTEM, LiveLane.MICROPHONE])
def test_single_source_analysis_keeps_original_level_without_changing_decoder_pcm(audible_lane):
    source = LiveV2Session(max_retained_samples=20000)
    values = (-32768, -1234, 0, 1234, 32767) * 32
    for lane in LiveLane:
        for sequence in range(2):
            source.accept(_values_frame(lane, sequence, sequence * 10000000, 16000,
                values if lane == audible_lane else (0,) * 160, silent=lane != audible_lane))
    result = LiveCompatibilityMixer().admit_available('test', source, _Runtime())
    assert _pcm_values(result.frame.analysis_pcm) == values
    assert _pcm_values(result.frame.pcm) == tuple(_encoded_sample(x) for x in values)


def test_two_audible_sources_analysis_preserves_existing_mix():
    result = LiveCompatibilityMixer().admit_available('test', _source_pair(), _Runtime())
    assert result.frame.analysis_pcm is None
    assert _pcm_values(result.frame.pcm) == (_encoded_sample(16384),) * 160


def test_observed_frame_ends_release_canonical_boundary_without_changing_two_lane_alignment():
    from dataclasses import replace
    timestamps = (0, 500000000, 1000000000, 1500000000, 2000000000, 2500500000)
    ends = (*timestamps[1:], 3000500000)
    def run(explicit):
        source = LiveV2Session(max_retained_samples=960000)
        mixer, runtime = LiveCompatibilityMixer(max_output_samples=8000), _Runtime()
        admitted = []
        for sequence, timestamp in enumerate(timestamps):
            for lane in LiveLane:
                values = tuple(1000 + i % 6000 if lane == LiveLane.SYSTEM else -700 + i % 1200 for i in range(8000))
                frame = _values_frame(lane, sequence, timestamp, 16000, values)
                if explicit:
                    frame = replace(frame, capture_end_timestamp_ns=ends[sequence])
                source.accept(frame)
                if explicit:
                    while mixer.admit_available('test', source, runtime) is not None:
                        pass
            while mixer.admit_available('test', source, runtime) is not None:
                pass
            admitted.append(sum(frame.sample_count for frame in runtime.frames))
        while mixer.admit_available('test', source, runtime, final=True) is not None:
            pass
        assert [frame.sequence for frame in runtime.frames] == list(range(len(runtime.frames)))
        return b''.join(frame.pcm for frame in runtime.frames), admitted
    baseline, before = run(False)
    actual, after = run(True)
    assert actual == baseline
    assert before[4] == 32000
    assert after[4] == 40008
    assert after[-1] == 48008


def test_explicit_frame_end_cannot_be_rewritten_after_source_accounting():
    from dataclasses import replace
    source = LiveV2Session(max_retained_samples=20000)
    mixer, runtime = LiveCompatibilityMixer(), _Runtime()
    for lane in LiveLane:
        source.accept(replace(_frame(lane, 0, 0, 16000, 8000, 1000), capture_end_timestamp_ns=500000000))
    assert mixer.admit_available('test', source, runtime) is not None
    assert not source.retained_frames(LiveLane.SYSTEM)
    with pytest.raises(ValueError, match='overlaps an explicitly sealed frame'):
        source.accept(_frame(LiveLane.SYSTEM, 1, 499500000, 16000, 8000, 1000))
    source.accept(_frame(LiveLane.SYSTEM, 1, 500000000, 16000, 8000, 1000))
