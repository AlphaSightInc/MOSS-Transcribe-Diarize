#!/usr/bin/env python3
"""Compose the terminal Campaign-A verdict from sealed A0-A5 artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
EVIDENCE = HERE / "evidence"
CONTROL = Path(
    "/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def record(path: Path) -> dict[str, str]:
    return {
        "path": path.resolve().relative_to(REPO.resolve()).as_posix(),
        "sha256": sha256(path),
    }


def arm_results(summary: dict[str, object]) -> list[dict[str, object]]:
    return [
        {
            "case_id": case["case_id"],
            "changed_duration_fraction": case["changed_duration_fraction"],
            "metrics": case["metrics"],
            "raw_path": case["raw_path"],
            "raw_sha256": case["raw_sha256"],
            "split": case["split"],
        }
        for case in summary["cases"]
    ]


def main() -> int:
    destination = HERE / "L2_STAGE0_VERDICT.json"
    if destination.exists():
        raise RuntimeError("a6_verdict_already_exists")
    a0_path = REPO / "scripts/ralph-l2-afk/evidence/a0-dry-run.json"
    a1_path = EVIDENCE / "a12-renewed-a1-validation-final.json"
    a2_path = EVIDENCE / "a2-completion-verdict.json"
    a3_path = EVIDENCE / "a3-verdict/lifecycle-verdict-v3.json"
    a4_path = EVIDENCE / "a4-completion/a4-completion-verdict.json"
    a4_raw_path = EVIDENCE / "a4/optimized/a4-runtime-optimized.json"
    a5_dev_path = EVIDENCE / "a5-dev-v4/a5-dev-validation.json"
    a5_holdout_path = EVIDENCE / "a5-holdout-opening/a5-holdout-summary.json"
    a0 = load(a0_path)
    a1 = load(a1_path)
    a2 = load(a2_path)
    a3 = load(a3_path)
    a4 = load(a4_path)
    a4_raw = load(a4_raw_path)
    a5_dev = load(a5_dev_path)
    a5_holdout = load(a5_holdout_path)
    failed_holdout = [
        gate for gate in a5_holdout["gate_evaluation"]["gates"] if not gate["pass"]
    ]
    if a5_holdout["overall"] != "FAIL" or len(failed_holdout) != 2:
        raise RuntimeError("a6_unexpected_holdout_verdict")
    if {gate["gate"] for gate in failed_holdout} != {
        "tape_beats_l1_target_subset_pp",
        "tape_beats_ledger_target_subset_pp",
    }:
        raise RuntimeError("a6_unexpected_failed_gate_set")
    authority = CONTROL / "docs/handoffs/decision-authority-20260803.md"
    plan = REPO / "docs/plans/r1-stage0-minimum-seam-0803.md"
    seam = HERE / "SEAM_INVENTORY.md"
    manifests = {
        "a0": REPO / "scripts/ralph-l2-afk/evidence/A0_EVIDENCE.sha256",
        "a1_a2": EVIDENCE / "A12_EVIDENCE.sha256",
        "a2_completion": EVIDENCE / "A2_COMPLETION_EVIDENCE.sha256",
        "a3": EVIDENCE / "A3_EVIDENCE_V3.sha256",
        "a4_completion": EVIDENCE / "A4_COMPLETION_EVIDENCE.sha256",
        "a5_dev": EVIDENCE / "A5_DEV_EVIDENCE.sha256",
        "a5_holdout": EVIDENCE / "a5-holdout-opening/A5_HOLDOUT_EVIDENCE.sha256",
    }
    verdict = {
        "arm_results": {
            "development_validation": {
                "cases": arm_results(a5_dev),
                "gate_evaluation": a5_dev["gate_evaluation"],
                "raw": record(a5_dev_path),
            },
            "blind_holdout_single_opening": {
                "cases": arm_results(a5_holdout),
                "gate_evaluation": a5_holdout["gate_evaluation"],
                "l1_runs_per_case": 2,
                "opening_count": a5_holdout["opening_count"],
                "raw": record(a5_holdout_path),
            },
        },
        "blocked": {
            "campaign_a_ended": True,
            "failed_gates": failed_holdout,
            "reason": (
                "The frozen tape candidate missed both predeclared blind-holdout "
                "minimum-gain gates; no rerun, replacement, or tuning is permitted."
            ),
        },
        "campaign": "A",
        "campaign_b_authorized": False,
        "commands": {
            "a0_guardrail": "python scripts/ralph-l2-afk/launch.py --dry-run-acceptance",
            "a1_validation": "python prototypes/streaming-diarization/l2-stage0/validate_inputs.py",
            "a2_control": "python prototypes/streaming-diarization/l2-stage0/run_l1_control.py --scope development_validation",
            "a3_lifecycle": "python prototypes/streaming-diarization/l2-stage0/run_lifecycle_evidence.py",
            "a4_remote_measurement": "ssh gyauo@ga0-alienware-rtx4070ti.local 'wsl.exe -d Ubuntu -- bash -s' < a4 remote stdin script",
            "a5_development": "python prototypes/streaming-diarization/l2-stage0/run_candidates.py --candidate-family prototypes/streaming-diarization/l2-stage0/a5-dev-candidate-family-v4.json",
            "a5_single_holdout_opening": "PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/run_a5_holdout.py",
            "a6_compose": "python prototypes/streaming-diarization/l2-stage0/write_a6_verdict.py",
        },
        "decision_authority": {
            "path": str(authority),
            "sha256": sha256(authority),
            "supervisor_authorized_freeze_opening_through_a6": True,
        },
        "environment": {
            "a4_deployment_cpu": a4_raw["host"],
            "a4_measurement_frame": a4_raw["measurement_frame"],
            "local_machine": platform.machine(),
            "local_platform": platform.platform(),
            "python": sys.version,
            "worktree_head_before_a6": subprocess.check_output(
                ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
            ).strip(),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_hashes": {
            "candidate_config": record(HERE / "candidate-config.json"),
            "candidate_family_v4": record(HERE / "a5-dev-candidate-family-v4.json"),
            "candidate_implementation": record(HERE / "candidate_engine.py"),
            "candidate_runner": record(HERE / "run_candidates.py"),
            "corpus_manifest_post_holdout_rebuild": record(HERE / "corpus-manifest.json"),
            "holdout_manifest": record(HERE / "holdout-manifest.json"),
            "holdout_procedure": record(HERE / "a5-holdout-procedure.json"),
            "model_manifest": record(HERE / "model-manifest.json"),
            "plan": record(plan),
            "rebuild_spec": record(HERE / "cache-rebuild-spec.json"),
            "seam_inventory": record(seam),
            "stage_evidence_manifests": {
                name: record(path) for name, path in manifests.items()
            },
        },
        "ready_for_product_stage": False,
        "resource_results": {
            "a4_completion": a4,
            "raw": record(a4_raw_path),
        },
        "schema": "moss-l2-stage0-terminal-verdict.v1",
        "stage_results": {
            "a0": {"overall": a0["overall"], "raw": record(a0_path)},
            "a1": {"overall": a1["overall"], "raw": record(a1_path)},
            "a2": {"overall": a2["overall"], "raw": record(a2_path)},
            "a3": {
                "decision": a3["decision"],
                "invariant_count": a3["invariant_count"],
                "negative_control_count": a3["negative_control_count"],
                "overall": a3["overall"],
                "raw": record(a3_path),
            },
            "a4": {"overall": a4["overall"], "raw": record(a4_path)},
            "a5_development_validation": {
                "overall": a5_dev["overall"],
                "raw": record(a5_dev_path),
            },
            "a5_blind_holdout": {
                "overall": a5_holdout["overall"],
                "raw": record(a5_holdout_path),
            },
        },
        "status": "BLOCKED",
    }
    destination.write_text(
        json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "failed_gates": [gate["gate"] for gate in failed_holdout],
                "overall": "BLOCKED",
                "output": record(destination),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
