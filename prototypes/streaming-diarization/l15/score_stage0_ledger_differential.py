#!/usr/bin/env python3
"""Score already-sealed Stage-0 ledger decisions; this is the only golden-reading process."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from runtime_fixture import sha256_file


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
EVIDENCE = HERE / "evidence/f1-stage0-ledger-differential"
DECISIONS = EVIDENCE / "stage0-ledger-decisions.json"
DECISIONS_SHA256 = "e2409e03b05884c36eeefba4dfc0964ed44b4fbbff931cf6311e096ad71b32aa"
DECISION_SEAL = EVIDENCE / "STAGE0_LEDGER_DECISIONS_EVIDENCE.sha256"
DECISION_SEAL_SHA256 = "0dc303959c01673d26eed707c3a3c2007b3d115c1558cdacdbd3a8957dd55d70"
F1_DEV_SCORE = HERE / "evidence/f1/f1-dev-score.json"
F1_DEV_SCORE_SHA256 = "ec73acf53746882c067387cd63d4662d5d0ffb57e793e8bf08355d62b55e006e"
DEFAULT_OUTPUT = EVIDENCE / "stage0-ledger-scored.json"


def verify_decision_seal() -> list[str]:
    if sha256_file(DECISION_SEAL) != DECISION_SEAL_SHA256:
        raise RuntimeError("stage0_ledger_decision_seal_hash_drift")
    members = []
    for line in DECISION_SEAL.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = (EVIDENCE / relative).resolve()
        if sha256_file(path) != expected:
            raise RuntimeError(f"stage0_ledger_decision_member_drift:{relative}")
        members.append(relative)
    if sha256_file(DECISIONS) != DECISIONS_SHA256:
        raise RuntimeError("stage0_ledger_decisions_hash_drift")
    return members


def _aggregate(metrics: Sequence[dict[str, object]]) -> dict[str, float]:
    reference = sum(float(item["reference_seconds"]) for item in metrics)
    matched = sum(float(item["matched_speaker_seconds"]) for item in metrics)
    errors = sum(
        float(item["confused_speaker_seconds"])
        + float(item["missed_speaker_seconds"])
        + float(item["false_positive_speaker_seconds"])
        for item in metrics
    )
    return {
        "reference_seconds": reference,
        "matched_speaker_seconds": matched,
        "speaker_accuracy": matched / reference if reference else 0.0,
        "diarization_error_rate": errors / reference if reference else 0.0,
        "false_positive_speaker_seconds": sum(
            float(item["false_positive_speaker_seconds"]) for item in metrics
        ),
    }


def main(output: Path) -> int:
    if output.exists():
        raise RuntimeError(f"stage0_ledger_score_output_exists:{output}")
    sealed_members = verify_decision_seal()
    if sha256_file(F1_DEV_SCORE) != F1_DEV_SCORE_SHA256:
        raise RuntimeError("stage0_ledger_f1_dev_score_hash_drift")
    decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))
    f1_dev = json.loads(F1_DEV_SCORE.read_text(encoding="utf-8"))
    f1_config = next(
        item for item in f1_dev["configurations"] if item["config_id"] == "f1-s035-m010-b005"
    )

    # Import only after every candidate-decision byte has been independently seal-verified.
    from run_f1_family import _score  # local: scorer process only

    cases = []
    l1_metrics_all = []
    stage0_metrics_all = []
    for position, case in enumerate(decisions["cases"], 1):
        case_id = str(case["case_id"])
        l1_labels = next(
            item for item in json.loads(
                (HERE / "evidence/f1/f1-dev-decisions.json").read_text(encoding="utf-8")
            )["cases"]
            if item["case_id"] == case_id
        )["l1"]["final_unit_labels"]
        l1_metrics = _score(case_id, "development", l1_labels)
        stage0_metrics = _score(case_id, "development", case["stage0_final_unit_labels"])
        f1_case = next(item for item in f1_config["cases"] if item["case_id"] == case_id)
        gain = 100.0 * (
            float(stage0_metrics["speaker_accuracy"]) - float(l1_metrics["speaker_accuracy"])
        )
        case_result = {
            "case_id": case_id,
            "eligible_vector_unit_count": case["eligible_vector_unit_count"],
            "stage0_proposal_count": case["stage0_proposal"]["trace"][
                "candidate_proposal_count"
            ],
            "stage0_accepted_correction_count": case["stage0_proposal"]["trace"][
                "accepted_correction_count"
            ],
            "f1_same_config_proposal_count": case["f1_same_config"]["proposal_count"],
            "f1_same_config_accepted_correction_count": case["f1_same_config"][
                "accepted_correction_count"
            ],
            "stage0_final_labels_equal_f1_same_config": (
                case["stage0_final_labels_semantic_sha256"]
                == case["f1_same_config"]["final_labels_semantic_sha256"]
            ),
            "l1_metrics": l1_metrics,
            "stage0_ledger_metrics": stage0_metrics,
            "stage0_gain_over_l1_pp": gain,
            "f1_same_config_gain_over_l1_pp": f1_case["gain_pp"],
        }
        cases.append(case_result)
        l1_metrics_all.append(l1_metrics)
        stage0_metrics_all.append(stage0_metrics)
        print(
            f"SCORE {position}/8 {case_id} stage0_proposals={case_result['stage0_proposal_count']} "
            f"f1_proposals={case_result['f1_same_config_proposal_count']} "
            f"stage0_gain_pp={gain:.9f}"
        )
    l1_aggregate = _aggregate(l1_metrics_all)
    stage0_aggregate = _aggregate(stage0_metrics_all)
    stage0_gain = 100.0 * (
        stage0_aggregate["speaker_accuracy"] - l1_aggregate["speaker_accuracy"]
    )
    result = {
        "schema": "moss-l15-stage0-ledger-differential-scored.v1",
        "diagnosis_step": 2,
        "decision_seal_verified_before_scorer_import": True,
        "decision_seal_sha256": DECISION_SEAL_SHA256,
        "decision_sealed_member_count": len(sealed_members),
        "decisions_sha256": DECISIONS_SHA256,
        "f1_dev_score_sha256": F1_DEV_SCORE_SHA256,
        "scorer_process": "score_stage0_ledger_differential.py",
        "candidate_process_imported_scorer": False,
        "development_truth_opened_after_decision_seal": True,
        "validation_opened": False,
        "holdout_opened": False,
        "case_count": len(cases),
        "cases": cases,
        "aggregate": {
            "l1": l1_aggregate,
            "stage0_ledger": stage0_aggregate,
            "stage0_gain_over_l1_pp": stage0_gain,
            "f1_same_config_gain_over_l1_pp": f1_config["gain_pp"],
            "total_stage0_proposals": sum(item["stage0_proposal_count"] for item in cases),
            "total_stage0_accepted_corrections": sum(
                item["stage0_accepted_correction_count"] for item in cases
            ),
            "total_f1_same_config_proposals": sum(
                item["f1_same_config_proposal_count"] for item in cases
            ),
            "all_proposal_counts_equal": all(
                item["stage0_proposal_count"] == item["f1_same_config_proposal_count"]
                for item in cases
            ),
            "all_accepted_counts_equal": all(
                item["stage0_accepted_correction_count"]
                == item["f1_same_config_accepted_correction_count"]
                for item in cases
            ),
            "all_final_labels_equal": all(
                item["stage0_final_labels_equal_f1_same_config"] for item in cases
            ),
        },
        "overall": "PASS",
    }
    if len(cases) != 8 or not all(case["stage0_final_labels_equal_f1_same_config"] for case in cases):
        raise RuntimeError("stage0_ledger_scored_comparison_incomplete")
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"PASS scored gain_pp={stage0_gain:.9f} sha256={sha256_file(output)}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    raise SystemExit(main(args.output))
