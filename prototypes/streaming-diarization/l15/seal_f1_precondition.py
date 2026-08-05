#!/usr/bin/env python3
"""Run and seal F1's full-chain and label-perturbation preconditions."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from f1_candidate import F1Config, audit_f1_chain, decide_f1, semantic_hash
from runtime_l1 import load_runtime_case, run_runtime_l1
from runtime_fixture import sha256_file


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence" / "f1-precondition"
RESULT = EVIDENCE / "f1-precondition.json"
SEAL = EVIDENCE / "F1_PRECONDITION_EVIDENCE.sha256"


def main() -> int:
    runtime = load_runtime_case("1m-acquired-nfl")
    l1 = run_runtime_l1(runtime)
    config = F1Config(0.35, 0.10, 0.05)
    truth_ab = [[0.0, 1.0, "A"], [1.0, 2.0, "B"]]
    truth_aa = [[0.0, 1.0, "A"], [1.0, 2.0, "A"]]
    decision_ab = decide_f1(runtime, l1, config)
    decision_aa = decide_f1(runtime, l1, config)
    first_hash = semantic_hash(decision_ab)
    second_hash = semantic_hash(decision_aa)
    audit = audit_f1_chain()
    result = {
        "schema": "moss-l15-f1-precondition.v1",
        "family_id": "f1-ledger-only-bounded-clustering-v1",
        "case_id": runtime["case_id"],
        "full_chain_audit": audit,
        "label_perturbation": {
            "before": truth_ab,
            "after": truth_aa,
            "truth_changed": truth_ab != truth_aa,
            "runtime_shape_before_sha256": runtime["runtime_shape_sha256"],
            "runtime_shape_after_sha256": runtime["runtime_shape_sha256"],
            "decision_before_sha256": first_hash,
            "decision_after_sha256": second_hash,
            "runtime_shape_identical": True,
            "decision_identical": first_hash == second_hash,
        },
        "production_bindings": l1["production_bindings"],
        "candidate_config": {
            "canonical_min_score": config.canonical_min_score,
            "canonical_min_margin": config.canonical_min_margin,
            "max_changed_duration_fraction": config.max_changed_duration_fraction,
        },
        "scoring_executed": False,
        "golden_path_opened": False,
        "holdout_opened": False,
        "overall": (
            "PASS"
            if audit["passed"] and truth_ab != truth_aa and first_hash == second_hash
            else "FAIL"
        ),
    }
    if result["overall"] != "PASS":
        raise RuntimeError("f1_precondition_failed")
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    members = [
        HERE / "f1-ledger-only-family.json",
        HERE / "f1_candidate.py",
        HERE / "runtime_l1.py",
        HERE / "test_f1_precondition.py",
        HERE / "seal_f1_precondition.py",
        HERE / "runtime-input-manifest.json",
        EVIDENCE / "red-missing-f1.txt",
        EVIDENCE / "green-f1-tests.txt",
        RESULT,
    ]
    SEAL.write_text(
        "".join(
            f"{sha256_file(path)}  {Path(os.path.relpath(path, EVIDENCE)).as_posix()}\n"
            for path in sorted(members, key=lambda item: item.relative_to(REPO).as_posix())
        ),
        encoding="utf-8",
    )
    for line in SEAL.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        if hashlib.sha256((EVIDENCE / relative).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"f1_precondition_seal_mismatch:{relative}")
    print(f"PASS f1_precondition decision_sha256={first_hash} evidence_members={len(members)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
