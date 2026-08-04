#!/usr/bin/env python3
"""Fail closed unless the terminal A6 package matches sealed A0-A5 facts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    verdict_path = HERE / "L2_STAGE0_VERDICT.json"
    output = HERE / "evidence/a6/a6-verification.json"
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    checks = {
        "a0_a4_pass": all(
            verdict["stage_results"][stage]["overall"] == "PASS"
            for stage in ("a0", "a1", "a2", "a3", "a4")
        ),
        "campaign_b_not_authorized": verdict["campaign_b_authorized"] is False,
        "dev_case_count": len(
            verdict["arm_results"]["development_validation"]["cases"]
        )
        == 6,
        "dev_pass": verdict["stage_results"]["a5_development_validation"]["overall"]
        == "PASS",
        "frozen_candidate_hashes": (
            verdict["input_hashes"]["candidate_config"]["sha256"]
            == "0f9fc2b0d23df377e3b04432e50dd8b5f19d53793682f14396270b3d0bf669b9"
            and verdict["input_hashes"]["candidate_family_v4"]["sha256"]
            == "280041b25865c0ce912ab3d05afdf8636561296723832deadeb6e328ea7b7a0f"
            and verdict["input_hashes"]["candidate_implementation"]["sha256"]
            == "fbed07c2a06efee9f1efab24000ae3e7c7f083761fa21b5ab544a7afce538467"
            and verdict["input_hashes"]["candidate_runner"]["sha256"]
            == "dfc481215e1541def902764b13e199783d7b62738d3e205197ccd52f122aa828"
        ),
        "holdout_case_count": len(
            verdict["arm_results"]["blind_holdout_single_opening"]["cases"]
        )
        == 3,
        "holdout_failed_once": (
            verdict["stage_results"]["a5_blind_holdout"]["overall"] == "FAIL"
            and verdict["arm_results"]["blind_holdout_single_opening"]["opening_count"]
            == 1
        ),
        "only_expected_gates_failed": {
            gate["gate"] for gate in verdict["blocked"]["failed_gates"]
        }
        == {
            "tape_beats_l1_target_subset_pp",
            "tape_beats_ledger_target_subset_pp",
        },
        "resource_gates_pass": all(
            gate["pass"]
            for gate in verdict["resource_results"]["a4_completion"][
                "revised_gate_table"
            ]
        ),
        "terminal_blocked": (
            verdict["status"] == "BLOCKED"
            and verdict["ready_for_product_stage"] is False
            and verdict["blocked"]["campaign_a_ended"] is True
        ),
    }
    for item in verdict["input_hashes"].values():
        if not isinstance(item, dict) or "path" not in item:
            continue
        path = REPO / item["path"]
        checks[f"input_hash:{item['path']}"] = path.is_file() and sha256(path) == item["sha256"]
    result = {
        "checks": checks,
        "overall": "PASS" if all(checks.values()) else "FAIL",
        "schema": "moss-l2-stage0-a6-verification.v1",
        "verdict_sha256": sha256(verdict_path),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise RuntimeError("a6_verification_already_exists")
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
