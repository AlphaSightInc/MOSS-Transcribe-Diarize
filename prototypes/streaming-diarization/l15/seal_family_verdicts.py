#!/usr/bin/env python3
"""Verify and seal the L1.5 family-verdict boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path

from runtime_fixture import sha256_file


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence/family-verdicts"
VERDICT = EVIDENCE / "family-verdicts.json"
SEAL = EVIDENCE / "FAMILY_VERDICTS_EVIDENCE.sha256"


def main() -> int:
    payload = json.loads(VERDICT.read_text())
    checks = {
        "three_families": len(payload["families"]) == 3,
        "none_freezeable": not any(family["freezeable"] for family in payload["families"]),
        "no_composition": not payload["composition_arm_run"],
        "no_freeze": not payload["candidate_freeze_proposed"],
        "holdout_sealed": not payload["holdout_opened"] and payload["holdout_status"] == "SEALED",
        "blocked_product": not payload["ready_for_product"] and payload["campaign_disposition"] == "BLOCKED_FOR_PRODUCT",
    }
    if not all(checks.values()):
        raise RuntimeError(f"family_verdicts_verification_failed:{checks}")
    verification = EVIDENCE / "family-verdicts-verification.json"
    verification.write_text(json.dumps({"checks": checks, "overall": "PASS"}, indent=2, sort_keys=True) + "\n")
    members = [
        VERDICT,
        verification,
        HERE / "write_family_verdicts.py",
        HERE / "seal_family_verdicts.py",
        HERE / "evidence/f1/F1_EVIDENCE.sha256",
        HERE / "evidence/f1/f1-verdict.json",
        HERE / "evidence/f2/F2_EXPLORATORY_EVIDENCE.sha256",
        HERE / "evidence/f2/f2-exploratory-verdict.json",
        HERE / "evidence/f3/F3_EVIDENCE.sha256",
        HERE / "evidence/f3/f3-verdict.json",
    ]
    SEAL.write_text(
        "".join(
            f"{sha256_file(path)}  {Path(os.path.relpath(path, EVIDENCE)).as_posix()}\n"
            for path in sorted(members, key=lambda item: item.relative_to(REPO).as_posix())
        )
    )
    print(f"PASS family_verdicts evidence_members={len(members)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
