#!/usr/bin/env python3
"""F3 scorer/config-freeze process over already sealed candidate decisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from f3_decisions import SPEC, SPEC_SHA256, schedules
from run_f1_family import _aggregate, _score
from runtime_fixture import sha256_file


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
DEFAULT_EVIDENCE = HERE / "evidence/f3"


def _write(path: Path, payload: object) -> None:
    if path.exists():
        raise RuntimeError(f"f3_score_output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _score_config(decisions: dict[str, Any], config_id: str) -> dict[str, Any]:
    split = str(decisions["split"])
    cases = []
    for case in decisions["cases"]:
        candidate = next(item for item in case["decisions"] if item["config_id"] == config_id)
        l1_metrics = _score(case["case_id"], split, case["l1"]["final_unit_labels"])
        candidate_metrics = _score(case["case_id"], split, candidate["decision"]["final_unit_labels"])
        changes = candidate["decision"]["corrections"]
        evidence_complete = all(
            item.get("score_delta") is not None
            and item.get("changed_duration_fraction") is not None
            for item in changes
        )
        cases.append(
            {
                "case_id": case["case_id"],
                "l1": l1_metrics,
                "candidate": candidate_metrics,
                "gain_pp": 100.0 * (candidate_metrics["speaker_accuracy"] - l1_metrics["speaker_accuracy"]),
                "regression_gate": candidate_metrics["speaker_accuracy"] >= l1_metrics["speaker_accuracy"] - 0.005,
                "fp_gate": candidate_metrics["false_positive_speaker_seconds"] <= l1_metrics["false_positive_speaker_seconds"] + 1e-9,
                "der_gate": candidate_metrics["diarization_error_rate"] <= l1_metrics["diarization_error_rate"] + 1e-9,
                "two_sided_gate": not l1_metrics["two_sided_mapping"] or candidate_metrics["two_sided_mapping"],
                "changed_assignment_evidence_gate": evidence_complete,
                "deterministic": candidate["deterministic"],
                "decision_semantic_sha256": candidate["run1_semantic_sha256"],
                "changed_duration_fraction": candidate["decision"]["changed_duration_fraction"],
                "corrections": changes,
            }
        )
    l1 = _aggregate(cases, "l1")
    candidate = _aggregate(cases, "candidate")
    gain_pp = 100.0 * (candidate["speaker_accuracy"] - l1["speaker_accuracy"])
    non_gain = all(
        case["regression_gate"]
        and case["fp_gate"]
        and case["der_gate"]
        and case["two_sided_gate"]
        and case["changed_assignment_evidence_gate"]
        and case["deterministic"]
        for case in cases
    )
    return {
        "config_id": config_id,
        "cases": cases,
        "l1_aggregate": l1,
        "candidate_aggregate": candidate,
        "aggregate_speaker_accuracy": candidate["speaker_accuracy"],
        "gain_pp": gain_pp,
        "gain_gate": gain_pp >= 1.0,
        "non_gain_gates_passed": non_gain,
        "overall": "PASS" if gain_pp >= 1.0 and non_gain else "FAIL",
    }


def _schedule_payload(config_id: str) -> dict[str, object]:
    schedule = next(item for item in schedules() if item.config_id == config_id)
    return {
        "config_id": config_id,
        "segments": [
            {"end_seconds_exclusive": boundary, "margin": margin}
            for boundary, margin in schedule.segments
        ],
    }


def _select(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    feasible = [record for record in records if record["non_gain_gates_passed"]]
    pool = feasible or list(records)
    return min(pool, key=lambda record: (-record["aggregate_speaker_accuracy"], record["config_id"]))


def dev_score(evidence: Path) -> None:
    decisions_path = evidence / "f3-dev-decisions.json"
    decisions = json.loads(decisions_path.read_text())
    prescore = evidence / "F3_DEV_DECISIONS_PRESCORE.sha256"
    if not prescore.is_file():
        raise RuntimeError("f3_dev_prescore_seal_missing")
    records = [_score_config(decisions, schedule.config_id) for schedule in schedules()]
    for record in records:
        record["config"] = _schedule_payload(record["config_id"])
    selected = _select(records)
    payload = {
        "schema": "moss-l15-f3-dev-score.v1",
        "family_spec_sha256": SPEC_SHA256,
        "prescore_seal_sha256": sha256_file(prescore),
        "decisions_sha256": sha256_file(decisions_path),
        "configuration_count": len(records),
        "configurations": records,
        "selected_config_id": selected["config_id"],
        "selected_dev_overall": selected["overall"],
        "validation_scored": False,
        "overall": "PASS",
    }
    output = evidence / "f3-dev-score.json"
    _write(output, payload)
    _write(
        evidence / "f3-selected-config.json",
        {
            "schema": "moss-l15-f3-selected-config.v1",
            "family_id": "f3-live-pass-duration-adaptive-margin-v1",
            "family_spec_sha256": SPEC_SHA256,
            "dev_score_sha256": sha256_file(output),
            "config_id": selected["config_id"],
            "config": selected["config"],
            "selection_rule": "preregistered accuracy/non-gain/lexicographic rule",
            "dev_gain_pp": selected["gain_pp"],
            "dev_non_gain_gates_passed": selected["non_gain_gates_passed"],
            "validation_opened": False,
            "frozen_for_validation": True,
        },
    )
    print(f"PASS dev-score selected={selected['config_id']} gain_pp={selected['gain_pp']:.6f}")


def validation_score(evidence: Path) -> None:
    decisions_path = evidence / "f3-validation-decisions.json"
    decisions = json.loads(decisions_path.read_text())
    selected = json.loads((evidence / "f3-selected-config.json").read_text())
    result = _score_config(decisions, selected["config_id"])
    result["config"] = selected["config"]
    payload = {
        "schema": "moss-l15-f3-validation-score.v1",
        "family_spec_sha256": SPEC_SHA256,
        "decisions_sha256": sha256_file(decisions_path),
        "selected_config_sha256": sha256_file(evidence / "f3-selected-config.json"),
        "result": result,
        "configuration_count": 1,
        "post_validation_tuning": False,
        "overall": result["overall"],
    }
    _write(evidence / "f3-validation-score.json", payload)
    print(f"PASS validation-score config={selected['config_id']} gain_pp={result['gain_pp']:.6f}")


def verdict(evidence: Path) -> None:
    dev = json.loads((evidence / "f3-dev-score.json").read_text())
    selected_id = dev["selected_config_id"]
    selected_dev = next(item for item in dev["configurations"] if item["config_id"] == selected_id)
    validation = json.loads((evidence / "f3-validation-score.json").read_text())["result"]
    timing = json.loads((evidence / "f3-timing.json").read_text())
    gates = {
        "development_gain": selected_dev["gain_gate"],
        "development_non_gain": selected_dev["non_gain_gates_passed"],
        "validation_gain": validation["gain_gate"],
        "validation_non_gain": validation["non_gain_gates_passed"],
        "compute_p95": timing["passed"],
    }
    payload = {
        "schema": "moss-l15-family-verdict.v1",
        "family_id": "f3-live-pass-duration-adaptive-margin-v1",
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
    _write(evidence / "f3-verdict.json", payload)
    print(f"VERDICT {payload['overall']} freezeable={payload['freezeable']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("dev-score", "validation-score", "verdict"))
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    args = parser.parse_args()
    if sha256_file(SPEC) != SPEC_SHA256:
        raise RuntimeError("f3_spec_hash_drift")
    if args.mode == "dev-score":
        dev_score(args.evidence_dir)
    elif args.mode == "validation-score":
        validation_score(args.evidence_dir)
    else:
        verdict(args.evidence_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
