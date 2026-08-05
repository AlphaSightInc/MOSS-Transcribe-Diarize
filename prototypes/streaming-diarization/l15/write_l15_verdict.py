#!/usr/bin/env python3
"""Compose the terminal Campaign L1.5 verdict from sealed family evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
EVIDENCE = HERE / "evidence"
L2 = REPO / "prototypes/streaming-diarization/l2-stage0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def record(path: Path) -> dict[str, str]:
    return {
        "path": path.resolve().relative_to(REPO.resolve()).as_posix(),
        "sha256": sha256(path),
    }


def main() -> int:
    destination = HERE / "L15_VERDICT.json"
    if destination.exists():
        raise RuntimeError("l15_verdict_already_exists")
    family_path = EVIDENCE / "family-verdicts/family-verdicts.json"
    f1_path = EVIDENCE / "f1/f1-verdict.json"
    f2_path = EVIDENCE / "f2/f2-exploratory-verdict.json"
    f3_path = EVIDENCE / "f3/f3-verdict.json"
    diagnosis_path = EVIDENCE / "f1-parameter-diagnosis/f1-two-config-differential-v2.json"
    differential_path = EVIDENCE / "f1-stage0-ledger-differential/stage0-ledger-differential-verdict.json"
    differential_raw_path = EVIDENCE / "f1-stage0-ledger-differential/stage0-ledger-scored.json"
    stage0_dev_path = L2 / "evidence/a5-dev-v4/a5-dev-validation.json"
    stage0_holdout_path = L2 / "evidence/a5-holdout-opening/a5-holdout-summary.json"
    split_path = HERE / "split-manifest.json"
    procedure_path = HERE / "holdout-procedure.json"
    family = load(family_path)
    f1 = load(f1_path)
    f2 = load(f2_path)
    f3 = load(f3_path)
    diagnosis = load(diagnosis_path)
    differential = load(differential_path)
    stage0_dev = load(stage0_dev_path)
    stage0_holdout = load(stage0_holdout_path)
    split = load(split_path)
    procedure = load(procedure_path)
    if family["campaign_disposition"] != "BLOCKED_FOR_PRODUCT":
        raise RuntimeError("l15_family_boundary_not_blocked")
    if any(item["freezeable"] for item in family["families"]):
        raise RuntimeError("l15_unexpected_freezeable_family")
    if f1["overall"] != "FAIL" or f2["freezeable"] or f3["overall"] != "FAIL":
        raise RuntimeError("l15_family_disposition_drift")
    opening_marker = REPO / procedure["opening_marker_path"]
    candidate_freeze = REPO / procedure["candidate_freeze_path"]
    holdout_cases = split["groups"]["blind_holdout"]
    holdout_input_paths = [
        REPO / case[f"{kind}_path"]
        for case in holdout_cases
        for kind in ("audio", "reference", "vector_cache")
    ]
    present_holdout_inputs = [path.relative_to(REPO).as_posix() for path in holdout_input_paths if path.exists()]
    if opening_marker.exists() or candidate_freeze.exists() or present_holdout_inputs:
        raise RuntimeError(
            "l15_holdout_not_virgin:"
            + json.dumps(
                {
                    "opening_marker": opening_marker.exists(),
                    "candidate_freeze": candidate_freeze.exists(),
                    "present_inputs": present_holdout_inputs,
                },
                sort_keys=True,
            )
        )
    stage0_dev_scores = stage0_dev["gate_evaluation"]["target_subset_scores"]
    stage0_holdout_scores = stage0_holdout["gate_evaluation"]["target_subset_scores"]
    f2_effect = f2["effect_by_prior_strength"]
    verdict = {
        "schema": "moss-l15-terminal-verdict.v1",
        "campaign": "L1.5",
        "stage": "L1_BENCH_CAMPAIGN",
        "status": "BLOCKED",
        "campaign_disposition": "BLOCKED_FOR_PRODUCT",
        "ready_for_product": False,
        "candidate_freeze_proposed": False,
        "composition_arm_run": False,
        "blocked": {
            "reason": "No acceptance-bearing family cleared the predeclared development and validation gates.",
            "designed_process_behavior": True,
            "hypotheses_killed": 3,
            "interpretation": "Three cheap hypotheses were resolved with bounded bench compute; the surviving lever is acceptance-grade lane evidence.",
        },
        "families": [
            {
                "family_id": f1["family_id"],
                "scope": "acceptance-bearing",
                "disposition": "FAIL_METHOD_CLASS_LIMITATION_D8_RUNTIME_FRAME",
                "overall": f1["overall"],
                "freezeable": f1["freezeable"],
                "development_gain_pp": f1["development"]["gain_pp"],
                "validation_gain_pp": f1["validation"]["gain_pp"],
                "verdict": record(f1_path),
                "evidence_manifest": record(EVIDENCE / "f1/F1_EVIDENCE.sha256"),
            },
            {
                "family_id": f2["family_id"],
                "scope": "exploratory-only",
                "disposition": f2["disposition"],
                "overall": f2["overall"],
                "freezeable": f2["freezeable"],
                "identity_accuracy_claim": False,
                "verdict": record(f2_path),
                "evidence_manifest": record(EVIDENCE / "f2/F2_EXPLORATORY_EVIDENCE.sha256"),
            },
            {
                "family_id": f3["family_id"],
                "scope": "acceptance-bearing",
                "disposition": "FAIL",
                "overall": f3["overall"],
                "freezeable": f3["freezeable"],
                "development_gain_pp": f3["development"]["gain_pp"],
                "validation_gain_pp": f3["validation"]["gain_pp"],
                "validation_non_gain_gates_passed": f3["validation"]["non_gain_gates_passed"],
                "sweep_compute_p95_seconds": f3["timing"]["p95_seconds"],
                "sweep_compute_gate_seconds": f3["timing"]["gate_seconds"],
                "verdict": record(f3_path),
                "evidence_manifest": record(EVIDENCE / "f3/F3_EVIDENCE.sha256"),
            },
        ],
        "findings_of_record": {
            "stage0_ledger_gains_frame_flattered": {
                "finding": "Stage-0 ledger-control gains on truth-timed partitions do not survive the D8-safe production-endpoint-over-deployed-ASR runtime frame and no longer carry strategic weight as a cheap live-mode win.",
                "truth_timed_frame": {
                    "development_l1_accuracy": stage0_dev_scores["l1_control"],
                    "development_ledger_accuracy": stage0_dev_scores["ledger_only_control"],
                    "development_gain_pp": 100.0 * (stage0_dev_scores["ledger_only_control"] - stage0_dev_scores["l1_control"]),
                    "development_raw": record(stage0_dev_path),
                    "development_evidence_manifest": record(L2 / "evidence/A5_DEV_EVIDENCE.sha256"),
                    "blind_l1_accuracy": stage0_holdout_scores["l1_control"],
                    "blind_ledger_accuracy": stage0_holdout_scores["ledger_only_control"],
                    "blind_gain_pp": 100.0 * (stage0_holdout_scores["ledger_only_control"] - stage0_holdout_scores["l1_control"]),
                    "blind_raw": record(stage0_holdout_path),
                    "blind_evidence_manifest": record(L2 / "evidence/a5-holdout-opening/A5_HOLDOUT_EVIDENCE.sha256"),
                },
                "d8_safe_runtime_frame": {
                    "gain_over_l1_pp": differential["aggregate"]["stage0_gain_over_l1_pp"],
                    "proposal_count": differential["aggregate"]["stage0_proposals"],
                    "accepted_correction_count": differential["aggregate"]["stage0_accepted_corrections"],
                    "raw": record(differential_raw_path),
                    "verdict": record(differential_path),
                    "evidence_manifest": record(EVIDENCE / "f1-stage0-ledger-differential/STAGE0_LEDGER_DIFFERENTIAL_EVIDENCE.sha256"),
                },
            },
            "posthoc_regrouping_inert_in_runtime_frame": {
                "finding": "The post-hoc regrouping method class is proposal-starved under honest runtime units; the exact sealed Stage-0 arm and F1 produce identical proposal counts, accepted corrections, and labels.",
                "parameter_grid_distinct_outcome_count": 1,
                "diagnostic_case": diagnosis["case_id"],
                "diagnostic_proposals_from_eligible_units": [
                    diagnosis["two_config_trace"]["low"]["decision_projection"]["proposal_count"],
                    diagnosis["two_config_trace"]["low"]["decision_projection"]["eligible_units"],
                ],
                "all_stage0_f1_counts_and_labels_identical": differential["aggregate"]["all_counts_and_labels_identical"],
                "diagnosis": record(diagnosis_path),
                "diagnosis_evidence_manifest": record(EVIDENCE / "f1-parameter-diagnosis/F1_PARAMETER_DIAGNOSIS_EVIDENCE.sha256"),
                "differential": record(differential_path),
            },
            "f2_lane_prior_direction": {
                "finding": "A stronger soft lane prior monotonically increased the exploratory own-lane acoustic classification rate; this is directional evidence only, not identity acceptance evidence.",
                "baseline_own_lane_rate": f2_effect[0]["own_lane_classification_rate_before"],
                "dose_response": f2_effect,
                "raw": record(EVIDENCE / "f2/f2-exploratory-effects.json"),
                "evidence_manifest": record(EVIDENCE / "f2/F2_EXPLORATORY_EVIDENCE.sha256"),
                "acceptance_grade_evidence_requirements": f2["acceptance_grade_evidence_requirements"],
            },
        },
        "strategic_conclusion": {
            "primary_surviving_lever": "acceptance-grade dual-lane evidence and a later separately preregistered F2-A campaign",
            "no_product_change_authorized": True,
            "dl1_inventory_authorized_after_merge": True,
        },
        "holdout": {
            "status": "SEALED_NEVER_OPENED",
            "opening_count": 0,
            "opened": False,
            "candidate_freeze_created": False,
            "opening_marker_created": False,
            "reason": "No candidate reached the preregistered freeze gate; refusing the opening is the designed behavior.",
            "remains_virgin_for_next_campaign": True,
            "asset_value": "The three cases retain blind evidentiary value for the next campaign.",
            "case_ids": [case["case_id"] for case in holdout_cases],
            "case_durations_seconds": {case["case_id"]: case["duration_seconds"] for case in holdout_cases},
            "input_paths_absent_count": len(holdout_input_paths),
            "input_paths_present": present_holdout_inputs,
            "split_manifest": record(split_path),
            "procedure": record(procedure_path),
        },
        "input_hashes": {
            "plan": record(REPO / "docs/plans/l15-live-uplift-0804.md"),
            "runtime_input_manifest": record(HERE / "runtime-input-manifest.json"),
            "family_boundary": record(family_path),
            "family_boundary_evidence": record(EVIDENCE / "family-verdicts/FAMILY_VERDICTS_EVIDENCE.sha256"),
            "f1_spec": record(HERE / "f1-ledger-only-family.json"),
            "f2_spec": record(HERE / "f2-lane-prior-family.json"),
            "f3_spec": record(HERE / "f3-adaptive-margin-family.json"),
        },
        "commands": {
            "l0_guardrail": "scripts/ralph-l15-afk/launch.sh --dry-run --evidence-dir scripts/ralph-l15-afk/evidence",
            "l1a_baseline": "PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l15/run_l1_baseline.py",
            "f1": "see prototypes/streaming-diarization/l15/evidence/f1/commands.txt",
            "f2": "see prototypes/streaming-diarization/l15/evidence/f2/commands.txt",
            "f3": "see prototypes/streaming-diarization/l15/evidence/f3/commands.txt",
            "terminal_verdict": "PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l15/write_l15_verdict.py",
            "full_swift_gate": "swift test --package-path macos/MOSSCapture",
            "full_python_gate": "PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python -m pytest tests -q -p no:cacheprovider",
            "diff_gate": "git diff --check",
        },
        "environment": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "worktree_head_before_package": subprocess.check_output(
                ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
            ).strip(),
            "python": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
    }
    destination.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": record(destination),
                "status": verdict["status"],
                "holdout_opening_count": verdict["holdout"]["opening_count"],
                "family_count": len(verdict["families"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
