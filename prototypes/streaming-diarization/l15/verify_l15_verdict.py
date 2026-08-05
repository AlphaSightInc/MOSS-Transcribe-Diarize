#!/usr/bin/env python3
"""Fail closed unless the L1.5 terminal verdict matches sealed campaign facts."""

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
    verdict_path = HERE / "L15_VERDICT.json"
    output = HERE / "evidence/closing/l15-verdict-verification.json"
    if output.exists():
        raise RuntimeError("l15_verdict_verification_exists")
    verdict = json.loads(verdict_path.read_text())
    family = {item["family_id"]: item for item in verdict["families"]}
    checks = {
        "terminal_blocked": verdict["status"] == "BLOCKED" and verdict["campaign_disposition"] == "BLOCKED_FOR_PRODUCT" and not verdict["ready_for_product"],
        "family_count_3": len(family) == 3,
        "none_freezeable": not any(item["freezeable"] for item in family.values()),
        "f1_fail_exact": family["f1-ledger-only-bounded-clustering-v1"]["disposition"] == "FAIL_METHOD_CLASS_LIMITATION_D8_RUNTIME_FRAME" and abs(family["f1-ledger-only-bounded-clustering-v1"]["development_gain_pp"] - 0.0342058101619247) < 1e-12,
        "f2_exploratory_only": family["f2-soft-lane-provenance-prior-v1"]["scope"] == "exploratory-only" and not family["f2-soft-lane-provenance-prior-v1"]["identity_accuracy_claim"],
        "f3_fail_exact": abs(family["f3-live-pass-duration-adaptive-margin-v1"]["development_gain_pp"] - (-0.054219848022663)) < 1e-12 and family["f3-live-pass-duration-adaptive-margin-v1"]["validation_gain_pp"] == 0.0,
        "f2_dose_response": [round(item["own_lane_classification_rate_after"], 12) for item in verdict["findings_of_record"]["f2_lane_prior_direction"]["dose_response"]] == [round(value, 12) for value in (0.9158440522484793, 0.9407717618905174, 0.9781633263535745)],
        "stage0_frame_finding": verdict["findings_of_record"]["stage0_ledger_gains_frame_flattered"]["d8_safe_runtime_frame"]["gain_over_l1_pp"] == 0.0342058101619247,
        "method_inert": verdict["findings_of_record"]["posthoc_regrouping_inert_in_runtime_frame"]["all_stage0_f1_counts_and_labels_identical"],
        "holdout_never_opened": verdict["holdout"]["status"] == "SEALED_NEVER_OPENED" and verdict["holdout"]["opening_count"] == 0 and verdict["holdout"]["remains_virgin_for_next_campaign"],
        "holdout_cases_exact": verdict["holdout"]["case_ids"] == ["5m-acquired-coca-cola", "5m-lex-keyu-jin", "30m-acquired-jamie-dimon"],
        "holdout_inputs_absent": verdict["holdout"]["input_paths_absent_count"] == 9 and not verdict["holdout"]["input_paths_present"],
        "no_freeze_or_composition": not verdict["candidate_freeze_proposed"] and not verdict["composition_arm_run"],
    }
    for section in ("input_hashes",):
        for name, item in verdict[section].items():
            path = REPO / item["path"]
            checks[f"{section}:{name}"] = path.is_file() and sha256(path) == item["sha256"]
    for item in verdict["families"]:
        for name in ("verdict", "evidence_manifest"):
            path = REPO / item[name]["path"]
            checks[f"family:{item['family_id']}:{name}"] = path.is_file() and sha256(path) == item[name]["sha256"]
    result = {
        "schema": "moss-l15-terminal-verdict-verification.v1",
        "checks": checks,
        "verdict_sha256": sha256(verdict_path),
        "overall": "PASS" if all(checks.values()) else "FAIL",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
