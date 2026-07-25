from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field

from .live_lane_contract import (
    LIVE_V2_REPLAY_ACK_WINDOW,
    LiveLane,
    LiveV2Ack,
    LiveV2Frame,
    LiveV2OutOfOrderFrameError,
    LiveV2PrunedReplayError,
)


class LiveV2LaneCapacityError(ValueError):
    def __init__(
        self,
        *,
        lane: LiveLane,
        max_retained_samples: int,
        retained_samples: int,
        frame_sample_count: int,
    ):
        self.lane = lane
        self.max_retained_samples = max_retained_samples
        self.retained_samples = retained_samples
        self.frame_sample_count = frame_sample_count
        super().__init__(
            f"v2 {lane.value} lane retention capacity reached "
            f"({retained_samples}+{frame_sample_count}>{max_retained_samples})."
        )


class LiveV2EpochDiscontinuityRequiredError(ValueError):
    def __init__(
        self,
        *,
        lane: LiveLane,
        sequence: int,
        current_device_epoch: int,
        received_device_epoch: int,
    ):
        self.lane = lane
        self.sequence = sequence
        self.current_device_epoch = current_device_epoch
        self.received_device_epoch = received_device_epoch
        super().__init__(
            f"v2 {lane.value} frame sequence {sequence} advances device_epoch "
            "without discontinuity."
        )


class LiveV2StaleDeviceEpochError(ValueError):
    def __init__(
        self,
        *,
        lane: LiveLane,
        sequence: int,
        current_device_epoch: int,
        received_device_epoch: int,
    ):
        self.lane = lane
        self.sequence = sequence
        self.current_device_epoch = current_device_epoch
        self.received_device_epoch = received_device_epoch
        super().__init__(
            f"v2 {lane.value} frame sequence {sequence} uses stale device_epoch "
            f"{received_device_epoch}; current is {current_device_epoch}."
        )


@dataclass(frozen=True, slots=True)
class RetainedLiveV2Frame:
    frame: LiveV2Frame
    start_sample: int
    end_sample: int


@dataclass(frozen=True, slots=True)
class LiveLaneIngressSnapshot:
    lane: LiveLane
    next_sequence: int
    accepted_samples: int
    retained_samples: int
    current_device_epoch: int | None
    pruned_through_sequence: int


@dataclass(slots=True)
class _LaneState:
    next_sequence: int = 0
    accepted_samples: int = 0
    retained_samples: int = 0
    current_device_epoch: int | None = None
    retained_frames: list[RetainedLiveV2Frame] = field(default_factory=list)


class LiveLaneIngress:
    """Deep in-process ingress for independently admitted v2 source lanes."""

    def __init__(
        self,
        *,
        max_retained_samples: int,
        max_retained_acks: int = LIVE_V2_REPLAY_ACK_WINDOW,
    ):
        _positive_int(max_retained_samples, "max_retained_samples")
        _positive_int(max_retained_acks, "max_retained_acks")
        self._max_retained_samples = max_retained_samples
        self._max_retained_acks = max_retained_acks
        self._lanes = {lane: _LaneState() for lane in LiveLane}
        self._pruned_through = {lane: -1 for lane in LiveLane}
        self._acks: OrderedDict[tuple[LiveLane, int], LiveV2Ack] = OrderedDict()
        self._lock = threading.RLock()

    def accept(self, frame: LiveV2Frame) -> LiveV2Ack:
        if not isinstance(frame, LiveV2Frame):
            raise ValueError("frame must be LiveV2Frame.")

        with self._lock:
            key = (frame.lane, frame.sequence)
            prior = self._acks.get(key)
            if prior is not None:
                return prior

            pruned_through = self._pruned_through[frame.lane]
            if frame.sequence <= pruned_through:
                raise LiveV2PrunedReplayError(
                    lane=frame.lane,
                    sequence=frame.sequence,
                    pruned_through_sequence=pruned_through,
                )

            lane = self._lanes[frame.lane]
            if frame.sequence != lane.next_sequence:
                raise LiveV2OutOfOrderFrameError(
                    lane=frame.lane,
                    expected_sequence=lane.next_sequence,
                    received_sequence=frame.sequence,
                )

            self._check_epoch(frame, lane)
            self._check_capacity(frame, lane)

            start_sample = lane.accepted_samples
            end_sample = start_sample + frame.sample_count
            retained_samples = lane.retained_samples + frame.sample_count
            ack = LiveV2Ack(
                lane=frame.lane,
                sequence=frame.sequence,
                start_sample=start_sample,
                end_sample=end_sample,
                accepted_samples=end_sample,
                retained_samples=retained_samples,
                frozen_span_ids=(),
            )
            retained = RetainedLiveV2Frame(
                frame=frame,
                start_sample=start_sample,
                end_sample=end_sample,
            )

            if len(self._acks) >= self._max_retained_acks:
                self._prune_oldest_ack()
            self._acks[key] = ack
            lane.retained_frames.append(retained)
            lane.accepted_samples = end_sample
            lane.retained_samples = retained_samples
            lane.next_sequence += 1
            lane.current_device_epoch = frame.device_epoch
            return ack

    def retained_frames(self, lane: LiveLane | None = None) -> tuple[RetainedLiveV2Frame, ...]:
        with self._lock:
            if lane is None:
                return tuple(
                    retained
                    for lane_value in LiveLane
                    for retained in self._lanes[lane_value].retained_frames
                )
            if not isinstance(lane, LiveLane):
                raise ValueError("lane must be a canonical v2 live lane.")
            return tuple(self._lanes[lane].retained_frames)

    def snapshot(self, lane: LiveLane) -> LiveLaneIngressSnapshot:
        if not isinstance(lane, LiveLane):
            raise ValueError("lane must be a canonical v2 live lane.")
        with self._lock:
            state = self._lanes[lane]
            return LiveLaneIngressSnapshot(
                lane=lane,
                next_sequence=state.next_sequence,
                accepted_samples=state.accepted_samples,
                retained_samples=state.retained_samples,
                current_device_epoch=state.current_device_epoch,
                pruned_through_sequence=self._pruned_through[lane],
            )

    def release_retained_prefix(
        self,
        lane: LiveLane,
        through_sequence: int,
    ) -> tuple[RetainedLiveV2Frame, ...]:
        if not isinstance(lane, LiveLane):
            raise ValueError("lane must be a canonical v2 live lane.")
        _non_negative_int(through_sequence, "through_sequence")
        with self._lock:
            state = self._lanes[lane]
            release_count = 0
            release_samples = 0
            for retained in state.retained_frames:
                if retained.frame.sequence > through_sequence:
                    break
                release_count += 1
                release_samples += retained.frame.sample_count
            released = tuple(state.retained_frames[:release_count])
            if release_count:
                del state.retained_frames[:release_count]
                state.retained_samples -= release_samples
            return released

    def _check_epoch(self, frame: LiveV2Frame, lane: _LaneState) -> None:
        current = lane.current_device_epoch
        if current is None or frame.device_epoch == current:
            return
        if frame.device_epoch < current:
            raise LiveV2StaleDeviceEpochError(
                lane=frame.lane,
                sequence=frame.sequence,
                current_device_epoch=current,
                received_device_epoch=frame.device_epoch,
            )
        if not frame.discontinuity:
            raise LiveV2EpochDiscontinuityRequiredError(
                lane=frame.lane,
                sequence=frame.sequence,
                current_device_epoch=current,
                received_device_epoch=frame.device_epoch,
            )

    def _check_capacity(self, frame: LiveV2Frame, lane: _LaneState) -> None:
        if frame.sample_count > self._max_retained_samples:
            raise LiveV2LaneCapacityError(
                lane=frame.lane,
                max_retained_samples=self._max_retained_samples,
                retained_samples=lane.retained_samples,
                frame_sample_count=frame.sample_count,
            )
        if lane.retained_samples + frame.sample_count > self._max_retained_samples:
            raise LiveV2LaneCapacityError(
                lane=frame.lane,
                max_retained_samples=self._max_retained_samples,
                retained_samples=lane.retained_samples,
                frame_sample_count=frame.sample_count,
            )

    def _prune_oldest_ack(self) -> None:
        oldest_lane, oldest_sequence = next(iter(self._acks))
        self._acks.pop((oldest_lane, oldest_sequence))
        self._pruned_through[oldest_lane] = max(
            self._pruned_through[oldest_lane],
            oldest_sequence,
        )


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
