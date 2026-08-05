#!/usr/bin/env python3
"""Interpret the Stage-0 differential only after its decision and scoring seals verify."""

from __future__ import annotations

import json
from pathlib import Path

from runtime_fixture import sha256_file


HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence/f1-stage0-ledger-differential"
SCORED = EVIDENCE / "stage0-ledger-scored.json"
SCORED_SHA256 = "d5a7769017cf90a3a9cc39447d63c2b8af9e2162146688322d33a0d8281ff013"
SCORED_SEAL = EVIDENCE / "STAGE0_LEDGER_SCORED_EVIDENCE.sha256"
SCORED_SEAL_SHA256 = "83bbaa6a270418f5022d43507399a9a1c7574bec17b65ecc2e0a6410a21f7f66"
OUTPUT = EVIDENCE / "stage0-ledger-differential-verdict.json"


def main() -> int:
    if OUTPUT.exists():
        raise RuntimeError(f"stage0_ledger_verdict_exists:{OUTPUT}")
    if sha256_file(SCORED) != SCORED_SHA256:
        raise RuntimeError("stage0_ledger_scored_hash_drift")
    if sha256_file(SCORED_SEAL) != SCORED_SEAL_SHA256:
        raise RuntimeError("stage0_ledger_scored_seal_hash_drift")
    scored = json.loads(SCORED.read_text(encoding="utf-8"))
    aggregate = scored["aggregate"]
    required = (
        aggregate["all_proposal_counts_equal"]
        and aggregate["all_accepted_counts_equal"]
        and aggregate["all_final_labels_equal"]
        and abs(
            aggregate["stage0_gain_over_l1_pp"]
            - aggregate["f1_same_config_gain_over_l1_pp"]
        )
        < 1e-12
    )
    if not required:
        raise RuntimeError("stage0_ledger_differential_not_identical")
    verdict = {
        "schema": "moss-l15-stage0-ledger-differential-verdict.v1",
        "diagnosis_step": 2,
        "raw_scored_sha256": SCORED_SHA256,
        "raw_scored_seal_sha256": SCORED_SEAL_SHA256,
        "raw_sealed_before_interpretation": True,
        "stage0_owning_commit": "a16c6d811031cac826878200256af0b69224add8",
        "stage0_candidate_engine_sha256": "fbed07c2a06efee9f1efab24000ae3e7c7f083761fa21b5ab544a7afce538467",
        "stage0_family_config_sha256": "280041b25865c0ce912ab3d05afdf8636561296723832deadeb6e328ea7b7a0f",
        "frame": "L1.5 D8-safe production-endpoint-over-deployed-ASR runtime units",
        "per_case": [
            {
                "case_id": case["case_id"],
                "eligible_vector_unit_count": case["eligible_vector_unit_count"],
                "stage0_proposal_count": case["stage0_proposal_count"],
                "f1_proposal_count": case["f1_same_config_proposal_count"],
                "stage0_accepted_corrections": case["stage0_accepted_correction_count"],
                "f1_accepted_corrections": case["f1_same_config_accepted_correction_count"],
                "gain_over_l1_pp": case["stage0_gain_over_l1_pp"],
                "final_labels_equal": case["stage0_final_labels_equal_f1_same_config"],
            }
            for case in scored["cases"]
        ],
        "aggregate": {
            "stage0_proposals": aggregate["total_stage0_proposals"],
            "f1_proposals": aggregate["total_f1_same_config_proposals"],
            "stage0_accepted_corrections": aggregate[
                "total_stage0_accepted_corrections"
            ],
            "stage0_gain_over_l1_pp": aggregate["stage0_gain_over_l1_pp"],
            "f1_same_config_gain_over_l1_pp": aggregate[
                "f1_same_config_gain_over_l1_pp"
            ],
            "all_counts_and_labels_identical": True,
        },
        "directed_decision_tree_result": "DATA_OR_FRAME_SIDE; SEALED_STAGE0_ARM_ALSO_COLLAPSES_ON_L15_D8_INPUTS",
        "f1_implementation_defect_proven": False,
        "f1_prime_authorized": False,
        "next_action": "STOP_FOR_SUPERVISOR_JOINT_RETHINK",
        "gates_or_tolerances_changed": False,
        "target_subset_or_fp_rule_changed": False,
        "validation_opened": False,
        "holdout_opened": False,
        "overall": "STOP",
    }
    OUTPUT.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"STOP data_frame_side proposals={aggregate['total_stage0_proposals']} "
        f"gain_pp={aggregate['stage0_gain_over_l1_pp']:.9f} sha256={sha256_file(OUTPUT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
