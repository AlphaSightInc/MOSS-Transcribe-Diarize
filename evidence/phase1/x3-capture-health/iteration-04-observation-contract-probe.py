#!/usr/bin/env python3
"""Measure which capture-health facts survive the production v2 snapshot.

Run from the repository root:
  PYTHONPATH=. .venv/bin/python evidence/phase1/x3-capture-health/iteration-04-observation-contract-probe.py \
    --write evidence/phase1/x3-capture-health/iteration-04-observation-contract.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from moss_transcribe_diarize.app.live_ingest import LiveV2LaneCapacityError
from moss_transcribe_diarize.app.live_lane_contract import LiveLane, LiveV2Frame, LiveV2OutOfOrderFrameError
from moss_transcribe_diarize.app.live_v2_session import LiveV2Session


def _frame(*, sequence: int, silent: bool, capture_timestamp_ns: int = 0) -> LiveV2Frame:
    return LiveV2Frame(
        lane=LiveLane.MICROPHONE,
        sequence=sequence,
        capture_timestamp_ns=capture_timestamp_ns,
        device_epoch=0,
        silent=silent,
        discontinuity=False,
        sample_rate=1,
        sample_count=1,
        pcm=b"\0\0",
    )


def _snapshot_after_one_frame(*, silent: bool) -> tuple[LiveV2Session, dict[str, object]]:
    session = LiveV2Session(max_retained_samples=1)
    session.accept(_frame(sequence=0, silent=silent))
    return session, session.snapshot().to_dict()


def _run_probe() -> dict[str, object]:
    silent_session, silent_snapshot = _snapshot_after_one_frame(silent=True)
    voiced_session, voiced_snapshot = _snapshot_after_one_frame(silent=False)
    assert silent_snapshot == voiced_snapshot

    silent_session.account_through({LiveLane.MICROPHONE: 0})
    accounted_silent_snapshot = silent_session.snapshot().to_dict()
    assert not silent_session.retained_frames(LiveLane.MICROPHONE)

    before_wait = voiced_session.snapshot().to_dict()
    started_ns = time.monotonic_ns()
    time.sleep(0.025)
    elapsed_ns = time.monotonic_ns() - started_ns
    after_wait = voiced_session.snapshot().to_dict()
    assert before_wait == after_wait

    gap_session, gap_before = _snapshot_after_one_frame(silent=False)
    gap_errors: list[str] = []
    for _ in range(3):
        try:
            gap_session.accept(_frame(sequence=2, silent=False))
        except LiveV2OutOfOrderFrameError as exc:
            gap_errors.append(type(exc).__name__)
    gap_after = gap_session.snapshot().to_dict()
    assert len(gap_errors) == 3
    assert gap_before == gap_after

    capacity_session, capacity_before = _snapshot_after_one_frame(silent=False)
    capacity_errors: list[str] = []
    for _ in range(2):
        try:
            capacity_session.accept(_frame(sequence=1, silent=False))
        except LiveV2LaneCapacityError as exc:
            capacity_errors.append(type(exc).__name__)
    capacity_after = capacity_session.snapshot().to_dict()
    assert len(capacity_errors) == 2
    assert capacity_before == capacity_after

    lane_keys = set(silent_snapshot["lanes"][LiveLane.MICROPHONE.value])
    required_observations = {
        "last_server_arrival_monotonic_ns",
        "consecutive_silent_samples",
        "consecutive_sequence_rejections",
        "consecutive_backpressure_rejections",
    }
    assert required_observations.isdisjoint(lane_keys)

    return {
        "question": "Does the production LiveV2Session snapshot retain the server facts needed for capture-health policy?",
        "production_path": "LiveV2Session.accept -> LiveV2Session.snapshot/account_through",
        "snapshot_lane_keys": sorted(lane_keys),
        "missing_required_observations": sorted(required_observations),
        "silent_vs_voiced": {
            "inputs": {"silent": True, "voiced": False},
            "snapshots_equal_before_accounting": silent_snapshot == voiced_snapshot,
            "accounted_silent_snapshot": accounted_silent_snapshot,
            "retained_frame_count_after_accounting": len(
                silent_session.retained_frames(LiveLane.MICROPHONE)
            ),
        },
        "recency": {
            "server_monotonic_elapsed_ns": elapsed_ns,
            "snapshot_equal_after_wait": before_wait == after_wait,
            "client_capture_timestamp_is_not_a_snapshot_field": True,
        },
        "sequence_gap": {
            "rejection_count_exercised": len(gap_errors),
            "errors": gap_errors,
            "snapshot_equal_after_rejections": gap_before == gap_after,
        },
        "backpressure": {
            "rejection_count_exercised": len(capacity_errors),
            "errors": capacity_errors,
            "snapshot_equal_after_rejections": capacity_before == capacity_after,
        },
        "verdict": (
            "The v2 snapshot retains cumulative accounting and lane health, but not server arrival "
            "time, silence history, sequence-rejection history, or backpressure history. "
            "Capture-health policy cannot truthfully infer those facts from this snapshot alone."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()
    result = _run_probe()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write is not None:
        args.write.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
