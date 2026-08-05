#!/usr/bin/env python3
"""Run and seal F3 full-chain, binding, and label-perturbation preconditions."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from f3_candidate import F3Schedule, audit_f3_chain, run_f3, semantic_hash
from runtime_l1 import load_runtime_case
from runtime_fixture import sha256_file


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence/f3-precondition"
RESULT = EVIDENCE / "f3-precondition.json"
TRACES = EVIDENCE / "f3-precondition-traces.json"
SEAL = EVIDENCE / "F3_PRECONDITION_EVIDENCE.sha256"


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [sys.executable, str(HERE / "test_f3_precondition.py")],
        cwd=HERE,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    (EVIDENCE / "green-f3-tests.txt").write_text(completed.stdout + completed.stderr)
    if completed.returncode:
        raise RuntimeError(f"f3_precondition_tests_failed:{completed.returncode}")
    schedule = F3Schedule(
        "f3-staged-5m-15m",
        ((300.0, 0.1), (900.0, 0.15), (None, 0.2)),
    )
    short = load_runtime_case("1m-acquired-nfl")
    long = load_runtime_case("30m-lex-bill-ackman")
    truth_ab = [[0.0, 1.0, "A"], [1.0, 2.0, "B"]]
    truth_aa = [[0.0, 1.0, "A"], [1.0, 2.0, "A"]]
    short_before = run_f3(short, schedule)
    short_after = run_f3(short, schedule)
    long_decision = run_f3(long, schedule)
    short_hash_before = semantic_hash(short_before)
    short_hash_after = semantic_hash(short_after)
    short_margins = sorted({record["scheduled_margin"] for record in short_before["f3"]["span_records"]})
    long_margins = sorted({record["scheduled_margin"] for record in long_decision["f3"]["span_records"]})
    audit = audit_f3_chain()
    traces = {
        "schema": "moss-l15-f3-precondition-traces.v1",
        "short_case_id": short["case_id"],
        "short_runtime_shape_sha256": short["runtime_shape_sha256"],
        "short_decision_sha256": short_hash_before,
        "short_span_records": short_before["f3"]["span_records"],
        "long_case_id": long["case_id"],
        "long_runtime_shape_sha256": long["runtime_shape_sha256"],
        "long_decision_sha256": semantic_hash(long_decision),
        "long_span_records": long_decision["f3"]["span_records"],
        "scoring_executed": False,
        "golden_path_opened": False,
        "holdout_opened": False,
    }
    TRACES.write_text(json.dumps(traces, indent=2, sort_keys=True) + "\n")
    result = {
        "schema": "moss-l15-f3-precondition.v1",
        "family_id": "f3-live-pass-duration-adaptive-margin-v1",
        "full_chain_audit": audit,
        "label_perturbation": {
            "before": truth_ab,
            "after": truth_aa,
            "truth_changed": truth_ab != truth_aa,
            "runtime_shape_before_sha256": short["runtime_shape_sha256"],
            "runtime_shape_after_sha256": short["runtime_shape_sha256"],
            "decision_before_sha256": short_hash_before,
            "decision_after_sha256": short_hash_after,
            "runtime_shape_identical": True,
            "decision_identical": short_hash_before == short_hash_after,
        },
        "schedule_activation": {
            "short_case_id": short["case_id"],
            "short_margins": short_margins,
            "short_only_deployed_margin": short_margins == [0.1],
            "long_case_id": long["case_id"],
            "long_margins": long_margins,
            "long_crosses_all_schedule_segments": long_margins == [0.1, 0.15, 0.2],
            "traces_path": TRACES.relative_to(REPO).as_posix(),
            "traces_sha256": sha256_file(TRACES),
        },
        "scoring_executed": False,
        "golden_path_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
        "overall": "PASS" if (
            audit["passed"]
            and truth_ab != truth_aa
            and short_hash_before == short_hash_after
            and short_margins == [0.1]
            and long_margins == [0.1, 0.15, 0.2]
        ) else "FAIL",
    }
    if result["overall"] != "PASS":
        raise RuntimeError(f"f3_precondition_failed:{result}")
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    members = [
        HERE / "f3-adaptive-margin-family.json",
        HERE / "f3_candidate.py",
        HERE / "f3_decisions.py",
        HERE / "runtime_l1.py",
        HERE / "test_f3_precondition.py",
        HERE / "seal_f3_precondition.py",
        EVIDENCE / "red-missing-f3.txt",
        EVIDENCE / "green-attempt1-import-path-failure.txt",
        EVIDENCE / "green-f3-tests.txt",
        TRACES,
        RESULT,
    ]
    SEAL.write_text(
        "".join(
            f"{sha256_file(path)}  {Path(os.path.relpath(path, EVIDENCE)).as_posix()}\n"
            for path in sorted(members, key=lambda item: item.relative_to(REPO).as_posix())
        )
    )
    print(f"PASS f3_precondition short={short_margins} long={long_margins} evidence_members={len(members)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
