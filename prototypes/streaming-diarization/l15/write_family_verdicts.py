#!/usr/bin/env python3
"""Write the L1.5 pre-holdout family-verdict boundary."""

from __future__ import annotations

import json
from pathlib import Path

from runtime_fixture import sha256_file


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "evidence/family-verdicts/family-verdicts.json"


def main() -> int:
    if OUTPUT.exists():
        raise RuntimeError("family_verdicts_output_exists")
    f1 = json.loads((HERE / "evidence/f1/f1-verdict.json").read_text())
    f2 = json.loads((HERE / "evidence/f2/f2-exploratory-verdict.json").read_text())
    f3 = json.loads((HERE / "evidence/f3/f3-verdict.json").read_text())
    families = [
        {
            "family_id": f1["family_id"],
            "scope": "acceptance-bearing",
            "disposition": "FAIL_METHOD_CLASS_LIMITATION_D8_RUNTIME_FRAME",
            "freezeable": f1["freezeable"],
            "development_gain_pp": f1["development"]["gain_pp"],
            "validation_gain_pp": f1["validation"]["gain_pp"],
            "verdict_path": "prototypes/streaming-diarization/l15/evidence/f1/f1-verdict.json",
            "verdict_sha256": sha256_file(HERE / "evidence/f1/f1-verdict.json"),
            "evidence_manifest_sha256": sha256_file(HERE / "evidence/f1/F1_EVIDENCE.sha256"),
        },
        {
            "family_id": f2["family_id"],
            "scope": "exploratory-only",
            "disposition": f2["disposition"],
            "freezeable": f2["freezeable"],
            "identity_accuracy_claim": False,
            "verdict_path": "prototypes/streaming-diarization/l15/evidence/f2/f2-exploratory-verdict.json",
            "verdict_sha256": sha256_file(HERE / "evidence/f2/f2-exploratory-verdict.json"),
            "evidence_manifest_sha256": sha256_file(HERE / "evidence/f2/F2_EXPLORATORY_EVIDENCE.sha256"),
        },
        {
            "family_id": f3["family_id"],
            "scope": "acceptance-bearing",
            "disposition": "FAIL",
            "freezeable": f3["freezeable"],
            "development_gain_pp": f3["development"]["gain_pp"],
            "validation_gain_pp": f3["validation"]["gain_pp"],
            "verdict_path": "prototypes/streaming-diarization/l15/evidence/f3/f3-verdict.json",
            "verdict_sha256": sha256_file(HERE / "evidence/f3/f3-verdict.json"),
            "evidence_manifest_sha256": sha256_file(HERE / "evidence/f3/F3_EVIDENCE.sha256"),
        },
    ]
    payload = {
        "schema": "moss-l15-family-verdicts.v1",
        "stage": "L1.b_PRE_HOLDOUT",
        "families": families,
        "composition_arm_run": False,
        "composition_arm_reason": "no acceptance-bearing constituent cleared its family gates",
        "candidate_freeze_proposed": False,
        "holdout_opened": False,
        "holdout_status": "SEALED",
        "ready_for_product": False,
        "campaign_disposition": "BLOCKED_FOR_PRODUCT",
        "strategic_findings": [
            "F1 ledger-only gains from Stage 0 were truth-timed-frame-flattered and collapse in the D8-safe runtime frame",
            "F2 shows a measurable acoustic lane-prior effect but lacks audited dual-lane identity evidence",
            "F3 live-pass adaptive margin does not clear gain gates and slightly worsens the 30-minute development case"
        ],
        "future_dual_lane_program": "DL1 inventory authorized separately; no effect on this sealed family verdict",
        "overall": "PASS_EVIDENCE_PROCESS_BLOCKED_PRODUCT",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"PASS family_verdicts disposition={payload['campaign_disposition']} sha256={sha256_file(OUTPUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
