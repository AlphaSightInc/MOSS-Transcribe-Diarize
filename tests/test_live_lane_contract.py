from __future__ import annotations

import base64

import pytest

from moss_transcribe_diarize.app.live_lane_contract import (
    LiveLane,
    LiveV2Ack,
    LiveV2Capabilities,
    LiveV2Descriptor,
    LiveV2Frame,
)


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
