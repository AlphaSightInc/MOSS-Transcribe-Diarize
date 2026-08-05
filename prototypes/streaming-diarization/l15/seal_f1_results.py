#!/usr/bin/env python3
"""Verify and seal the complete F1 family result."""

from __future__ import annotations

import json
import os
from pathlib import Path

from runtime_fixture import sha256_file


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence/f1"
VERIFY = EVIDENCE / "f1-verification.json"
SEAL = EVIDENCE / "F1_EVIDENCE.sha256"
FILES = (
    "f1-dev-decisions.json",
    "f1-dev-decisions.txt",
    "f1-dev-score.json",
    "f1-selected-config.json",
    "f1-validation-decisions.json",
    "f1-validation-decisions.txt",
    "f1-validation-score.json",
    "f1-timing.json",
    "f1-verdict.json",
    "commands.txt",
)


def main() -> int:
    payloads = {name: json.loads((EVIDENCE / name).read_text()) for name in FILES if name.endswith(".json")}
    dev_decisions = payloads["f1-dev-decisions.json"]
    dev_score = payloads["f1-dev-score.json"]
    selected = payloads["f1-selected-config.json"]
    validation_decisions = payloads["f1-validation-decisions.json"]
    validation_score = payloads["f1-validation-score.json"]
    timing = payloads["f1-timing.json"]
    verdict = payloads["f1-verdict.json"]
    checks = {
        "dev_case_count_8": dev_decisions["case_count"] == 8,
        "dev_configs_27": dev_decisions["configuration_count"] == 27,
        "dev_all_deterministic": all(
            decision["deterministic"]
            for case in dev_decisions["cases"]
            for decision in case["decisions"]
        ),
        "dev_decisions_unscored": not dev_decisions["scoring_executed"] and not dev_decisions["golden_path_opened"],
        "selected_pinned_to_dev": selected["dev_score_sha256"] == sha256_file(EVIDENCE / "f1-dev-score.json"),
        "validation_case_count_8": validation_decisions["case_count"] == 8,
        "validation_config_count_1": validation_decisions["configuration_count"] == 1,
        "validation_all_deterministic": all(
            decision["deterministic"]
            for case in validation_decisions["cases"]
            for decision in case["decisions"]
        ),
        "validation_decisions_unscored": not validation_decisions["scoring_executed"] and not validation_decisions["golden_path_opened"],
        "validation_no_tuning": validation_score["configuration_count"] == 1 and not validation_score["post_validation_tuning"],
        "timing_20": timing["sample_count"] == 20,
        "verdict_fail": verdict["overall"] == "FAIL" and verdict["freezeable"] is False,
        "dev_gain_exact": abs(verdict["development"]["gain_pp"] - 0.0342058101619247) < 1e-12,
        "validation_gain_exact": abs(verdict["validation"]["gain_pp"] - 0.5961729831751916) < 1e-12,
        "holdout_sealed": verdict["holdout_opened"] is False,
        "one_optimization_pass": verdict["optimization_passes_used"] == 1,
    }
    if not all(checks.values()):
        raise RuntimeError(f"f1_verification_failed:{checks}")
    verification = {
        "schema": "moss-l15-f1-verification.v1",
        "checks": checks,
        "selected_config_id": selected["config_id"],
        "dev_gain_pp": verdict["development"]["gain_pp"],
        "validation_gain_pp": verdict["validation"]["gain_pp"],
        "timing_p95_seconds": timing["p95_seconds"],
        "failed_gates": [name for name, passed in verdict["gates"].items() if not passed],
        "overall": "PASS",
    }
    VERIFY.write_text(json.dumps(verification, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    members = [
        *(EVIDENCE / name for name in FILES),
        VERIFY,
        HERE / "f1-ledger-only-family.json",
        HERE / "f1_candidate.py",
        HERE / "f1_decisions.py",
        HERE / "run_f1_family.py",
        HERE / "runtime_l1.py",
        HERE / "evidence/f1-adapter/F1_ADAPTER_EVIDENCE.sha256",
    ]
    SEAL.write_text(
        "".join(
            f"{sha256_file(path)}  {Path(os.path.relpath(path, EVIDENCE)).as_posix()}\n"
            for path in sorted(members, key=lambda item: item.relative_to(REPO).as_posix())
        ),
        encoding="utf-8",
    )
    print(f"PASS f1_results evidence_members={len(members)} verdict=FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
