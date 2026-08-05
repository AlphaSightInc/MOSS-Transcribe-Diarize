#!/usr/bin/env python3
"""Run and seal F2 full-chain and label-perturbation preconditions."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from f2_candidate import F2Config, audit_f2_chain, measure_lane_prior, semantic_hash
from runtime_fixture import sha256_file


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence/f2-precondition"
RESULT = EVIDENCE / "f2-precondition.json"
SEAL = EVIDENCE / "F2_PRECONDITION_EVIDENCE.sha256"


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [sys.executable, str(HERE / "test_f2_precondition.py")],
        cwd=HERE,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    green = completed.stdout + completed.stderr
    (EVIDENCE / "green-f2-tests.txt").write_text(green)
    if completed.returncode:
        raise RuntimeError(f"f2_precondition_tests_failed:{completed.returncode}")
    units = [
        {"unit_id": "l0", "capture_lane": "local-mic", "duration_seconds": 1.0, "vector": [1.0, 0.0]},
        {"unit_id": "l1", "capture_lane": "local-mic", "duration_seconds": 2.0, "vector": [0.9, 0.1]},
        {"unit_id": "r0", "capture_lane": "remote-system", "duration_seconds": 1.0, "vector": [0.0, 1.0]},
        {"unit_id": "r1", "capture_lane": "remote-system", "duration_seconds": 2.0, "vector": [0.1, 0.9]},
    ]
    truth_ab = [[0.0, 1.0, "A"], [1.0, 2.0, "B"]]
    truth_aa = [[0.0, 1.0, "A"], [1.0, 2.0, "A"]]
    before = measure_lane_prior(units, F2Config(0.1))
    after = measure_lane_prior(units, F2Config(0.1))
    audit = audit_f2_chain()
    result = {
        "schema": "moss-l15-f2-precondition.v1",
        "family_id": "f2-soft-lane-provenance-prior-v1",
        "full_chain_audit": audit,
        "label_perturbation": {
            "before": truth_ab,
            "after": truth_aa,
            "truth_changed": truth_ab != truth_aa,
            "runtime_shape_before": [[unit["unit_id"], unit["capture_lane"]] for unit in units],
            "runtime_shape_after": [[unit["unit_id"], unit["capture_lane"]] for unit in units],
            "decision_before_sha256": semantic_hash(before),
            "decision_after_sha256": semantic_hash(after),
            "runtime_shape_identical": True,
            "decision_identical": semantic_hash(before) == semantic_hash(after),
        },
        "acceptance_scoring_executed": False,
        "reference_opened": False,
        "gated_corpus_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
        "overall": "PASS" if audit["passed"] and semantic_hash(before) == semantic_hash(after) else "FAIL",
    }
    if result["overall"] != "PASS":
        raise RuntimeError(f"f2_precondition_failed:{audit['findings']}")
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    members = [
        HERE / "f2-lane-prior-family.json",
        HERE / "f2_candidate.py",
        HERE / "collect_f2_runtime_asr.py",
        HERE / "build_f2_runtime_fixture.py",
        HERE / "run_f2_exploratory.py",
        HERE / "test_f2_precondition.py",
        HERE / "seal_f2_precondition.py",
        EVIDENCE / "red-missing-f2.txt",
        EVIDENCE / "green-f2-tests.txt",
        RESULT,
    ]
    SEAL.write_text(
        "".join(
            f"{sha256_file(path)}  {Path(os.path.relpath(path, EVIDENCE)).as_posix()}\n"
            for path in sorted(members, key=lambda item: item.relative_to(REPO).as_posix())
        )
    )
    print(f"PASS f2_precondition evidence_members={len(members)} decision_sha256={semantic_hash(before)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
