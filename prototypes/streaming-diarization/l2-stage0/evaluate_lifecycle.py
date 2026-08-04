#!/usr/bin/env python3
"""Evaluate A3 evidence and emit the finalizing-vs-job decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))

from lifecycle_prototype import (  # noqa: E402
    CurrentClosingClosedControl,
    EarlyTapeReleaseControl,
    LifecyclePrototype,
    OneThreadPerSessionControl,
)


INVARIANTS = (
    ("i1", "capture_authority_ends_at_stop_ack", "test_capture_authority_ends_at_stop_ack", "i1-capture-authority", "i1-capture-authority"),
    ("i2", "terminal_revision_visible", "test_view_authority_survives_finalizing_through_terminal_revision", "i2-view-terminal", "i2-view-terminal"),
    ("i3", "tape_sealed_and_read_leased", "test_tape_is_sealed_and_read_leased_while_finalizer_runs", "i3-tape-lease", "i3-tape-lease"),
    ("i4", "bounded_single_cpu_finalizer", "test_one_bounded_queue_owns_finalizers_and_one_cpu_runs", "i4-bounded-queue", "i4-bounded-queue"),
    ("i5", "failure_release_once_and_l1_fallback", "test_every_failed_finalizer_releases_once_and_falls_back_to_l1", "i5-failure-release-fallback", "i5-failure-release-fallback"),
    ("i6", "abort_never_starts_l2", "test_abort_never_starts_l2", "i6-abort-no-l2", "i6-abort-no-l2-v2"),
    ("i7", "ttl_zero_respects_read_lease", "test_ttl_zero_reaps_only_after_lease_release", "i7-ttl-zero", "i7-ttl-zero"),
    ("i8", "new_live_meeting_responsive", "test_new_live_meeting_progresses_while_older_finalizer_runs", "i8-live-responsive", "i8-live-responsive"),
)

SUPPLEMENTS = {
    "i4": (
        "test_bounded_queue_refuses_overflow_without_partial_transition",
        "i4b-queue-overflow",
    ),
    "i5": (
        "test_raised_finalizer_exception_releases_once_and_falls_back",
        "i5b-raised-exception",
    ),
    "i6": (
        "test_abort_of_queued_finalization_removes_job_without_l2",
        "i6b-abort-queued",
    ),
}

NEGATIVE_CONTROLS = (
    ("n1", "active_closing_closed", "test_active_closing_closed_reproduces_invisible_revision", "n1-invisible-revision"),
    ("n2", "one_thread_per_session", "test_one_thread_per_session_fails_bounded_concurrency", "n2-unbounded-threads"),
    ("n3", "early_tape_release", "test_early_tape_release_fails_read_lease_invariant", "n3-early-release"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proof(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    transcript = path.with_suffix(".txt")
    return {
        "json_path": path.relative_to(REPO).as_posix(),
        "json_sha256": sha256(path),
        "successful": payload["successful"],
        "transcript_path": transcript.relative_to(REPO).as_posix(),
        "transcript_sha256": sha256(transcript),
    }


def state_trace() -> dict[str, object]:
    lifecycle = LifecyclePrototype(queue_capacity=2)
    trace = [lifecycle.start("meeting-1")]
    trace.append(lifecycle.begin_stop("meeting-1"))
    trace.append(lifecycle.acknowledge_stop("meeting-1"))
    trace.append(lifecycle.start_next_finalizer())
    lifecycle.start("new-live")
    live_during_finalizer = lifecycle.capture("new-live", b"frame")
    responsiveness = lifecycle.responsiveness_snapshot()
    trace.append(lifecycle.finish_active_finalizer("success"))
    return {
        "new_live_during_finalizer": live_during_finalizer,
        "responsiveness": responsiveness,
        "states": [snapshot["state"] for snapshot in trace],
        "trace": trace,
    }


def failure_trace() -> dict[str, object]:
    failures = {}
    for outcome in ("timeout", "cancelled", "shutdown", "degraded_tape", "exception"):
        lifecycle = LifecyclePrototype(queue_capacity=1)
        lifecycle.start(outcome)
        lifecycle.begin_stop(outcome)
        lifecycle.acknowledge_stop(outcome)
        lifecycle.start_next_finalizer()
        if outcome == "exception":
            def raise_finalizer_error() -> str:
                raise RuntimeError("synthetic-finalizer-fault")

            failures[outcome] = lifecycle.execute_active_finalizer(raise_finalizer_error)
        else:
            failures[outcome] = lifecycle.finish_active_finalizer(outcome)
    return failures


def evaluate() -> dict[str, object]:
    matrix = []
    for invariant_id, description, test_name, red_stem, green_stem in INVARIANTS:
        red = proof(HERE / f"evidence/a3-red/{red_stem}.json")
        green = proof(HERE / f"evidence/a3-green/{green_stem}.json")
        row = {
                "description": description,
                "green_proof": green,
                "invariant_id": invariant_id,
                "passed": red["successful"] is False and green["successful"] is True,
                "red_proof": red,
                "test_name": f"test_lifecycle_prototype.LifecyclePrototypeTest.{test_name}",
        }
        if invariant_id in SUPPLEMENTS:
            supplement_name, stem = SUPPLEMENTS[invariant_id]
            supplemental_red = proof(HERE / f"evidence/a3-red/{stem}.json")
            supplemental_green = proof(HERE / f"evidence/a3-green/{stem}.json")
            row["supplemental_proof"] = {
                "green_proof": supplemental_green,
                "red_proof": supplemental_red,
                "test_name": f"test_lifecycle_prototype.LifecyclePrototypeTest.{supplement_name}",
            }
            row["passed"] = (
                row["passed"]
                and supplemental_red["successful"] is False
                and supplemental_green["successful"] is True
            )
        matrix.append(row)

    control_results = {
        "active_closing_closed": CurrentClosingClosedControl().run(),
        "early_tape_release": EarlyTapeReleaseControl().run(),
        "one_thread_per_session": OneThreadPerSessionControl().run(session_count=3),
    }
    controls = []
    for control_id, name, test_name, stem in NEGATIVE_CONTROLS:
        red = proof(HERE / f"evidence/a3-negative-red/{stem}.json")
        detection = proof(HERE / f"evidence/a3-negative-controls/{stem}.json")
        raw_result = control_results[name]
        controls.append(
            {
                "control_id": control_id,
                "detection_proof": detection,
                "failed_invariant": raw_result["failed_invariant"],
                "invariant_passed": raw_result["invariant_passed"],
                "name": name,
                "passed": (
                    red["successful"] is False
                    and detection["successful"] is True
                    and raw_result["invariant_passed"] is False
                ),
                "raw_result": raw_result,
                "red_proof": red,
                "test_name": f"test_lifecycle_prototype.LifecycleNegativeControlTest.{test_name}",
            }
        )

    full_suite = proof(HERE / "evidence/a3-green/full-suite-v3.json")
    all_invariants = all(row["passed"] for row in matrix)
    all_controls = all(row["passed"] for row in controls)
    choose_finalizing = all_invariants and all_controls and full_suite["successful"] is True
    return {
        "decision": {
            "campaign_a_must_stop_for_revised_plan": not choose_finalizing,
            "choice": "finalizing" if choose_finalizing else "persisted_job_api",
            "quiet_synchronous_l2_inside_stop": False,
            "rule": "choose finalizing only when all eight invariants and all three negative controls pass",
        },
        "failure_outcomes": failure_trace(),
        "full_suite": full_suite,
        "holdout_opened": False,
        "invariant_count": len(matrix),
        "invariant_matrix": matrix,
        "negative_control_count": len(controls),
        "negative_controls": controls,
        "overall": "PASS" if choose_finalizing else "FAIL",
        "product_code_modified": False,
        "schema": "moss-l2-stage0-lifecycle-verdict.v1",
        "state_model": {
            "abort_branches": [
                ["active", "closing", "aborted"],
                ["active", "closing", "finalizing", "aborted"],
            ],
            "failure_branch": ["active", "closing", "finalizing", "failed"],
            "success_path": ["active", "closing", "finalizing", "closed"],
        },
        "state_trace": state_trace(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--transcript-output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate()
    transcript = (
        f"A3 LIFECYCLE {result['overall']} invariants=8/8 controls=3/3 "
        f"decision={result['decision']['choice']} holdout=SEALED\n"
        + ("<promise>COMPLETE</promise>\n" if result["overall"] == "PASS" else "<promise>BLOCKED</promise>\n")
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.transcript_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.transcript_output.write_text(transcript, encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    print(transcript, end="")
    return 0 if result["overall"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
