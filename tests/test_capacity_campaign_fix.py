"""Fix-pass controls for attributed S7/S8 capacity measurements."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "prototypes" / "capacity-campaign"


def _measurement_module():
    path = CAMPAIGN / "measurement.py"
    spec = importlib.util.spec_from_file_location("capacity_fix_measurement", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _row(kind, key, index, accepted, started, ended):
    return {
        "owner_kind": kind,
        "owner_key": key,
        "window_index": index,
        "accepted_monotonic_ns": accepted,
        "wait_started_monotonic_ns": accepted,
        "started_monotonic_ns": started,
        "ended_monotonic_ns": ended,
    }


def test_capacity_runner_exposes_paired_stop_file_hook():
    result = subprocess.run(
        [sys.executable, str(CAMPAIGN / "run.py"), "--help"],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "."},
        capture_output=True,
        text=True,
        check=True,
    )

    assert "--paired-stop-file" in result.stdout


def test_attributed_stage_clocks_accept_fair_window_interleaving():
    measurement = _measurement_module()
    second = 1_000_000_000
    rows = [
        _row("background", "terminal-a", 0, 0, 0, 5 * second),
        _row("background", "terminal-b", 0, second // 10, 5 * second, 10 * second),
        _row("live", "live-waiter", 0, 4 * second, 4 * second, 5 * second),
        _row("background", "file-one", 0, second, 10 * second, 15 * second),
        _row("background", "terminal-a", 1, 5 * second, 15 * second, 20 * second),
        _row("background", "terminal-b", 1, 10 * second, 20 * second, 25 * second),
    ]

    summary = measurement.summarize_dispatch(
        rows,
        file_acceptances_ns={"file-one": second},
        terminal_keys={"terminal-a", "terminal-b"},
        first_dispatch_limit_sec=12,
    )

    assert summary["passes"] is True
    assert summary["full_denominator"] == summary["completed_windows"] == 6
    assert summary["maximum_total_inflight"] == 2
    assert summary["maximum_background_inflight"] == 1
    assert summary["file_acceptance_to_first_dispatch_sec"] == {"file-one": 9.0}
    assert summary["fair_file_interleaving"] == {"file-one": True}
    assert summary["live_preemptions"]["observed"] >= 1
    assert summary["live_preemptions"]["passed"] == summary["live_preemptions"]["observed"]
    assert summary["terminal_vs_terminal_wait_sec"] > 0


def test_unattributed_proxy_rows_and_whole_batch_hold_are_refused():
    measurement = _measurement_module()
    with pytest.raises(ValueError, match="attributed"):
        measurement.summarize_dispatch(
            [{"kind": "start", "time": 1.0}],
            file_acceptances_ns={"file-one": 0},
            terminal_keys={"terminal-a", "terminal-b"},
            first_dispatch_limit_sec=12,
        )

    second = 1_000_000_000
    held = [
        _row("background", "terminal-a", 0, 0, 0, 15 * second),
        _row("background", "file-one", 0, second, 15 * second, 20 * second),
    ]
    summary = measurement.summarize_dispatch(
        held,
        file_acceptances_ns={"file-one": second},
        terminal_keys={"terminal-a"},
        first_dispatch_limit_sec=12,
    )

    assert summary["passes"] is False
    assert summary["fair_file_interleaving"] == {"file-one": False}
    assert summary["file_acceptance_to_first_dispatch_sec"] == {"file-one": 14.0}
