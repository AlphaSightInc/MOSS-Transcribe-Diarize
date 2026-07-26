from __future__ import annotations

import tempfile
from dataclasses import FrozenInstanceError

import pytest

pytest.importorskip("fastapi")

from live_integration_replay import LocalIntegrationReplay


def test_local_integration_replay_reports_http_only_helper_view_scenario():
    with tempfile.TemporaryDirectory() as tmpdir:
        report = LocalIntegrationReplay(tmpdir=tmpdir).run()

    assert report.session_created is True
    assert report.transcript_lines
    assert report.authority_redaction_checked is True
    assert report.exact_duplicate_ack == report.changed_payload_duplicate_ack
    assert report.replay_counter_unchanged is True
    assert report.system_continuation_ack.lane == "system"
    assert report.system_continuation_ack.sequence == 2
    assert report.helper_state == "capturing"
    assert report.helper_sequence == 2
    assert {
        lane.lane: (lane.state, lane.failure_code)
        for lane in report.helper_lanes
    }["microphone"] == ("failed", "permission_denied")
    lanes = {lane.lane: lane for lane in report.lanes}
    assert lanes["microphone"].health == "failed"
    assert lanes["microphone"].failure_code == "permission_denied"
    assert lanes["microphone"].failed_samples > 0
    assert lanes["system"].health == "active"
    assert lanes["system"].next_sequence == 2
    assert report.view_snapshot_status == "active"
    assert [event.seq for event in report.events] == sorted({event.seq for event in report.events})
    assert report.stop_deadline == 5.0
    assert report.stop_status_code == 409
    assert report.terminal_v2_status == "failed"
    assert report.terminal_reason == "permission_denied"
    assert {
        (exchange.action, exchange.status_code)
        for exchange in report.exchanges
    } >= {
        ("heartbeat:capture", 200),
        ("view:events", 200),
        ("view:snapshot:failed-lane", 200),
        ("view:stop", 409),
    }
    with pytest.raises(FrozenInstanceError):
        report.stop_deadline = 0.0
