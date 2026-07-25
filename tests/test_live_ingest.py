from __future__ import annotations

import pytest

from moss_transcribe_diarize.app.live_ingest import (
    LiveLaneIngress,
    LiveV2EpochDiscontinuityRequiredError,
    LiveV2LaneCapacityError,
    LiveV2StaleDeviceEpochError,
)
from moss_transcribe_diarize.app.live_lane_contract import (
    LIVE_V2_REPLAY_ACK_WINDOW,
    LiveLane,
    LiveV2Frame,
    LiveV2OutOfOrderFrameError,
    LiveV2PrunedReplayError,
)


def frame(
    lane: LiveLane,
    sequence: int,
    samples: int,
    *,
    device_epoch: int = 0,
    discontinuity: bool = False,
    capture_timestamp_ns: int = 123,
    silent: bool = False,
    pcm_byte: int | None = None,
) -> LiveV2Frame:
    value = sequence if pcm_byte is None else pcm_byte
    return LiveV2Frame(
        lane=lane,
        sequence=sequence,
        capture_timestamp_ns=capture_timestamp_ns,
        device_epoch=device_epoch,
        silent=silent,
        discontinuity=discontinuity,
        sample_rate=16000,
        sample_count=samples,
        pcm=bytes([value % 256]) * samples * 2,
    )


def test_accepts_complete_frames_with_lane_local_coordinates_and_retention():
    ingress = LiveLaneIngress(max_retained_samples=8)
    system = frame(LiveLane.SYSTEM, 0, 2, capture_timestamp_ns=11, pcm_byte=1)
    microphone = frame(
        LiveLane.MICROPHONE,
        0,
        3,
        capture_timestamp_ns=22,
        device_epoch=5,
        silent=True,
        pcm_byte=2,
    )

    system_ack = ingress.accept(system)
    microphone_ack = ingress.accept(microphone)

    assert system_ack.to_dict() == {
        "lane": "system",
        "sequence": 0,
        "start_sample": 0,
        "end_sample": 2,
        "accepted_samples": 2,
        "retained_samples": 2,
        "frozen_span_ids": [],
    }
    assert microphone_ack.to_dict() == {
        "lane": "microphone",
        "sequence": 0,
        "start_sample": 0,
        "end_sample": 3,
        "accepted_samples": 3,
        "retained_samples": 3,
        "frozen_span_ids": [],
    }
    retained_system = ingress.retained_frames(LiveLane.SYSTEM)
    retained_microphone = ingress.retained_frames(LiveLane.MICROPHONE)
    assert isinstance(retained_system, tuple)
    assert retained_system[0].frame == system
    assert retained_system[0].frame.pcm == system.pcm
    assert retained_system[0].frame.capture_timestamp_ns == 11
    assert retained_microphone[0].frame == microphone
    assert retained_microphone[0].frame.device_epoch == 5
    assert retained_microphone[0].frame.silent is True


def test_replays_prior_ack_without_comparing_changed_payload():
    ingress = LiveLaneIngress(max_retained_samples=8)
    accepted = ingress.accept(frame(LiveLane.SYSTEM, 0, 2, pcm_byte=1))

    replayed = ingress.accept(frame(LiveLane.SYSTEM, 0, 4, capture_timestamp_ns=99, pcm_byte=9))

    assert replayed == accepted
    retained = ingress.retained_frames(LiveLane.SYSTEM)
    assert len(retained) == 1
    assert retained[0].frame.sample_count == 2


def test_rejects_sequence_gap_before_mutating_lane_state():
    ingress = LiveLaneIngress(max_retained_samples=8)

    with pytest.raises(LiveV2OutOfOrderFrameError) as raised:
        ingress.accept(frame(LiveLane.SYSTEM, 1, 2))

    assert raised.value.expected_sequence == 0
    assert ingress.retained_frames(LiveLane.SYSTEM) == ()
    accepted = ingress.accept(frame(LiveLane.SYSTEM, 0, 2))
    assert accepted.sequence == 0


def test_each_lane_has_independent_retention_capacity():
    ingress = LiveLaneIngress(max_retained_samples=5)
    assert ingress.accept(frame(LiveLane.SYSTEM, 0, 4)).retained_samples == 4
    assert ingress.accept(frame(LiveLane.MICROPHONE, 0, 4)).retained_samples == 4

    with pytest.raises(LiveV2LaneCapacityError) as raised:
        ingress.accept(frame(LiveLane.SYSTEM, 1, 2))

    assert raised.value.lane is LiveLane.SYSTEM
    assert raised.value.max_retained_samples == 5
    assert ingress.retained_frames(LiveLane.SYSTEM)[0].frame.pcm == b"\0" * 8
    accepted = ingress.accept(frame(LiveLane.MICROPHONE, 1, 1))
    assert accepted.retained_samples == 5


def test_capacity_failure_does_not_consume_sequence_or_evict_metadata():
    ingress = LiveLaneIngress(max_retained_samples=4)
    accepted = ingress.accept(frame(LiveLane.SYSTEM, 0, 3, capture_timestamp_ns=17, pcm_byte=7))

    with pytest.raises(LiveV2LaneCapacityError):
        ingress.accept(frame(LiveLane.SYSTEM, 1, 2, capture_timestamp_ns=18, pcm_byte=8))

    retained = ingress.retained_frames(LiveLane.SYSTEM)
    assert len(retained) == 1
    assert retained[0].frame.capture_timestamp_ns == 17
    assert retained[0].frame.pcm == bytes([7]) * 6
    replayed = ingress.accept(frame(LiveLane.SYSTEM, 0, 1, pcm_byte=9))
    assert replayed == accepted
    corrected = ingress.accept(frame(LiveLane.SYSTEM, 1, 1, capture_timestamp_ns=19, pcm_byte=9))
    assert corrected.start_sample == 3
    assert corrected.end_sample == 4


def test_epoch_transition_requires_marked_discontinuity_and_retries_without_mutation():
    ingress = LiveLaneIngress(max_retained_samples=12)
    ingress.accept(frame(LiveLane.SYSTEM, 0, 2, device_epoch=10))

    with pytest.raises(LiveV2EpochDiscontinuityRequiredError) as raised:
        ingress.accept(frame(LiveLane.SYSTEM, 1, 2, device_epoch=11, discontinuity=False))

    assert raised.value.current_device_epoch == 10
    assert raised.value.received_device_epoch == 11
    corrected = ingress.accept(frame(LiveLane.SYSTEM, 1, 2, device_epoch=11, discontinuity=True))
    assert corrected.sequence == 1
    assert corrected.start_sample == 2

    with pytest.raises(LiveV2StaleDeviceEpochError) as stale:
        ingress.accept(frame(LiveLane.SYSTEM, 2, 2, device_epoch=10, discontinuity=True))

    assert stale.value.current_device_epoch == 11
    assert stale.value.received_device_epoch == 10
    accepted = ingress.accept(frame(LiveLane.SYSTEM, 2, 2, device_epoch=11))
    assert accepted.sequence == 2


def test_ack_window_prunes_replay_without_pruning_retained_frames_or_blocking_idle_lane():
    ingress = LiveLaneIngress(max_retained_samples=LIVE_V2_REPLAY_ACK_WINDOW + 4)
    first = ingress.accept(frame(LiveLane.SYSTEM, 0, 1))
    ingress.accept(frame(LiveLane.MICROPHONE, 0, 1))

    for sequence in range(1, LIVE_V2_REPLAY_ACK_WINDOW + 1):
        ingress.accept(frame(LiveLane.SYSTEM, sequence, 1))

    with pytest.raises(LiveV2PrunedReplayError) as raised:
        ingress.accept(frame(LiveLane.SYSTEM, 0, 1))

    assert raised.value.pruned_through_sequence == first.sequence
    resumed_idle_lane = ingress.accept(frame(LiveLane.MICROPHONE, 1, 1))
    assert resumed_idle_lane.start_sample == 1
    assert len(ingress.retained_frames(LiveLane.SYSTEM)) == LIVE_V2_REPLAY_ACK_WINDOW + 1
    assert len(ingress.retained_frames(LiveLane.MICROPHONE)) == 2
