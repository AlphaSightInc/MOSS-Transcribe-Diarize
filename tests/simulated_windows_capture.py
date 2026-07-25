from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from moss_transcribe_diarize.app.live_lane_contract import LiveLane, LiveV2Frame


@dataclass(frozen=True, slots=True)
class CaptureFormat:
    sample_rate: int
    channels: int
    sample_format: str

    def __post_init__(self) -> None:
        _positive_int(self.sample_rate, "sample_rate")
        _positive_int(self.channels, "channels")
        if self.sample_format not in {"float32_le", "pcm16_le"}:
            raise ValueError("sample_format must be float32_le or pcm16_le.")


@dataclass(frozen=True, slots=True)
class CaptureLaneFailure:
    session_id: str
    lane: LiveLane
    code: str
    device_epoch: int
    sequence: int

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not self.session_id:
            raise ValueError("session_id must be a non-empty string.")
        _lane(self.lane)
        if not isinstance(self.code, str) or not self.code:
            raise ValueError("code must be a non-empty string.")
        _non_negative_int(self.device_epoch, "device_epoch")
        _non_negative_int(self.sequence, "sequence")


@dataclass(slots=True)
class _LaneState:
    sequence: int = 0
    device_epoch: int = 0
    force_discontinuity: bool = False
    last_timestamp_ns: int | None = None
    failed_code: str | None = None


class SimulatedWindowsCaptureAdapter:
    """Test-only adapter that shapes native capture callbacks into LiveV2Frame."""

    def __init__(self, *, session_id: str):
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id must be a non-empty string.")
        self.session_id = session_id
        self._lanes = {lane: _LaneState() for lane in LiveLane}

    def emit(
        self,
        *,
        lane: LiveLane,
        capture_timestamp_ns: int,
        native_format: CaptureFormat,
        pcm: bytes,
        silent: bool = False,
        discontinuity: bool = False,
    ) -> LiveV2Frame:
        lane = _lane(lane)
        _non_negative_int(capture_timestamp_ns, "capture_timestamp_ns")
        if not isinstance(native_format, CaptureFormat):
            raise ValueError("native_format must be CaptureFormat.")
        if not isinstance(pcm, bytes):
            raise ValueError("pcm must be bytes.")
        if not isinstance(silent, bool):
            raise ValueError("silent must be a boolean.")
        if not isinstance(discontinuity, bool):
            raise ValueError("discontinuity must be a boolean.")

        state = self._lanes[lane]
        if state.failed_code is not None:
            raise ValueError(f"{lane.value} lane already failed.")
        if (
            state.last_timestamp_ns is not None
            and capture_timestamp_ns < state.last_timestamp_ns
        ):
            raise ValueError("capture_timestamp_ns must be monotonic per lane.")

        samples = _native_to_pcm16(native_format, pcm)
        if silent:
            samples = (0,) * len(samples)
        frame = LiveV2Frame(
            lane=lane,
            sequence=state.sequence,
            capture_timestamp_ns=capture_timestamp_ns,
            device_epoch=state.device_epoch,
            silent=silent,
            discontinuity=discontinuity or state.force_discontinuity,
            sample_rate=native_format.sample_rate,
            sample_count=len(samples),
            pcm=struct.pack("<" + "h" * len(samples), *samples),
        )
        state.sequence += 1
        state.force_discontinuity = False
        state.last_timestamp_ns = capture_timestamp_ns
        return frame

    def device_invalidated(self, lane: LiveLane) -> int:
        lane = _lane(lane)
        state = self._lanes[lane]
        if state.failed_code is not None:
            raise ValueError(f"{lane.value} lane already failed.")
        state.device_epoch += 1
        state.force_discontinuity = True
        return state.device_epoch

    def fail_lane(self, lane: LiveLane, code: str) -> CaptureLaneFailure:
        lane = _lane(lane)
        if not isinstance(code, str) or not code:
            raise ValueError("code must be a non-empty string.")
        state = self._lanes[lane]
        if state.failed_code is not None and state.failed_code != code:
            raise ValueError(f"{lane.value} lane already failed.")
        state.failed_code = code
        return CaptureLaneFailure(
            session_id=self.session_id,
            lane=lane,
            code=code,
            device_epoch=state.device_epoch,
            sequence=state.sequence,
        )


def _native_to_pcm16(native_format: CaptureFormat, pcm: bytes) -> tuple[int, ...]:
    bytes_per_sample = 4 if native_format.sample_format == "float32_le" else 2
    frame_size = native_format.channels * bytes_per_sample
    if len(pcm) % frame_size:
        raise ValueError("pcm length must align to native frame size.")

    sample_count = len(pcm) // frame_size
    samples: list[int] = []
    if native_format.sample_format == "float32_le":
        values = struct.unpack("<" + "f" * (sample_count * native_format.channels), pcm)
        for index in range(sample_count):
            start = index * native_format.channels
            samples.append(
                _float_to_pcm16(
                    sum(values[start : start + native_format.channels])
                    / native_format.channels
                )
            )
        return tuple(samples)

    values = struct.unpack("<" + "h" * (sample_count * native_format.channels), pcm)
    for index in range(sample_count):
        start = index * native_format.channels
        samples.append(
            _round_half_away_from_zero(
                sum(values[start : start + native_format.channels])
                / native_format.channels
            )
        )
    return tuple(samples)


def _float_to_pcm16(value: float) -> int:
    if not math.isfinite(value):
        raise ValueError("float32 samples must be finite.")
    clipped = max(-1.0, min(1.0, value))
    if clipped <= -1.0:
        return -32768
    if clipped >= 1.0:
        return 32767
    scale = 32768.0 if clipped < 0.0 else 32767.0
    return _round_half_away_from_zero(clipped * scale)


def _round_half_away_from_zero(value: float) -> int:
    if value < 0:
        return int(math.ceil(value - 0.5))
    return int(math.floor(value + 0.5))


def _lane(value: LiveLane) -> LiveLane:
    if not isinstance(value, LiveLane):
        raise ValueError("lane must be a canonical v2 live lane.")
    return value


def _positive_int(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer.")
    if value <= 0:
        raise ValueError(f"{name} must be positive.")


def _non_negative_int(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer.")
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")
