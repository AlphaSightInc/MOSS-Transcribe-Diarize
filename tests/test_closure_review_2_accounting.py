"""Review-2 receipt control; all transports are replaced before execution."""

from __future__ import annotations

import argparse
import runpy
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_f3s_503_remains_one_actual_decoder_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feature = runpy.run_path(str(ROOT / "prototypes/feature-rows/run.py"))
    counters = feature["ProxyCounters"]
    before = counters()
    after = counters(
        accepted=1,
        completed=0,
        upstream_failed=1,
        peak_in_flight=1,
        event_count=2,
        row_attempted=1,
        row_upstream_failed=1,
        distinct_attempt_ids=1,
        row_owners=("summaries",),
        row_reconciled=True,
    )
    snapshots = iter((before, after))
    monkeypatch.setitem(feature["execute"].__globals__, "proxy_counters", lambda *_a, **_k: next(snapshots))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess([], 1, stdout="", stderr="controlled 503"),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-control-only")
    args = argparse.Namespace(
        allow_decoder=True,
        allow_provider=True,
        base="http://127.0.0.1:1",
        decoder_proxy_log=tmp_path / "unused.jsonl",
    )
    receipt, code = feature["execute"](args, feature["summary_plan"]())

    assert code == 2
    assert receipt["status"] == "INCOMPLETE"
    assert receipt["decoder_proxy_counter_deltas"]["accepted"] == 1
    assert receipt["decoder_proxy_counter_deltas"]["upstream_failed"] == 1
    assert receipt["actual_calls"]["decoder"] == 1
