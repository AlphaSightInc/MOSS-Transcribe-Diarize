from __future__ import annotations

import dataclasses
import struct

import pytest

from moss_transcribe_diarize.app.live_ingest import LiveV2StaleDeviceEpochError
from moss_transcribe_diarize.app.live_lane_contract import LiveLane, LiveV2Frame
from moss_transcribe_diarize.app.live_v2_session import LiveV2Session
from simulated_windows_capture import (
    CaptureFormat,
    CaptureLaneFailure,
    SimulatedWindowsCaptureAdapter,
)


def _values(frame: LiveV2Frame) -> tuple[int, ...]:
    return tuple(value[0] for value in struct.iter_unpack("<h", frame.pcm))


def test_windows_adapter_converts_signed_asymmetric_float_stereo_to_pcm16_mono():
    adapter = SimulatedWindowsCaptureAdapter(session_id="capture-1")
    native_format = CaptureFormat(
        sample_rate=44_100,
        channels=2,
        sample_format="float32_le",
    )
    pcm = struct.pack(
        "<8f",
        0.50,
        0.25,
        -0.50,
        -0.25,
        0.25,
        -0.75,
        -0.25,
        0.75,
    )

    frame = adapter.emit(
        lane=LiveLane.SYSTEM,
        capture_timestamp_ns=1_000_000,
        native_format=native_format,
        pcm=pcm,
    )

    assert frame.lane == LiveLane.SYSTEM
    assert frame.sequence == 0
    assert frame.device_epoch == 0
    assert frame.capture_timestamp_ns == 1_000_000
    assert frame.sample_rate == 44_100
    assert frame.sample_count == 4
    assert _values(frame) == (12_288, -12_288, -8_192, 8_192)


def test_windows_adapter_clips_float_edges_without_wraparound():
    adapter = SimulatedWindowsCaptureAdapter(session_id="capture-1")
    native_format = CaptureFormat(
        sample_rate=48_000,
        channels=1,
        sample_format="float32_le",
    )
    pcm = struct.pack("<6f", -1.25, -1.0, -0.5, 0.5, 1.0, 1.25)

    frame = adapter.emit(
        lane=LiveLane.MICROPHONE,
        capture_timestamp_ns=2_000_000,
        native_format=native_format,
        pcm=pcm,
    )

    assert _values(frame) == (-32_768, -32_768, -16_384, 16_384, 32_767, 32_767)
    assert len(frame.pcm) == frame.sample_count * 2


def test_windows_adapter_converts_interleaved_pcm16_and_keeps_lane_sequences_independent():
    adapter = SimulatedWindowsCaptureAdapter(session_id="capture-1")
    native_format = CaptureFormat(
        sample_rate=48_000,
        channels=2,
        sample_format="pcm16_le",
    )

    system_0 = adapter.emit(
        lane=LiveLane.SYSTEM,
        capture_timestamp_ns=100,
        native_format=native_format,
        pcm=struct.pack("<4h", 3_000, 1_000, -3_000, -1_000),
    )
    microphone_0 = adapter.emit(
        lane=LiveLane.MICROPHONE,
        capture_timestamp_ns=50,
        native_format=native_format,
        pcm=struct.pack("<4h", 10_000, -2_000, -10_000, 2_000),
    )
    system_1 = adapter.emit(
        lane=LiveLane.SYSTEM,
        capture_timestamp_ns=200,
        native_format=native_format,
        pcm=struct.pack("<4h", 4_000, 2_000, -4_000, -2_000),
    )

    assert (system_0.sequence, microphone_0.sequence, system_1.sequence) == (0, 0, 1)
    assert _values(system_0) == (2_000, -2_000)
    assert _values(microphone_0) == (4_000, -4_000)
    assert _values(system_1) == (3_000, -3_000)


def test_windows_adapter_preserves_opposed_lane_clocks_and_native_rates():
    adapter = SimulatedWindowsCaptureAdapter(session_id="capture-1")
    system_format = CaptureFormat(
        sample_rate=44_100,
        channels=1,
        sample_format="pcm16_le",
    )
    microphone_format = CaptureFormat(
        sample_rate=48_000,
        channels=1,
        sample_format="pcm16_le",
    )

    system = adapter.emit(
        lane=LiveLane.SYSTEM,
        capture_timestamp_ns=1_000_000_000,
        native_format=system_format,
        pcm=struct.pack("<2h", 1, 2),
    )
    microphone = adapter.emit(
        lane=LiveLane.MICROPHONE,
        capture_timestamp_ns=999_997_500,
        native_format=microphone_format,
        pcm=struct.pack("<3h", 3, 4, 5),
    )

    assert system.capture_timestamp_ns == 1_000_000_000
    assert microphone.capture_timestamp_ns == 999_997_500
    assert system.sample_rate == 44_100
    assert microphone.sample_rate == 48_000
    assert system.sample_count == 2
    assert microphone.sample_count == 3


def test_windows_adapter_device_invalidation_advances_only_that_lane_epoch_and_forces_discontinuity():
    adapter = SimulatedWindowsCaptureAdapter(session_id="capture-1")
    native_format = CaptureFormat(
        sample_rate=48_000,
        channels=1,
        sample_format="pcm16_le",
    )
    adapter.emit(
        lane=LiveLane.SYSTEM,
        capture_timestamp_ns=1_000,
        native_format=native_format,
        pcm=struct.pack("<h", 1),
    )
    adapter.emit(
        lane=LiveLane.MICROPHONE,
        capture_timestamp_ns=1_000,
        native_format=native_format,
        pcm=struct.pack("<h", 2),
    )

    assert adapter.device_invalidated(LiveLane.SYSTEM) == 1
    system = adapter.emit(
        lane=LiveLane.SYSTEM,
        capture_timestamp_ns=2_000,
        native_format=native_format,
        pcm=struct.pack("<h", 3),
    )
    microphone = adapter.emit(
        lane=LiveLane.MICROPHONE,
        capture_timestamp_ns=2_000,
        native_format=native_format,
        pcm=struct.pack("<h", 4),
    )

    assert system.sequence == 1
    assert system.device_epoch == 1
    assert system.discontinuity is True
    assert microphone.sequence == 1
    assert microphone.device_epoch == 0
    assert microphone.discontinuity is False


def test_windows_adapter_new_epoch_enters_ingress_and_stale_epoch_rejects_without_mutation():
    adapter = SimulatedWindowsCaptureAdapter(session_id="capture-1")
    source = LiveV2Session(max_retained_samples=100)
    native_format = CaptureFormat(
        sample_rate=48_000,
        channels=1,
        sample_format="pcm16_le",
    )
    source.accept(
        adapter.emit(
            lane=LiveLane.SYSTEM,
            capture_timestamp_ns=1_000,
            native_format=native_format,
            pcm=struct.pack("<h", 1),
        )
    )
    adapter.device_invalidated(LiveLane.SYSTEM)
    source.accept(
        adapter.emit(
            lane=LiveLane.SYSTEM,
            capture_timestamp_ns=2_000,
            native_format=native_format,
            pcm=struct.pack("<h", 2),
        )
    )
    before = source.snapshot().to_dict()

    with pytest.raises(LiveV2StaleDeviceEpochError):
        source.accept(
            LiveV2Frame(
                lane=LiveLane.SYSTEM,
                sequence=2,
                capture_timestamp_ns=3_000,
                device_epoch=0,
                silent=False,
                discontinuity=False,
                sample_rate=48_000,
                sample_count=1,
                pcm=struct.pack("<h", 3),
            )
        )

    assert source.snapshot().to_dict() == before


def test_windows_adapter_native_silence_zeroes_pcm_without_conflating_failure():
    adapter = SimulatedWindowsCaptureAdapter(session_id="capture-1")
    native_format = CaptureFormat(
        sample_rate=48_000,
        channels=1,
        sample_format="pcm16_le",
    )

    frame = adapter.emit(
        lane=LiveLane.MICROPHONE,
        capture_timestamp_ns=1_000,
        native_format=native_format,
        pcm=struct.pack("<3h", 30_000, -30_000, 1_234),
        silent=True,
    )

    assert frame.silent is True
    assert _values(frame) == (0, 0, 0)
    assert frame.discontinuity is False


def test_windows_adapter_emits_immutable_typed_lane_failure():
    adapter = SimulatedWindowsCaptureAdapter(session_id="capture-1")

    failure = adapter.fail_lane(LiveLane.MICROPHONE, "windows_device_invalidated")

    assert isinstance(failure, CaptureLaneFailure)
    assert failure.session_id == "capture-1"
    assert failure.lane == LiveLane.MICROPHONE
    assert failure.code == "windows_device_invalidated"
    assert failure.device_epoch == 0
    assert failure.sequence == 0
    with pytest.raises(dataclasses.FrozenInstanceError):
        failure.code = "different"  # type: ignore[misc]
