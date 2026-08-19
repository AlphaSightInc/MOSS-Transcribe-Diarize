#!/usr/bin/env python3
"""Measure whether the production event writer may be read before its final drain.

This is bench-only code. It exercises the production ``_CanonicalEventLogWriter``
and the runner's lifecycle evaluator with a complete fair lifecycle, then compares
the evaluator's result before and after the writer's non-closing ``drain()`` barrier.
It changes neither runtime scheduling nor any preregistered gate value.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
ROUTE_PROBE_DIR = ROOT / "prototypes" / "browser-capture-feasibility"
if str(ROUTE_PROBE_DIR) not in sys.path:
    sys.path.insert(0, str(ROUTE_PROBE_DIR))

from production_route_server import _CanonicalEventLogWriter  # noqa: E402
from run_cpu_hf_local_measurement import _atomic_json, _canonical_lifecycle_fairness  # noqa: E402


def _complete_fair_lifecycle(*, sessions: int, items_per_session: int) -> list[dict[str, Any]]:
    """Build ordinary queue/start/process records with no pending work at the end."""
    events: list[dict[str, Any]] = []
    for item_id in range(items_per_session):
        for session_number in range(sessions):
            events.append(
                {
                    "session_id": f"session-{session_number}",
                    "kind": "canonical_queued",
                    "payload": {"item_id": item_id},
                }
            )
        for session_number in range(sessions):
            events.append(
                {
                    "session_id": f"session-{session_number}",
                    "kind": "canonical_started",
                    "payload": {"item_id": item_id},
                }
            )
        for session_number in range(sessions):
            events.append(
                {
                    "session_id": f"session-{session_number}",
                    "kind": "canonical_processed",
                    "payload": {"item_id": item_id},
                }
            )
    return events


def _read_lifecycle(path: Path) -> dict[str, Any]:
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    try:
        events = [json.loads(line) for line in raw_lines]
    except json.JSONDecodeError as error:
        return {
            "readable": False,
            "line_count": len(raw_lines),
            "json_error": str(error),
            "events": [],
        }
    return {"readable": True, "line_count": len(raw_lines), "events": events}


def _wait_for_writer_activity(writer: _CanonicalEventLogWriter, *, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        stats = writer.stats()
        if stats["write_elapsed_ns"] > 0:
            return {"writer_activity_observed": True, "stats": stats}
        time.sleep(0.001)
    return {"writer_activity_observed": False, "stats": writer.stats()}


def _trial(*, sessions: int, items_per_session: int, writer_activity_timeout_seconds: float) -> dict[str, Any]:
    session_ids = {f"session-{number}" for number in range(sessions)}
    expected = _complete_fair_lifecycle(sessions=sessions, items_per_session=items_per_session)
    with tempfile.TemporaryDirectory(prefix="moss-writer-evaluator-boundary-") as scratch:
        path = Path(scratch) / "canonical.jsonl"
        writer = _CanonicalEventLogWriter(path)
        try:
            for event in expected:
                writer.append(event)
            before = _wait_for_writer_activity(
                writer, timeout_seconds=writer_activity_timeout_seconds
            )
            immediate = _read_lifecycle(path)
            immediate["fairness"] = _canonical_lifecycle_fairness(
                immediate["events"], session_ids, maximum_skew=1
            )
            drain_completed = writer.drain(timeout_seconds=writer_activity_timeout_seconds)
            drained = _read_lifecycle(path)
            drained["fairness"] = _canonical_lifecycle_fairness(
                drained["events"], session_ids, maximum_skew=1
            )
        finally:
            writer.close()
        after = writer.stats()
    return {
        "expected_event_count": len(expected),
        "writer_activity_before_read": before,
        "immediate_read": {key: value for key, value in immediate.items() if key != "events"},
        "drain_completed": drain_completed,
        "drained_read": {key: value for key, value in drained.items() if key != "events"},
        "writer_stats_after_close": after,
        "race_observed": (
            before["writer_activity_observed"]
            and immediate["line_count"] < len(expected)
            and drain_completed
            and drained["readable"]
            and drained["line_count"] == len(expected)
            and not immediate["fairness"]["passes"]
            and drained["fairness"]["passes"]
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--sessions", type=int, default=2)
    parser.add_argument("--items-per-session", type=int, default=8)
    parser.add_argument("--writer-activity-timeout-seconds", type=float, default=2.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.attempts < 1 or args.sessions < 2 or args.items_per_session < 1:
        parser.error("attempts and items-per-session must be positive; sessions must be at least two")
    if args.writer_activity_timeout_seconds <= 0:
        parser.error("writer activity timeout must be positive")
    return args


def main() -> int:
    args = parse_args()
    trials = [
        _trial(
            sessions=args.sessions,
            items_per_session=args.items_per_session,
            writer_activity_timeout_seconds=args.writer_activity_timeout_seconds,
        )
        for _ in range(args.attempts)
    ]
    result = {
        "schema": "moss-writer-evaluator-boundary-prototype.v1",
        "question": (
            "Can the production asynchronous canonical-event writer make a complete lifecycle "
            "evaluate as incomplete when the runner reads its file before the writer drains?"
        ),
        "production_code_path": {
            "writer": "prototypes/browser-capture-feasibility/production_route_server.py:_CanonicalEventLogWriter",
            "evaluator": "prototypes/streaming-diarization/concurrency/run_cpu_hf_local_measurement.py:_canonical_lifecycle_fairness",
        },
        "inputs": {
            "attempts": args.attempts,
            "sessions": args.sessions,
            "items_per_session": args.items_per_session,
            "writer_activity_timeout_seconds": args.writer_activity_timeout_seconds,
        },
        "trials": trials,
        "verdict": {
            "race_observed_in_all_trials": all(trial["race_observed"] for trial in trials),
            "required_repair_boundary": (
                "The measurement runner must wait for a writer-owned drain barrier before it reads "
                "canonical lifecycle evidence; do not alter fairness or drain gate values."
            ),
        },
    }
    if args.output is not None:
        _atomic_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"]["race_observed_in_all_trials"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
