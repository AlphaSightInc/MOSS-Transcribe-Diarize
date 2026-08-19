#!/usr/bin/env python3
"""Audit whether a saved W2 lifecycle log is complete enough to re-score.

This bench-only probe never starts a route, model, or tunnel.  It compares the
event-log line count against the cumulative writer counters captured in the
saved run state, so a previous asynchronous writer race cannot be reclassified
as scheduler or stop-drain behavior after the fact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from run_cpu_hf_local_measurement import _atomic_json


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number} must contain one JSON object")
        events.append(value)
    return events


def _phase_event_count(phase: dict[str, Any]) -> int:
    instrumentation = phase.get("canonical_event_log_instrumentation")
    if not isinstance(instrumentation, dict):
        raise ValueError("phase lacks canonical event-log instrumentation")
    event_log = instrumentation.get("event_log")
    if not isinstance(event_log, dict):
        raise ValueError("phase instrumentation lacks an event-log object")
    event_count = event_log.get("event_count")
    if not isinstance(event_count, int) or event_count < 0:
        raise ValueError("phase event-log counter must be a non-negative integer")
    return event_count


def audit_saved_lifecycle(run_directory: Path) -> dict[str, Any]:
    state_path = run_directory / "run-state.json"
    event_log_path = run_directory / "canonical-processed.jsonl"
    state = _read_json_object(state_path)
    events = _read_jsonl(event_log_path)
    phases = state.get("phases")
    if not isinstance(phases, list):
        raise ValueError("run state lacks a phases list")

    phase_records: list[dict[str, Any]] = []
    seen_session_ids: set[str] = set()
    expected_cumulative_count = 0
    actual_cumulative_count = 0
    validation_errors: list[str] = []
    for phase_index, phase in enumerate(phases):
        if not isinstance(phase, dict) or phase.get("kind") not in {"normal", "overload"}:
            continue
        raw_session_ids = phase.get("sessions")
        if not isinstance(raw_session_ids, list) or not raw_session_ids or not all(
            isinstance(session_id, str) and session_id for session_id in raw_session_ids
        ):
            validation_errors.append(f"phase {phase_index} lacks non-empty session ids")
            continue
        session_ids = set(raw_session_ids)
        if len(session_ids) != len(raw_session_ids):
            validation_errors.append(f"phase {phase_index} repeats a session id")
            continue
        overlap = sorted(seen_session_ids & session_ids)
        if overlap:
            validation_errors.append(f"phase {phase_index} reuses earlier session ids")
            continue
        seen_session_ids.update(session_ids)
        try:
            cumulative_counter = _phase_event_count(phase)
        except ValueError as error:
            validation_errors.append(f"phase {phase_index}: {error}")
            continue
        expected_phase_count = cumulative_counter - expected_cumulative_count
        if expected_phase_count < 0:
            validation_errors.append(f"phase {phase_index} decreases the cumulative writer counter")
            continue
        actual_phase_count = sum(event.get("session_id") in session_ids for event in events)
        actual_cumulative_count += actual_phase_count
        phase_records.append(
            {
                "phase_index": phase_index,
                "phase_name": phase.get("name"),
                "phase_kind": phase.get("kind"),
                "session_count": len(session_ids),
                "expected_cumulative_writer_records": cumulative_counter,
                "expected_phase_records": expected_phase_count,
                "actual_phase_records": actual_phase_count,
                "complete": actual_phase_count == expected_phase_count,
            }
        )
        expected_cumulative_count = cumulative_counter

    terminal_counter_matches_raw_log = (
        expected_cumulative_count == len(events) == actual_cumulative_count
    )
    all_phase_records_complete = bool(phase_records) and all(
        record["complete"] for record in phase_records
    )
    rescore_permitted = (
        not validation_errors
        and terminal_counter_matches_raw_log
        and all_phase_records_complete
    )
    return {
        "schema": "moss-saved-lifecycle-completeness-prototype.v1",
        "question": (
            "Is a saved asynchronous canonical lifecycle log complete enough to re-score its "
            "fairness or stop-drain predicates without another live matrix run?"
        ),
        "inputs": {
            "run_directory": str(run_directory),
            "run_state_sha256": _sha256(state_path),
            "event_log_sha256": _sha256(event_log_path),
        },
        "event_log": {
            "raw_line_count": len(events),
            "terminal_writer_counter": expected_cumulative_count,
            "phase_attributed_record_count": actual_cumulative_count,
            "terminal_counter_matches_raw_log": terminal_counter_matches_raw_log,
        },
        "phase_records": phase_records,
        "validation_errors": validation_errors,
        "verdict": {
            "rescore_permitted": rescore_permitted,
            "required_next_step": (
                "A full, fresh frozen matrix is required; do not reclassify lifecycle, fairness, "
                "or stop-drain findings from this incomplete saved log."
                if not rescore_permitted
                else "Saved lifecycle evidence is complete; re-score only with the current separated predicates."
            ),
            "does_not_establish": [
                "scheduler fairness",
                "stop-drain correctness",
                "G4",
                "G5",
                "any new live service or inference result",
            ],
        },
        "oracle_history": {
            "named_degenerate_oracles": [
                "repeated-marker integrity oracle",
                "unscoped fairness counter",
                "writer/evaluator observation race",
            ],
            "lesson": (
                "A confident derived number is unusable unless its source evidence is complete and its "
                "predicate measures only the behavior it names."
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = audit_saved_lifecycle(args.run_directory)
    if args.output is not None:
        _atomic_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
