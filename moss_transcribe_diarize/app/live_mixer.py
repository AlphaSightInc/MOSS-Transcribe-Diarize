from __future__ import annotations

import math
import struct
import threading
from dataclasses import dataclass
from typing import Mapping

from .live_ingest import RetainedLiveV2Frame
from .live_lane_contract import LiveLane
from .live_session import AudioFrame, LIVE_SAMPLE_RATE
from .live_v2_session import LiveV2Session


_NANOSECONDS_PER_SECOND = 1_000_000_000
_HEADROOM_GAIN = 10 ** (-6 / 20)
_LIMITER_THRESHOLD = 0.98
_LIMITER_RANGE = 1.0 - _LIMITER_THRESHOLD


class LiveMixIntegrityError(ValueError):
    """Raised before downstream admission when source timing cannot be mixed."""


class LiveMixSourceMissingError(LiveMixIntegrityError):
    """Raised at final flush when an active source lane never produced frames."""


@dataclass(frozen=True, slots=True)
class LiveMixDiagnostics:
    start_timestamp_ns: int
    end_timestamp_ns: int
    sample_count: int
    overlap_samples: int
    limited_samples: int
    silent_samples: Mapping[LiveLane, int]
    gap_samples: Mapping[LiveLane, int]
    source_watermarks: Mapping[LiveLane, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "silent_samples", dict(self.silent_samples))
        object.__setattr__(self, "gap_samples", dict(self.gap_samples))
        object.__setattr__(self, "source_watermarks", dict(self.source_watermarks))

    def to_dict(self) -> dict[str, object]:
        return {
            "start_timestamp_ns": self.start_timestamp_ns,
            "end_timestamp_ns": self.end_timestamp_ns,
            "sample_count": self.sample_count,
            "overlap_samples": self.overlap_samples,
            "limited_samples": self.limited_samples,
            "silent_samples": {
                lane.value: value for lane, value in self.silent_samples.items()
            },
            "gap_samples": {
                lane.value: value for lane, value in self.gap_samples.items()
            },
            "source_watermarks": {
                lane.value: value for lane, value in self.source_watermarks.items()
            },
        }


@dataclass(frozen=True, slots=True)
class LiveMixResult:
    frame: AudioFrame
    queued_item_ids: tuple[int, ...]
    diagnostics: LiveMixDiagnostics

    def __post_init__(self) -> None:
        object.__setattr__(self, "queued_item_ids", tuple(self.queued_item_ids))


@dataclass(frozen=True, slots=True)
class _LaneInterval:
    retained: RetainedLiveV2Frame
    start_ns: int
    end_ns: int


@dataclass(frozen=True, slots=True)
class _StagedMix:
    frame: AudioFrame
    diagnostics: LiveMixDiagnostics


class LiveCompatibilityMixer:
    """Transactional retained-v2-lane to mono-runtime compatibility mixer."""

    def __init__(self):
        self._cursor_ns: int | None = None
        self._lock = threading.RLock()

    def admit_available(
        self,
        session_id: str,
        source: LiveV2Session,
        runtime,
        final: bool = False,
    ) -> LiveMixResult | None:
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id must be a non-empty string.")
        if not isinstance(source, LiveV2Session):
            raise ValueError("source must be LiveV2Session.")
        if not isinstance(final, bool):
            raise ValueError("final must be a boolean.")

        with self._lock:
            staged = self._stage(session_id, source, runtime, final=final)
            if staged is None:
                return None
            accepted = runtime.accept_frame(session_id, staged.frame)
            self._cursor_ns = staged.diagnostics.end_timestamp_ns
            source.account_through(staged.diagnostics.source_watermarks)
            return LiveMixResult(
                frame=staged.frame,
                queued_item_ids=tuple(getattr(accepted, "queued_item_ids", ())),
                diagnostics=staged.diagnostics,
            )

    def _stage(
        self,
        session_id: str,
        source: LiveV2Session,
        runtime,
        *,
        final: bool,
    ) -> _StagedMix | None:
        retained_by_lane = {
            lane: source.retained_frames(lane)
            for lane in (LiveLane.SYSTEM, LiveLane.MICROPHONE)
        }
        lane_snapshots = source.snapshot().lanes
        failed_lanes = {
            lane
            for lane, snapshot in lane_snapshots.items()
            if snapshot.health == "failed" or snapshot.failed_samples
        }
        active_lanes = tuple(lane for lane in retained_by_lane if lane not in failed_lanes)
        observed_active_lanes = tuple(
            lane for lane in active_lanes if retained_by_lane[lane]
        )
        missing_active_lanes = tuple(
            lane for lane in active_lanes if lane not in observed_active_lanes
        )
        if final and missing_active_lanes:
            missing = sorted(
                lane.value for lane in missing_active_lanes
            )
            raise LiveMixSourceMissingError(
                "missing active source lane: " + ", ".join(missing)
            )
        if missing_active_lanes:
            return None
        if not active_lanes:
            return None

        intervals_by_lane = {
            lane: self._sealed_intervals(retained, final=final)
            for lane, retained in retained_by_lane.items()
            if lane in active_lanes
        }
        if any(not intervals for intervals in intervals_by_lane.values()):
            return None

        origin_ns = max(
            retained_by_lane[lane][0].frame.capture_timestamp_ns
            for lane in active_lanes
        )
        cursor_ns = origin_ns if self._cursor_ns is None else self._cursor_ns
        safe_end_ns = (
            max(intervals[-1].end_ns for intervals in intervals_by_lane.values())
            if final
            else min(intervals[-1].end_ns for intervals in intervals_by_lane.values())
        )
        if safe_end_ns <= cursor_ns:
            return None

        sample_count = math.floor(
            (safe_end_ns - cursor_ns) * LIVE_SAMPLE_RATE / _NANOSECONDS_PER_SECOND
        )
        if sample_count <= 0:
            return None

        runtime_snapshot = runtime.snapshot(session_id)
        if runtime_snapshot is None:
            raise KeyError(session_id)
        sequence = runtime_snapshot.session.next_frame_sequence
        lane_values: dict[LiveLane, list[float]] = {}
        lane_gaps: dict[LiveLane, int] = {}
        lane_silent: dict[LiveLane, int] = {}
        for lane in retained_by_lane:
            if lane in failed_lanes:
                lane_values[lane] = [0.0] * sample_count
                lane_gaps[lane] = 0
                lane_silent[lane] = sample_count
                continue
            intervals = intervals_by_lane[lane]
            values, gaps, silent = self._render_lane(
                intervals,
                cursor_ns=cursor_ns,
                sample_count=sample_count,
            )
            lane_values[lane] = values
            lane_gaps[lane] = gaps
            lane_silent[lane] = silent

        samples: list[int] = []
        overlap_samples = 0
        limited_samples = 0
        for index in range(sample_count):
            system = lane_values[LiveLane.SYSTEM][index]
            microphone = lane_values[LiveLane.MICROPHONE][index]
            if system != 0.0 and microphone != 0.0:
                overlap_samples += 1
            mixed = (system * _HEADROOM_GAIN) + (microphone * _HEADROOM_GAIN)
            if abs(mixed) > _LIMITER_THRESHOLD:
                limited_samples += 1
                mixed = math.copysign(
                    _LIMITER_THRESHOLD
                    + _LIMITER_RANGE
                    * math.tanh((abs(mixed) - _LIMITER_THRESHOLD) / _LIMITER_RANGE),
                    mixed,
                )
            mixed = max(-1.0, min(1.0, mixed))
            samples.append(int(mixed * 32767.0))

        pcm = struct.pack("<" + "h" * len(samples), *samples)
        watermarks = self._watermarks(intervals_by_lane, safe_end_ns)
        diagnostics = LiveMixDiagnostics(
            start_timestamp_ns=cursor_ns,
            end_timestamp_ns=safe_end_ns,
            sample_count=sample_count,
            overlap_samples=overlap_samples,
            limited_samples=limited_samples,
            silent_samples=lane_silent,
            gap_samples=lane_gaps,
            source_watermarks=watermarks,
        )
        frame = AudioFrame(
            sequence=sequence,
            pcm=pcm,
            sample_count=sample_count,
            sample_rate=LIVE_SAMPLE_RATE,
        )
        return _StagedMix(frame=frame, diagnostics=diagnostics)

    def _sealed_intervals(
        self,
        retained: tuple[RetainedLiveV2Frame, ...],
        *,
        final: bool,
    ) -> tuple[_LaneInterval, ...]:
        intervals: list[_LaneInterval] = []
        for index, item in enumerate(retained):
            frame = item.frame
            start_ns = frame.capture_timestamp_ns
            if index + 1 < len(retained):
                successor = retained[index + 1].frame
                if successor.discontinuity:
                    end_ns = self._nominal_end_ns(item)
                    if successor.capture_timestamp_ns < end_ns:
                        raise LiveMixIntegrityError(
                            f"{frame.lane.value} discontinuity overlaps prior frame."
                        )
                else:
                    end_ns = successor.capture_timestamp_ns
            elif final:
                end_ns = self._nominal_end_ns(item)
            else:
                continue
            if end_ns <= start_ns:
                raise LiveMixIntegrityError(
                    f"{frame.lane.value} capture timestamps must advance."
                )
            intervals.append(_LaneInterval(retained=item, start_ns=start_ns, end_ns=end_ns))
        return tuple(intervals)

    def _render_lane(
        self,
        intervals: tuple[_LaneInterval, ...],
        *,
        cursor_ns: int,
        sample_count: int,
    ) -> tuple[list[float], int, int]:
        values = [0.0] * sample_count
        covered = [False] * sample_count
        silent_count = 0
        for interval in intervals:
            frame = interval.retained.frame
            decoded = () if frame.silent else self._decode_pcm16(frame.pcm)
            for index in range(sample_count):
                timestamp_ns = self._grid_timestamp_ns(cursor_ns, index)
                if timestamp_ns < interval.start_ns or timestamp_ns >= interval.end_ns:
                    continue
                covered[index] = True
                if frame.silent:
                    silent_count += 1
                    continue
                source_index = (
                    (timestamp_ns - interval.start_ns)
                    * frame.sample_count
                    / (interval.end_ns - interval.start_ns)
                )
                values[index] = self._interpolate(decoded, source_index)
        gap_count = sum(1 for seen in covered if not seen)
        return values, gap_count, silent_count

    @staticmethod
    def _decode_pcm16(pcm: bytes) -> tuple[float, ...]:
        if len(pcm) % 2:
            raise LiveMixIntegrityError("PCM16 byte length must be even.")
        return tuple(value / 32768.0 for (value,) in struct.iter_unpack("<h", pcm))

    @staticmethod
    def _interpolate(values: tuple[float, ...], source_index: float) -> float:
        if not values:
            return 0.0
        left = math.floor(source_index)
        if left < 0:
            return values[0]
        if left >= len(values) - 1:
            return values[-1]
        fraction = source_index - left
        return values[left] + (values[left + 1] - values[left]) * fraction

    @staticmethod
    def _grid_timestamp_ns(cursor_ns: int, index: int) -> float:
        return cursor_ns + (index * _NANOSECONDS_PER_SECOND / LIVE_SAMPLE_RATE)

    @staticmethod
    def _nominal_end_ns(retained: RetainedLiveV2Frame) -> int:
        frame = retained.frame
        return frame.capture_timestamp_ns + math.ceil(
            frame.sample_count * _NANOSECONDS_PER_SECOND / frame.sample_rate
        )

    @staticmethod
    def _watermarks(
        intervals_by_lane: Mapping[LiveLane, tuple[_LaneInterval, ...]],
        safe_end_ns: int,
    ) -> dict[LiveLane, int]:
        watermarks: dict[LiveLane, int] = {}
        for lane, intervals in intervals_by_lane.items():
            eligible = [
                interval.retained.frame.sequence
                for interval in intervals
                if interval.end_ns <= safe_end_ns
            ]
            if eligible:
                watermarks[lane] = max(eligible)
        return watermarks


class LiveCompatibilityMixerRegistry:
    def __init__(self):
        self._mixers: dict[str, LiveCompatibilityMixer] = {}
        self._lock = threading.RLock()

    def create(self, session_id: str) -> LiveCompatibilityMixer:
        _session_id(session_id)
        with self._lock:
            if session_id in self._mixers:
                raise ValueError(f"compatibility mixer {session_id} already exists.")
            mixer = LiveCompatibilityMixer()
            self._mixers[session_id] = mixer
            return mixer

    def get(self, session_id: str) -> LiveCompatibilityMixer:
        _session_id(session_id)
        with self._lock:
            try:
                return self._mixers[session_id]
            except KeyError as exc:
                raise KeyError(session_id) from exc

    def release(self, session_id: str) -> LiveCompatibilityMixer | None:
        _session_id(session_id)
        with self._lock:
            return self._mixers.pop(session_id, None)


def _session_id(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("session_id must be a non-empty string.")
