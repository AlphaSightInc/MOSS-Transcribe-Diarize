#!/usr/bin/env python3
"""F1 scoring/config-freeze process. Candidate decisions are already sealed inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from f1_decisions import SPEC, SPEC_SHA256, config_grid
from runtime_l1 import load_runtime_case
from runtime_fixture import sha256_file


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SPLITS = HERE / "split-manifest.json"
DEFAULT_EVIDENCE = HERE / "evidence/f1"


def _write(path: Path, payload: object) -> None:
    if path.exists():
        raise RuntimeError(f"f1_score_output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _evaluation_case(case_id: str, split: str) -> dict[str, object]:
    payload = json.loads(SPLITS.read_text(encoding="utf-8"))
    matches = [case for case in payload["groups"][split] if case["case_id"] == case_id]
    if len(matches) != 1:
        raise RuntimeError(f"f1_evaluation_case:{case_id}:{split}")
    return matches[0]


def _score(case_id: str, split: str, labels: Sequence[str | None]) -> dict[str, object]:
    from moss_transcribe_diarize.live_speaker_accuracy import (  # local: scorer process only
        SpeakerActivityInterval,
        load_reference_speaker_activity_jsonl,
        score_live_speaker_accuracy,
    )

    evaluation = _evaluation_case(case_id, split)
    reference_path = REPO / evaluation["reference_path"]
    if sha256_file(reference_path) != evaluation["reference_sha256"]:
        raise RuntimeError(f"f1_evaluation_hash:{case_id}")
    runtime = load_runtime_case(case_id)
    if len(labels) != len(runtime["units"]):
        raise RuntimeError(f"f1_score_label_count:{case_id}")
    hypothesis = tuple(
        SpeakerActivityInterval(
            piece["start_sample"] / 16_000.0,
            piece["end_sample"] / 16_000.0,
            label,
        )
        for unit, label in zip(runtime["units"], labels, strict=True)
        if label is not None
        for piece in unit["pieces"]
    )
    reference = load_reference_speaker_activity_jsonl(reference_path)
    return score_live_speaker_accuracy(reference, hypothesis)


def _aggregate(cases: Sequence[dict[str, object]], arm: str) -> dict[str, float]:
    metrics = [case[arm] for case in cases]
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


def _score_config(decisions: dict[str, object], config_id: str) -> dict[str, object]:
    case_results = []
    split = str(decisions["split"])
    for case in decisions["cases"]:
        candidate = next(item for item in case["decisions"] if item["config_id"] == config_id)
        l1_metrics = _score(case["case_id"], split, case["l1"]["final_unit_labels"])
        candidate_metrics = _score(
            case["case_id"], split, candidate["decision"]["final_unit_labels"]
        )
        corrections = candidate["decision"]["corrections"]
        evidence_complete = all(
            "score_delta" in item and "changed_duration_fraction" in item for item in corrections
        )
        case_results.append(
            {
                "case_id": case["case_id"],
                "l1": l1_metrics,
                "candidate": candidate_metrics,
                "gain_pp": 100.0
                * (float(candidate_metrics["speaker_accuracy"]) - float(l1_metrics["speaker_accuracy"])),
                "regression_gate": (
                    float(candidate_metrics["speaker_accuracy"])
                    >= float(l1_metrics["speaker_accuracy"]) - 0.005
                ),
                "fp_gate": (
                    float(candidate_metrics["false_positive_speaker_seconds"])
                    <= float(l1_metrics["false_positive_speaker_seconds"]) + 1e-9
                ),
                "der_gate": (
                    float(candidate_metrics["diarization_error_rate"])
                    <= float(l1_metrics["diarization_error_rate"]) + 1e-9
                ),
                "two_sided_gate": (
                    not bool(l1_metrics["two_sided_mapping"])
                    or bool(candidate_metrics["two_sided_mapping"])
                ),
                "correction_evidence_gate": evidence_complete,
                "deterministic": candidate["deterministic"],
                "decision_semantic_sha256": candidate["run1_semantic_sha256"],
                "changed_duration_fraction": candidate["decision"]["changed_duration_fraction"],
                "corrections": corrections,
            }
        )
    l1_aggregate = _aggregate(case_results, "l1")
    candidate_aggregate = _aggregate(case_results, "candidate")
    non_gain = all(
        case["regression_gate"]
        and case["fp_gate"]
        and case["der_gate"]
        and case["two_sided_gate"]
        and case["correction_evidence_gate"]
        and case["deterministic"]
        for case in case_results
    )
    gain_pp = 100.0 * (
        candidate_aggregate["speaker_accuracy"] - l1_aggregate["speaker_accuracy"]
    )
    return {
        "config_id": config_id,
        "cases": case_results,
        "l1_aggregate": l1_aggregate,
        "candidate_aggregate": candidate_aggregate,
        "aggregate_speaker_accuracy": candidate_aggregate["speaker_accuracy"],
        "gain_pp": gain_pp,
        "gain_gate": gain_pp >= 1.0,
        "non_gain_gates_passed": non_gain,
        "overall": "PASS" if gain_pp >= 1.0 and non_gain else "FAIL",
    }


def select_config(candidates: Sequence[dict[str, object]]) -> dict[str, object]:
    feasible = [item for item in candidates if item["non_gain_gates_passed"]]
    pool = feasible or list(candidates)
    return min(
        pool,
        key=lambda item: (
            -float(item["aggregate_speaker_accuracy"]),
            float(item["config"]["max_changed_duration_fraction"]),
            -float(item["config"]["canonical_min_score"]),
            -float(item["config"]["canonical_min_margin"]),
            str(item["config_id"]),
        ),
    )


def dev_score(evidence: Path) -> None:
    decisions_path = evidence / "f1-dev-decisions.json"
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    grid = config_grid()
    records = []
    for index, config in enumerate(grid, 1):
        print(f"SCORE development {index}/27 {config['config_id']}", flush=True)
        record = _score_config(decisions, str(config["config_id"]))
        record["config"] = {key: value for key, value in config.items() if key != "config_id"}
        records.append(record)
    selected = select_config(records)
    payload = {
        "schema": "moss-l15-f1-dev-score.v1",
        "family_spec_sha256": SPEC_SHA256,
        "decisions_sha256": sha256_file(decisions_path),
        "configuration_count": len(records),
        "configurations": records,
        "selected_config_id": selected["config_id"],
        "selected_dev_overall": selected["overall"],
        "validation_scored": False,
        "overall": "PASS",
    }
    output = evidence / "f1-dev-score.json"
    _write(output, payload)
    _write(
        evidence / "f1-selected-config.json",
        {
            "schema": "moss-l15-f1-selected-config.v1",
            "family_id": "f1-ledger-only-bounded-clustering-v1",
            "family_spec_sha256": SPEC_SHA256,
            "dev_score_sha256": sha256_file(output),
            "config_id": selected["config_id"],
            "config": selected["config"],
            "selection_rule": "preregistered accuracy/non-gain/tie-break rule",
            "dev_gain_pp": selected["gain_pp"],
            "dev_non_gain_gates_passed": selected["non_gain_gates_passed"],
            "validation_opened": False,
            "frozen_for_validation": True,
        },
    )
    print(f"PASS dev-score selected={selected['config_id']} gain_pp={selected['gain_pp']:.6f}")


def validation_score(evidence: Path) -> None:
    decisions_path = evidence / "f1-validation-decisions.json"
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    selected = json.loads((evidence / "f1-selected-config.json").read_text(encoding="utf-8"))
    result = _score_config(decisions, selected["config_id"])
    result["config"] = selected["config"]
    payload = {
        "schema": "moss-l15-f1-validation-score.v1",
        "family_spec_sha256": SPEC_SHA256,
        "decisions_sha256": sha256_file(decisions_path),
        "selected_config_sha256": sha256_file(evidence / "f1-selected-config.json"),
        "result": result,
        "configuration_count": 1,
        "post_validation_tuning": False,
        "overall": result["overall"],
    }
    _write(evidence / "f1-validation-score.json", payload)
    print(f"PASS validation-score config={selected['config_id']} gain_pp={result['gain_pp']:.6f}")


def verdict(evidence: Path) -> None:
    dev = json.loads((evidence / "f1-dev-score.json").read_text(encoding="utf-8"))
    selected_id = dev["selected_config_id"]
    selected_dev = next(item for item in dev["configurations"] if item["config_id"] == selected_id)
    validation = json.loads((evidence / "f1-validation-score.json").read_text(encoding="utf-8"))[
        "result"
    ]
    timing = json.loads((evidence / "f1-timing.json").read_text(encoding="utf-8"))
    gates = {
        "development_gain": selected_dev["gain_gate"],
        "development_non_gain": selected_dev["non_gain_gates_passed"],
        "validation_gain": validation["gain_gate"],
        "validation_non_gain": validation["non_gain_gates_passed"],
        "compute_p95": timing["passed"],
    }
    payload = {
        "schema": "moss-l15-family-verdict.v1",
        "family_id": "f1-ledger-only-bounded-clustering-v1",
        "selected_config_id": selected_id,
        "development": selected_dev,
        "validation": validation,
        "timing": timing,
        "gates": gates,
        "optimization_passes_used": 1,
        "validation_configurations_run": 1,
        "holdout_opened": False,
        "freezeable": all(gates.values()),
        "overall": "PASS" if all(gates.values()) else "FAIL",
    }
    _write(evidence / "f1-verdict.json", payload)
    print(f"VERDICT {payload['overall']} freezeable={payload['freezeable']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("dev-score", "validation-score", "verdict"))
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    args = parser.parse_args()
    if sha256_file(SPEC) != SPEC_SHA256:
        raise RuntimeError("f1_spec_hash_drift")
    if args.mode == "dev-score":
        dev_score(args.evidence_dir)
    elif args.mode == "validation-score":
        validation_score(args.evidence_dir)
    else:
        verdict(args.evidence_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
