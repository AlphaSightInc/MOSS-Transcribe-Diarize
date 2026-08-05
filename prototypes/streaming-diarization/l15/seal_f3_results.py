#!/usr/bin/env python3
"""Verify and seal the complete F3 family result."""

from __future__ import annotations

import json
import os
from pathlib import Path

from runtime_fixture import sha256_file


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence/f3"
SEAL = EVIDENCE / "F3_EVIDENCE.sha256"


def main() -> int:
    dev_decisions = json.loads((EVIDENCE / "f3-dev-decisions.json").read_text())
    dev = json.loads((EVIDENCE / "f3-dev-score.json").read_text())
    selected = json.loads((EVIDENCE / "f3-selected-config.json").read_text())
    validation_decisions = json.loads((EVIDENCE / "f3-validation-decisions.json").read_text())
    validation = json.loads((EVIDENCE / "f3-validation-score.json").read_text())
    timing = json.loads((EVIDENCE / "f3-timing.json").read_text())
    verdict = json.loads((EVIDENCE / "f3-verdict.json").read_text())
    selected_dev = next(item for item in dev["configurations"] if item["config_id"] == selected["config_id"])
    checks = {
        "dev_case_count_8": dev_decisions["case_count"] == 8,
        "dev_schedules_3": dev_decisions["configuration_count"] == 3,
        "dev_all_deterministic": all(item["deterministic"] for case in dev_decisions["cases"] for item in case["decisions"]),
        "dev_prescore_sealed": (EVIDENCE / "F3_DEV_DECISIONS_PRESCORE.sha256").is_file(),
        "selected_from_dev": selected["dev_score_sha256"] == sha256_file(EVIDENCE / "f3-dev-score.json"),
        "validation_case_count_8": validation_decisions["case_count"] == 8,
        "validation_schedule_count_1": validation_decisions["configuration_count"] == 1,
        "validation_all_deterministic": all(item["deterministic"] for case in validation_decisions["cases"] for item in case["decisions"]),
        "validation_prescore_sealed": (EVIDENCE / "F3_VALIDATION_DECISIONS_PRESCORE.sha256").is_file(),
        "validation_no_tuning": validation["configuration_count"] == 1 and not validation["post_validation_tuning"],
        "dev_gain_exact": abs(selected_dev["gain_pp"] - (-0.054219848022663)) < 1e-12,
        "validation_gain_exact": abs(validation["result"]["gain_pp"] - 0.0) < 1e-12,
        "timing_20_replays": timing["replay_runs"] == 20 and timing["sweep_call_count"] == 640,
        "timing_gate_pass": timing["passed"] and timing["p95_seconds"] <= timing["gate_seconds"],
        "verdict_fail": verdict["overall"] == "FAIL" and verdict["freezeable"] is False,
        "holdout_sealed": not verdict["holdout_opened"],
        "one_optimization_pass": verdict["optimization_passes_used"] == 1,
    }
    if not all(checks.values()):
        raise RuntimeError(f"f3_verification_failed:{checks}")
    verification = EVIDENCE / "f3-verification.json"
    verification.write_text(
        json.dumps(
            {
                "schema": "moss-l15-f3-verification.v1",
                "checks": checks,
                "selected_config_id": selected["config_id"],
                "development_gain_pp": selected_dev["gain_pp"],
                "validation_gain_pp": validation["result"]["gain_pp"],
                "timing_p95_seconds": timing["p95_seconds"],
                "failed_gates": [name for name, passed in verdict["gates"].items() if not passed],
                "overall": "PASS",
            },
            indent=2,
            sort_keys=True,
        ) + "\n"
    )
    members = [
        HERE / "f3-adaptive-margin-family.json",
        HERE / "f3_candidate.py",
        HERE / "f3_decisions.py",
        HERE / "f3_score.py",
        HERE / "seal_f3_precondition.py",
        HERE / "seal_f3_dev_decisions.py",
        HERE / "seal_f3_validation_decisions.py",
        HERE / "seal_f3_results.py",
        HERE / "test_f3_precondition.py",
        HERE / "evidence/f3-precondition/F3_PRECONDITION_EVIDENCE.sha256",
        EVIDENCE / "F3_DEV_DECISIONS_PRESCORE.sha256",
        EVIDENCE / "F3_VALIDATION_DECISIONS_PRESCORE.sha256",
        EVIDENCE / "commands.txt",
        EVIDENCE / "f3-dev-decisions.json",
        EVIDENCE / "f3-dev-decisions.txt",
        EVIDENCE / "f3-dev-prescore-verification.json",
        EVIDENCE / "f3-dev-score.json",
        EVIDENCE / "f3-selected-config.json",
        EVIDENCE / "f3-validation-decisions.json",
        EVIDENCE / "f3-validation-decisions.txt",
        EVIDENCE / "f3-validation-prescore-verification.json",
        EVIDENCE / "f3-validation-score.json",
        EVIDENCE / "f3-timing.json",
        EVIDENCE / "f3-verdict.json",
        verification,
    ]
    SEAL.write_text(
        "".join(
            f"{sha256_file(path)}  {Path(os.path.relpath(path, EVIDENCE)).as_posix()}\n"
            for path in sorted(members, key=lambda item: item.relative_to(REPO).as_posix())
        )
    )
    print(f"PASS f3_results evidence_members={len(members)} verdict=FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
