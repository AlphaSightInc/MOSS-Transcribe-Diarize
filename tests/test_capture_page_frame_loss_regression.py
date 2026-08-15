"""Regression guard for the x1 P0: the capture page must not silently discard PCM.

The three browser probes under ``prototypes/browser-capture-feasibility/`` need a working
Chrome, so nothing in the suite notices if the page regresses. This test runs the committed
page's REAL transport script through ``page_sender_harness.mjs`` (Node vm + stubbed browser
APIs and strict-v2 route) and scores it with the SAME ``_lane_summary`` the committed
slow-POST gate uses.

Two directions, because only the pair is evidence:
  * the page as it stands must PASS the admitted-vs-elapsed-cadence assertion, and
  * the page with the historical one-in-flight drop guard put back must FAIL it.

This is a transport-semantics guard only: no AudioWorklet, no Chrome scheduler, no real HTTP
and no hidden-tab throttling. It does not replace G7 or the attended Gate-1 checklist.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = REPO_ROOT / "prototypes" / "browser-capture-feasibility"
HARNESS = PROTOTYPE / "page_sender_harness.mjs"

sys.path.insert(0, str(PROTOTYPE))

from probe_slow_post_characterization import _lane_summary  # noqa: E402

LANES = ("system", "microphone")
# A response slower than the frame period is what makes the defect observable at all.
_FRAMES = 24
_RESPONSE_DELAY_MS = 100
_SETTLE_MS = 3000


def _node() -> str:
    for candidate in ("/opt/homebrew/bin/node", "/usr/local/bin/node"):
        if Path(candidate).is_file():
            return candidate
    found = shutil.which("node")
    if found is None:
        pytest.skip("node is not available; the capture-page transport guard needs it")
    return found


def _run(mutation: str) -> dict:
    config = {
        "frames": _FRAMES,
        "frameDelayMs": _RESPONSE_DELAY_MS,
        "settleMs": _SETTLE_MS,
        "mutation": mutation,
    }
    completed = subprocess.run(
        [_node(), str(HARNESS), json.dumps(config)],
        cwd=str(PROTOTYPE),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.stdout.strip(), f"harness produced no output: {completed.stderr[-800:]}"
    payload = json.loads(completed.stdout)
    assert "error" not in payload, payload.get("error", "")[:800]
    return payload


def _cadence_delta(run: dict) -> dict[str, int]:
    descriptor = run["config"]["descriptor"]
    frame_period_ms = descriptor["frame_samples"] / descriptor["sample_rate"] * 1_000
    deltas = {}
    for lane in LANES:
        records = sorted(
            (record for record in run["server"]["telemetry"] if record.get("lane") == lane),
            key=lambda record: int(record.get("sequence", -1)),
        )
        summary = _lane_summary(
            records,
            frame_period_ms=frame_period_ms,
            accepted=run["server"]["accepted_by_lane"][lane],
        )
        deltas[lane] = summary["accepted_minus_elapsed_expected"]
    return deltas


def test_the_capture_page_admits_every_elapsed_cadence_frame_under_a_slow_post():
    run = _run("none")
    deltas = _cadence_delta(run)
    # The committed browser gate uses <= 1. Two frames of slack here absorbs Node-timer
    # jitter on a loaded machine without blunting the signal: the defect this pair guards
    # against shows up as roughly -25 over the same 24-frame window, not -2.
    assert all(abs(delta) <= 2 for delta in deltas.values()), deltas
    for lane in LANES:
        counters = run["scenario"]["lanes"][lane]
        assert counters["dropped_frames"] == 0, counters
        # One serial sender per lane: unbounded concurrency was the pre-branch behaviour.
        assert run["server"]["per_lane_max_concurrent"][lane] == 1, run["server"]


def test_the_cadence_assertion_fails_when_the_historical_drop_guard_returns():
    """If this ever passes, the gate above has stopped being able to fail."""
    run = _run("inflight_drop")
    assert run["mutation_applied"] is True
    deltas = _cadence_delta(run)
    # Well past the jitter slack the positive test allows, so the pair really does separate
    # "the sender is a bit behind" from "the sender threw a quarter of the meeting away".
    assert all(delta < -5 for delta in deltas.values()), deltas
    for lane in LANES:
        counters = run["scenario"]["lanes"][lane]
        # The defect's signature: audio is gone and nothing on the client says so.
        assert counters["sent"] < counters["emitted"] * 0.75, counters
        assert counters["dropped_frames"] == 0, counters


def test_a_forced_queue_overflow_is_counted_and_marked_discontinuous():
    """The PRD's fallback: if the page must drop, it may not drop silently."""
    node = _node()
    config = {
        "frames": 40,
        "frameDelayMs": 150,
        "settleMs": _SETTLE_MS,
        "descriptor": {
            "sample_rate": 16000,
            "frame_samples": 1000,
            "bounds": {
                "max_frame_samples": 16000,
                "max_retained_samples": 4000,  # one frame short of four periods of backlog
                "max_queue_depth": 64,
            },
        },
    }
    completed = subprocess.run(
        [node, str(HARNESS), json.dumps(config)],
        cwd=str(PROTOTYPE), capture_output=True, text=True, timeout=180,
    )
    payload = json.loads(completed.stdout)
    assert "error" not in payload, payload.get("error", "")[:800]
    heartbeat = payload["server"]["heartbeats"][-1]["lanes"]
    for lane in LANES:
        counters = payload["scenario"]["lanes"][lane]
        assert counters["frame_capacity"] == 4, counters
        assert counters["dropped_frames"] > 0, counters
        assert counters["discontinuities"] > 0, counters
        assert heartbeat[lane]["dropped_frames"] > 0, heartbeat
    assert any(record.get("discontinuity") for record in payload["server"]["acceptances"])
