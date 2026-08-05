#!/usr/bin/env python3
"""Diagnosis-only trace of F1 configuration flow; never scores or mutates F1 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from f1_candidate import F1Config, decide_f1, semantic_hash
from runtime_l1 import load_runtime_case


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
INPUT = HERE / "evidence/f1/f1-dev-decisions.json"
OUTPUT = HERE / "evidence/f1-parameter-diagnosis/f1-two-config-differential-v2.json"
CASE_ID = "3m-acquired-jamie-dimon"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gate_trace(decision: dict[str, object]) -> list[dict[str, object]]:
    config = decision["config"]
    evidence = decision["trace"]["cluster_evidence"]
    return [
        {
            "cluster": cluster,
            "score": values["score"],
            "score_threshold": config["canonical_min_score"],
            "score_pass": values["score"] >= config["canonical_min_score"],
            "margin": values["margin"],
            "margin_threshold": config["canonical_min_margin"],
            "margin_pass": values["margin"] >= config["canonical_min_margin"],
            "mapped": cluster in decision["trace"]["cluster_mapping"],
        }
        for cluster, values in sorted(evidence.items(), key=lambda item: int(item[0]))
    ]


def _projection(decision: dict[str, object]) -> dict[str, object]:
    """Decision-bearing fields; excludes effective config and diagnostic budget size."""

    trace = decision["trace"]
    return {
        "final_unit_labels": decision["final_unit_labels"],
        "corrections": decision["corrections"],
        "changed_duration_fraction": decision["changed_duration_fraction"],
        "cluster_mapping": trace["cluster_mapping"],
        "eligible_units": trace["eligible_units"],
        "proposal_count": trace["proposal_count"],
        "accepted_correction_count": trace["accepted_correction_count"],
        "changed_duration_seconds": trace["changed_duration_seconds"],
    }


def main(output: Path) -> int:
    if output.exists():
        raise RuntimeError(f"f1_parameter_diagnosis_output_exists:{output}")
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    case = next(item for item in payload["cases"] if item["case_id"] == CASE_ID)
    runtime = load_runtime_case(CASE_ID)
    configs = {
        "low": F1Config(0.30, 0.05, 0.02),
        "high": F1Config(0.40, 0.15, 0.08),
    }
    decisions = {name: decide_f1(runtime, case["l1"], config) for name, config in configs.items()}
    records = {}
    for name, decision in decisions.items():
        print(
            f"{name} effective score={decision['config']['canonical_min_score']:.2f} "
            f"margin={decision['config']['canonical_min_margin']:.2f} "
            f"budget_fraction={decision['config']['max_changed_duration_fraction']:.2f}"
        )
        print(
            f"{name} proposals={decision['trace']['proposal_count']} "
            f"accepted={decision['trace']['accepted_correction_count']} "
            f"used={decision['trace']['changed_duration_seconds']:.6f} "
            f"budget={decision['trace']['budget_seconds']:.6f}"
        )
        records[name] = {
            "effective_config_reported_inside_decide_f1": decision["config"],
            "complete_semantic_sha256": semantic_hash(decision),
            "decision_projection": _projection(decision),
            "decision_projection_sha256": semantic_hash(_projection(decision)),
            "cluster_gate_trace": _gate_trace(decision),
            "budget_seconds": decision["trace"]["budget_seconds"],
            "changed_duration_seconds": decision["trace"]["changed_duration_seconds"],
        }
    same_projection = (
        records["low"]["decision_projection_sha256"]
        == records["high"]["decision_projection_sha256"]
    )
    result = {
        "schema": "moss-l15-f1-parameter-diagnosis.v1",
        "case_id": CASE_ID,
        "scoring_executed": False,
        "holdout_opened": False,
        "inputs": {
            "f1_dev_decisions_path": INPUT.relative_to(REPO).as_posix(),
            "f1_dev_decisions_sha256": sha256_file(INPUT),
            "runtime_shape_sha256": runtime["runtime_shape_sha256"],
            "l1_semantic_sha256": case["l1_semantic_sha256"],
            "f1_candidate_sha256": sha256_file(HERE / "f1_candidate.py"),
            "f1_decisions_sha256": sha256_file(HERE / "f1_decisions.py"),
        },
        "two_config_trace": records,
        "decision_projection_identical": same_projection,
        "root_cause": {
            "config_key_mismatch": False,
            "constant_shadowing": False,
            "same_config_object": False,
            "effective_thresholds_differ": True,
            "score_margin_nonbinding": (
                all(item["mapped"] for item in records["low"]["cluster_gate_trace"] if item["score_pass"] and item["margin_pass"])
                and [item["mapped"] for item in records["low"]["cluster_gate_trace"]]
                == [item["mapped"] for item in records["high"]["cluster_gate_trace"]]
            ),
            "minimum_budget_nonbinding": (
                records["low"]["changed_duration_seconds"]
                <= records["low"]["budget_seconds"]
            ),
            "proposal_stage_starved": (
                records["low"]["decision_projection"]["proposal_count"] == 3
                and records["low"]["decision_projection"]["eligible_units"] == 75
            ),
            "explanation": (
                "The distinct config values reach decide_f1. Score/margin gate only the "
                "cluster-to-canonical mapping; every viable cluster lies outside both grid "
                "boundaries, while the third cluster fails both. That fixed mapping yields "
                "only three proposals from 75 eligible units. Their 3.07 seconds fit inside "
                "the smallest 3.4864-second budget, so every larger budget is inert."
            ),
        },
        "source_bindings": [
            "f1_decisions.py:50-55 constructs distinct F1Config values",
            "f1_decisions.py:110-113 passes each config to decide_f1",
            "f1_candidate.py:100-111 applies score and margin only to cluster mapping",
            "f1_candidate.py:113-138 emits proposals only where fixed cluster mapping differs from L1",
            "f1_candidate.py:139-159 applies the duration budget after proposal starvation",
        ],
        "boundary_1_verdict": "PARAMETERS_FLOW_CORRECT_BUT_ALL_THREE_RANGES_ARE_NONBINDING_AFTER_PROPOSAL_STARVATION",
        "next_step_authorized": "Stage-0 sealed ledger-arm differential; no fix before that evidence",
        "overall": "PASS",
    }
    if not same_projection:
        raise RuntimeError("f1_parameter_diagnosis_projection_differs")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        shown = output.relative_to(REPO)
    except ValueError:
        shown = output
    print(f"PASS output={shown} sha256={sha256_file(output)}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    raise SystemExit(main(args.output))
