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
