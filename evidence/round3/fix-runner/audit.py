"""Offline audit of the retained literal S7/S8 result; makes no decoder calls."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
result = json.loads((HERE / "s7-s8-2x300/result.json").read_text())
receipt = json.loads((HERE / "request-receipt.json").read_text())

assert result["clean"] is True and result["failures"] == []
assert (result["sessions"], result["seconds"]) == (2, 300)
assert result["scheduled_session_seconds"] == [300, 300]
assert [row["clip"].split(":", 1)[0] for row in result["session_results"]] == [
    "mono_javier_intro_50s",
    "discussion_jamie_dimon_180s",
]
assert result["mixed_background"]["scheduled_at_seconds"] == 60.0
assert result["mixed_background"]["source_seconds"] == 150
assert result["mixed_background"]["clean"] is True

for session in result["session_results"]:
    assert session["clean"] is True
    assert session["p95_canonical_lag"] < 10
    assert session["accepted_samples"] == session["accounted_samples"] == 4_800_000
    assert session["retries"] == session["wrong_owner_failures"] == 0
    backlog = session["live_backlog_measurements"]
    assert abs(backlog["last_third_median_seconds"] - backlog["first_third_median_seconds"]) < 1

dispatch = result["dispatch_measurement"]
assert dispatch["passes"] is True
assert dispatch["completed_windows"] == dispatch["full_denominator"] == 342
assert (dispatch["maximum_total_inflight"], dispatch["maximum_background_inflight"]) == (2, 1)
assert dispatch["live_preemptions"] == {"observed": 10, "passed": 10}
assert len(dispatch["file_acceptance_to_first_dispatch_sec"]) == 3
assert max(dispatch["file_acceptance_to_first_dispatch_sec"].values()) <= 12
assert all(dispatch["fair_file_interleaving"].values())
assert dispatch["terminal_vs_terminal_wait_sec"] > 0
assert all(
    set(row) >= {
        "owner_kind", "owner_key", "window_index", "accepted_monotonic_ns",
        "wait_started_monotonic_ns", "started_monotonic_ns", "ended_monotonic_ns",
    }
    for row in dispatch["windows"]
)

paired = result["paired_stop_file"]
assert paired["clean"] is True
assert 0 <= paired["stop_request_gap_sec"] < 1
assert 0 <= paired["file_submit_after_last_stop_sec"] < 1
assert paired["dispatch"]["acceptance_to_first_dispatch_sec"] <= 12
assert paired["dispatch"]["fair_interleaving"] is True
assert paired["file"]["finished_at_seconds"] > paired["file"]["accepted_at_seconds"]

assert result["foreign_load_detected"] is False
assert result["maximum_own_inflight"] == 2
assert receipt["requests_started"] == receipt["requests_finished"] == result["decoder_calls"] == 342
assert receipt["budget"] == 400 and receipt["tunnel_closed"] is True
assert receipt["gpu_lease_released"] is True

print(json.dumps({
    "verdict": "PASS",
    "sessions": "2x300",
    "dispatch_windows": "342/342",
    "live_preemptions": "10/10",
    "decoder_requests": "342/400",
}, sort_keys=True))
