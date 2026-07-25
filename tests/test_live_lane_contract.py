from __future__ import annotations

import base64

import pytest

from moss_transcribe_diarize.app.live_lane_contract import (
    LiveLane,
    LiveV2Ack,
    LiveV2Capabilities,
    LiveV2Descriptor,
    LiveV2Frame,
    LiveV2Negotiation,
    LiveV2ObsoleteClientError,
    LiveV2OutOfOrderFrameError,
    LiveV2PriorAckReplayStore,
    LiveV2PrunedReplayError,
    negotiate_v2_protocol,
)
from moss_transcribe_diarize.app.live_transport import live_v2_obsolete_client_response


def frame_payload(**overrides):
    payload = {
        "lane": "system",
        "sequence": 0,
        "capture_timestamp_ns": 123,
        "device_epoch": 7,
        "silent": False,
        "discontinuity": False,
        "sample_rate": 16000,
        "sample_count": 2,
        "pcm_base64": base64.b64encode(b"\0\1\2\3").decode("ascii"),
    }
    payload.update(overrides)
    return payload


def ack_for(
    frame: LiveV2Frame,
    *,
    accepted_samples: int | None = None,
    retained_samples: int | None = None,
) -> LiveV2Ack:
    accepted = frame.sample_count if accepted_samples is None else accepted_samples
    retained = frame.sample_count if retained_samples is None else retained_samples
    return LiveV2Ack(
        lane=frame.lane,
        sequence=frame.sequence,
        start_sample=0,
        end_sample=frame.sample_count,
        accepted_samples=accepted,
        retained_samples=retained,
        frozen_span_ids=(),
    )


def test_v2_frame_accepts_canonical_lanes_and_round_trips_json_payloads():
    frame = LiveV2Frame.from_dict(frame_payload(lane="microphone", silent=True, discontinuity=True))

    assert frame.lane is LiveLane.MICROPHONE
    assert frame.sequence == 0
    assert frame.capture_timestamp_ns == 123
    assert frame.device_epoch == 7
    assert frame.silent is True
    assert frame.discontinuity is True
    assert frame.sample_rate == 16000
    assert frame.sample_count == 2
    assert frame.pcm == b"\0\1\2\3"
    assert LiveV2Frame.from_dict(frame.to_dict()) == frame


@pytest.mark.parametrize("lane", ["system", "microphone"])
def test_v2_frame_lane_vocabulary_is_exact(lane):
    assert LiveV2Frame.from_dict(frame_payload(lane=lane)).lane.value == lane


@pytest.mark.parametrize("lane", ["speaker", "SYSTEM", "", 0])
def test_v2_frame_rejects_unknown_lane_values(lane):
    with pytest.raises(ValueError, match="lane"):
        LiveV2Frame.from_dict(frame_payload(lane=lane))


@pytest.mark.parametrize(
    "field",
    [
        "lane",
        "sequence",
        "capture_timestamp_ns",
        "device_epoch",
        "silent",
        "discontinuity",
        "sample_rate",
        "sample_count",
        "pcm_base64",
    ],
)
def test_v2_frame_rejects_missing_required_fields(field):
    payload = frame_payload()
    payload.pop(field)

    with pytest.raises(ValueError, match="missing fields"):
        LiveV2Frame.from_dict(payload)


def test_v2_frame_rejects_unknown_fields():
    with pytest.raises(ValueError, match="unknown fields"):
        LiveV2Frame.from_dict(frame_payload(extra=True))


@pytest.mark.parametrize("field", ["sequence", "capture_timestamp_ns", "device_epoch"])
def test_v2_frame_rejects_negative_numeric_fields(field):
    with pytest.raises(ValueError, match=field):
        LiveV2Frame.from_dict(frame_payload(**{field: -1}))


@pytest.mark.parametrize("field", ["sample_rate", "sample_count"])
def test_v2_frame_rejects_non_positive_sample_fields(field):
    with pytest.raises(ValueError, match=field):
        LiveV2Frame.from_dict(frame_payload(**{field: 0}))


@pytest.mark.parametrize("field", ["sequence", "capture_timestamp_ns", "device_epoch", "sample_rate", "sample_count"])
def test_v2_frame_rejects_bool_values_for_integer_fields(field):
    with pytest.raises(ValueError, match=field):
        LiveV2Frame.from_dict(frame_payload(**{field: True}))


@pytest.mark.parametrize("field", ["silent", "discontinuity"])
def test_v2_frame_rejects_integer_values_for_boolean_fields(field):
    with pytest.raises(ValueError, match=field):
        LiveV2Frame.from_dict(frame_payload(**{field: 0}))


@pytest.mark.parametrize("pcm_base64", ["not base64!", base64.b64encode(b"\0\1").decode("ascii")[:-1]])
def test_v2_frame_rejects_malformed_base64(pcm_base64):
    with pytest.raises(ValueError, match="pcm_base64"):
        LiveV2Frame.from_dict(frame_payload(pcm_base64=pcm_base64))


def test_v2_frame_rejects_pcm_length_that_does_not_match_sample_count():
    with pytest.raises(ValueError, match="pcm length"):
        LiveV2Frame.from_dict(frame_payload(sample_count=3))


def test_v2_ack_carries_lane_and_existing_mono_ack_facts():
    ack = LiveV2Ack(
        lane=LiveLane.SYSTEM,
        sequence=3,
        start_sample=10,
        end_sample=14,
        accepted_samples=20,
        retained_samples=4,
        frozen_span_ids=(1, 2),
    )

    payload = ack.to_dict()

    assert payload == {
        "lane": "system",
        "sequence": 3,
        "start_sample": 10,
        "end_sample": 14,
        "accepted_samples": 20,
        "retained_samples": 4,
        "frozen_span_ids": [1, 2],
    }
    assert LiveV2Ack.from_dict(payload) == ack


def test_v2_ack_validation_is_strict():
    with pytest.raises(ValueError, match="end_sample"):
        LiveV2Ack(
            lane=LiveLane.MICROPHONE,
            sequence=0,
            start_sample=5,
            end_sample=4,
            accepted_samples=5,
            retained_samples=1,
            frozen_span_ids=(),
        )
    with pytest.raises(ValueError, match="frozen_span_ids"):
        LiveV2Ack.from_dict(
            {
                "lane": "microphone",
                "sequence": 0,
                "start_sample": 0,
                "end_sample": 1,
                "accepted_samples": 1,
                "retained_samples": 1,
                "frozen_span_ids": [-1],
            }
        )


def test_v2_descriptor_declares_protocol_range_and_capabilities():
    descriptor = LiveV2Descriptor()

    assert descriptor.to_dict() == {
        "protocol": "moss-live-service.v2",
        "min_protocol_version": 2,
        "max_protocol_version": 2,
        "capabilities": {
            "lanes": True,
            "binary": False,
            "idempotent_frames": True,
            "resumable": True,
        },
    }
    assert LiveV2Descriptor.from_dict(descriptor.to_dict()) == descriptor


def test_v2_descriptor_rejects_non_exact_capability_bools_and_protocol_range():
    with pytest.raises(ValueError, match="binary"):
        LiveV2Capabilities(binary=0)
    with pytest.raises(ValueError, match="protocol range"):
        LiveV2Descriptor(min_protocol_version=1)


def test_v2_negotiation_selects_highest_common_protocol_version_and_round_trips():
    negotiated = negotiate_v2_protocol(client_min_protocol_version=1, client_max_protocol_version=2)

    assert negotiated == LiveV2Negotiation(selected_protocol_version=2)
    assert negotiated.to_dict() == {
        "protocol": "moss-live-service.v2",
        "selected_protocol_version": 2,
    }
    assert LiveV2Negotiation.from_dict(negotiated.to_dict()) == negotiated


def test_v2_negotiation_rejects_obsolete_client_with_machine_payload():
    with pytest.raises(LiveV2ObsoleteClientError) as raised:
        negotiate_v2_protocol(client_min_protocol_version=1, client_max_protocol_version=1)

    assert raised.value.to_dict() == {
        "code": "obsolete_client",
        "protocol": "moss-live-service.v2",
        "required_min_protocol_version": 2,
        "server_min_protocol_version": 2,
        "server_max_protocol_version": 2,
        "client_min_protocol_version": 1,
        "client_max_protocol_version": 1,
    }


def test_v2_negotiation_rejects_future_disjoint_range_as_unsupported():
    with pytest.raises(ValueError, match="no common version"):
        negotiate_v2_protocol(client_min_protocol_version=3, client_max_protocol_version=4)


@pytest.mark.parametrize(
    ("client_min_protocol_version", "client_max_protocol_version", "message"),
    [
        (2, 1, "must not exceed"),
        (True, 2, "client protocol range min_protocol_version"),
        (1, False, "client protocol range max_protocol_version"),
        (0, 2, "positive"),
    ],
)
def test_v2_negotiation_rejects_invalid_ranges(client_min_protocol_version, client_max_protocol_version, message):
    with pytest.raises(ValueError, match=message):
        negotiate_v2_protocol(
            client_min_protocol_version=client_min_protocol_version,
            client_max_protocol_version=client_max_protocol_version,
        )


def test_v2_obsolete_client_maps_to_426_style_http_payload():
    error = LiveV2ObsoleteClientError(
        client_min_protocol_version=1,
        client_max_protocol_version=1,
        server_min_protocol_version=2,
        server_max_protocol_version=2,
    )

    status, payload = live_v2_obsolete_client_response(error)

    assert status == 426
    assert payload["failure"]["code"] == "obsolete_client"
    assert payload["failure"]["required_min_protocol_version"] == 2


def test_v2_replay_store_keys_prior_acknowledgements_by_lane_and_sequence():
    store = LiveV2PriorAckReplayStore(max_retained_acks=4)
    calls = []

    def accept_new(frame):
        calls.append((frame.lane, frame.sequence))
        return ack_for(frame, accepted_samples=len(calls) * frame.sample_count)

    system_zero = LiveV2Frame.from_dict(frame_payload(lane="system", sequence=0))
    microphone_zero = LiveV2Frame.from_dict(frame_payload(lane="microphone", sequence=0))

    system_ack = store.accept(system_zero, accept_new)
    microphone_ack = store.accept(microphone_zero, accept_new)
    duplicate_system_ack = store.accept(system_zero, accept_new)

    assert system_ack.lane is LiveLane.SYSTEM
    assert microphone_ack.lane is LiveLane.MICROPHONE
    assert system_ack.sequence == microphone_ack.sequence == 0
    assert duplicate_system_ack == system_ack
    assert calls == [(LiveLane.SYSTEM, 0), (LiveLane.MICROPHONE, 0)]
    assert store.retained_ack_count == 2
    assert store.next_sequence(LiveLane.SYSTEM) == 1
    assert store.next_sequence(LiveLane.MICROPHONE) == 1


def test_v2_replay_store_rejects_future_gap_before_acceptor_mutation():
    store = LiveV2PriorAckReplayStore(max_retained_acks=4)
    calls = []
    future = LiveV2Frame.from_dict(frame_payload(lane="system", sequence=1))

    with pytest.raises(LiveV2OutOfOrderFrameError) as raised:
        store.accept(future, lambda frame: calls.append(frame) or ack_for(frame))

    assert raised.value.lane is LiveLane.SYSTEM
    assert raised.value.expected_sequence == 0
    assert raised.value.received_sequence == 1
    assert calls == []
    assert store.retained_ack_count == 0


def test_v2_replay_store_rejects_explicitly_pruned_old_key():
    store = LiveV2PriorAckReplayStore(max_retained_acks=4)
    frame = LiveV2Frame.from_dict(frame_payload(lane="system", sequence=0))
    store.accept(frame, ack_for)

    assert store.prune_through(lane=LiveLane.SYSTEM, sequence=0) == 1

    with pytest.raises(LiveV2PrunedReplayError) as raised:
        store.accept(frame, ack_for)

    assert raised.value.lane is LiveLane.SYSTEM
    assert raised.value.sequence == 0
    assert raised.value.pruned_through_sequence == 0
    assert store.retained_ack_count == 0


def test_v2_replay_store_prunes_oldest_ack_when_its_own_window_is_full():
    store = LiveV2PriorAckReplayStore(max_retained_acks=1)
    first = LiveV2Frame.from_dict(frame_payload(lane="system", sequence=0))
    second = LiveV2Frame.from_dict(frame_payload(lane="system", sequence=1))
    calls = []

    store.accept(first, lambda frame: calls.append(frame.sequence) or ack_for(frame))
    accepted = store.accept(second, lambda frame: calls.append(frame.sequence) or ack_for(frame))

    assert accepted.sequence == 1
    assert calls == [0, 1]
    assert store.retained_ack_count == 1
    with pytest.raises(LiveV2PrunedReplayError) as raised:
        store.accept(first, ack_for)
    assert raised.value.pruned_through_sequence == 0
