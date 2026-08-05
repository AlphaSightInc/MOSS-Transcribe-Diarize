#!/usr/bin/env python3
"""Seal scorer-free F3 development decisions before opening development truth."""

from __future__ import annotations

import json
import os
from pathlib import Path

from runtime_fixture import sha256_file


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence/f3"
SEAL = EVIDENCE / "F3_DEV_DECISIONS_PRESCORE.sha256"


def main() -> int:
    decisions = json.loads((EVIDENCE / "f3-dev-decisions.json").read_text())
    checks = {
        "development": decisions["split"] == "development",
        "eight_cases": decisions["case_count"] == 8,
        "three_schedules": decisions["configuration_count"] == 3,
        "all_deterministic": all(
            item["deterministic"]
            for case in decisions["cases"]
            for item in case["decisions"]
        ),
        "unscored": not decisions["scoring_executed"],
        "golden_unopened": not decisions["golden_path_opened"],
        "holdout_sealed": not decisions["holdout_opened"],
    }
    if not all(checks.values()):
        raise RuntimeError(f"f3_dev_prescore_failed:{checks}")
    verification = EVIDENCE / "f3-dev-prescore-verification.json"
    verification.write_text(json.dumps({"checks": checks, "overall": "PASS"}, indent=2, sort_keys=True) + "\n")
    members = [
        HERE / "f3-adaptive-margin-family.json",
        HERE / "f3_candidate.py",
        HERE / "f3_decisions.py",
        HERE / "runtime_l1.py",
        HERE / "evidence/f3-precondition/F3_PRECONDITION_EVIDENCE.sha256",
        EVIDENCE / "f3-dev-decisions.json",
        EVIDENCE / "f3-dev-decisions.txt",
        verification,
    ]
    SEAL.write_text(
        "".join(
            f"{sha256_file(path)}  {Path(os.path.relpath(path, EVIDENCE)).as_posix()}\n"
            for path in sorted(members, key=lambda item: item.relative_to(REPO).as_posix())
        )
    )
    print(f"PASS f3_dev_prescore evidence_members={len(members)} decisions_sha256={sha256_file(EVIDENCE / 'f3-dev-decisions.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
