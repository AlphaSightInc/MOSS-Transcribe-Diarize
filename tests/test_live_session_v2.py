from __future__ import annotations

import asyncio

import pytest

from moss_transcribe_diarize.app.live_ingest import LiveV2LaneCapacityError
from moss_transcribe_diarize.app.live_lane_contract import LiveLane, LiveV2Frame
from moss_transcribe_diarize.app.live_v2_session import (
    LiveV2AccountingError,
    LiveV2Session,
    LiveV2SessionRegistry,
    LiveV2SessionTerminalError,
)


def frame(lane: LiveLane, sequence: int, samples: int, *, pcm_byte: int | None = None) -> LiveV2Frame:
    value = sequence if pcm_byte is None else pcm_byte
    return LiveV2Frame(
        lane=lane,
        sequence=sequence,
        capture_timestamp_ns=sequence,
        device_epoch=0,
        silent=False,
        discontinuity=False,
        sample_rate=16000,
        sample_count=samples,
        pcm=bytes([value % 256]) * samples * 2,
    )


def test_session_snapshot_reports_independent_lane_reconnect_facts():
    session = LiveV2Session(max_retained_samples=8)

    system_ack = session.accept(frame(LiveLane.SYSTEM, 0, 3, pcm_byte=1))
    microphone_ack = session.accept(frame(LiveLane.MICROPHONE, 0, 2, pcm_byte=2))

    assert system_ack.start_sample == 0
    assert microphone_ack.start_sample == 0
    assert session.snapshot().to_dict() == {
        "status": "active",
        "terminal_reason": None,
        "lanes": {
            "system": {
                "lane": "system",
                "next_sequence": 1,
                "accepted_samples": 3,
                "accounted_samples": 0,
                "failed_samples": 0,
                "retained_samples": 3,
                "current_device_epoch": 0,
                "pruned_through_sequence": -1,
                "health": "active",
                "failure_code": None,
            },
            "microphone": {
                "lane": "microphone",
                "next_sequence": 1,
                "accepted_samples": 2,
                "accounted_samples": 0,
                "failed_samples": 0,
                "retained_samples": 2,
                "current_device_epoch": 0,
                "pruned_through_sequence": -1,
                "health": "active",
                "failure_code": None,
            },
        },
    }


def test_accounting_releases_whole_retained_prefix_and_recovers_capacity():
    session = LiveV2Session(max_retained_samples=4)
    session.accept(frame(LiveLane.SYSTEM, 0, 4, pcm_byte=7))

    with pytest.raises(LiveV2LaneCapacityError):
        session.accept(frame(LiveLane.SYSTEM, 1, 1, pcm_byte=8))

    snapshot = session.account_through({LiveLane.SYSTEM: 0}).to_dict()
    assert snapshot["lanes"]["system"]["accounted_samples"] == 4
    assert snapshot["lanes"]["system"]["retained_samples"] == 0
    recovered = session.accept(frame(LiveLane.SYSTEM, 1, 1, pcm_byte=9))
    assert recovered.sequence == 1
    assert recovered.retained_samples == 1


def test_accounting_validates_all_requested_lanes_before_mutation():
    session = LiveV2Session(max_retained_samples=8)
    session.accept(frame(LiveLane.SYSTEM, 0, 2))
    session.accept(frame(LiveLane.MICROPHONE, 0, 2))
    before = session.snapshot()

    with pytest.raises(LiveV2AccountingError):
        session.account_through(
            {
                LiveLane.SYSTEM: 0,
                LiveLane.MICROPHONE: 1,
            }
        )

    assert session.snapshot() == before
    assert len(session.retained_frames(LiveLane.SYSTEM)) == 1
    assert len(session.retained_frames(LiveLane.MICROPHONE)) == 1


def test_clean_stop_requires_exact_accounting():
    session = LiveV2Session(max_retained_samples=8)
    session.accept(frame(LiveLane.SYSTEM, 0, 2))
    unaccounted = asyncio.run(session.stop(0.0))
    assert unaccounted.to_dict()["status"] == "closing"

    session.account_through({LiveLane.SYSTEM: 0})
    closed = asyncio.run(session.stop(0.0)).to_dict()

    assert closed["status"] == "closed"
    assert closed["lanes"]["system"]["accepted_samples"] == 2
    assert closed["lanes"]["system"]["accounted_samples"] == 2
    assert closed["lanes"]["system"]["retained_samples"] == 0


def test_typed_lane_failure_conserves_retained_samples_and_keeps_sibling_usable():
    session = LiveV2Session(max_retained_samples=8)
    session.accept(frame(LiveLane.MICROPHONE, 0, 3))

    failed = session.fail_lane(LiveLane.MICROPHONE, "helper_inactive").to_dict()
    assert failed["lanes"]["microphone"]["health"] == "failed"
    assert failed["lanes"]["microphone"]["failure_code"] == "helper_inactive"
    assert failed["lanes"]["microphone"]["failed_samples"] == 3
    assert failed["lanes"]["microphone"]["retained_samples"] == 0
    assert session.accept(frame(LiveLane.SYSTEM, 0, 1)).sequence == 0
    with pytest.raises(LiveV2SessionTerminalError):
        session.accept(frame(LiveLane.MICROPHONE, 1, 1))

    stopped = asyncio.run(session.stop(0.0)).to_dict()
    assert stopped["status"] == "failed"
    assert stopped["lanes"]["microphone"]["accepted_samples"] == (
        stopped["lanes"]["microphone"]["accounted_samples"]
        + stopped["lanes"]["microphone"]["failed_samples"]
    )


def test_registry_expiry_returns_terminal_snapshot_and_releases_session():
    registry = LiveV2SessionRegistry(max_retained_samples=4)
    session = registry.create("session-1")
    session.accept(frame(LiveLane.SYSTEM, 0, 4))

    expired = registry.expire("session-1", "helper_inactive").to_dict()

    assert "session-1" not in registry
    assert expired["status"] == "failed"
    assert expired["terminal_reason"] == "helper_inactive"
    assert expired["lanes"]["system"]["failed_samples"] == 4
    assert expired["lanes"]["system"]["retained_samples"] == 0
