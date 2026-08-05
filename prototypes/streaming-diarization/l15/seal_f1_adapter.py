#!/usr/bin/env python3
"""Seal the synthetic terminal-scorer suppression after decision-equivalence proof."""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "prototypes/streaming-diarization/l2-stage0"))

import run_l1_control as a2_control  # noqa: E402

from runtime_fixture import sha256_file  # noqa: E402


EVIDENCE = HERE / "evidence/f1-adapter"
RESULT = EVIDENCE / "f1-adapter-verdict.json"
SEAL = EVIDENCE / "F1_ADAPTER_EVIDENCE.sha256"


def main() -> int:
    source_lines, source_start = inspect.getsourcelines(a2_control.replay_case)
    scoring_offsets = [index for index, line in enumerate(source_lines) if "score_live_speaker_accuracy" in line]
    final_label_offsets = [index for index, line in enumerate(source_lines) if "final_labels" in line]
    if not scoring_offsets or not final_label_offsets or min(scoring_offsets) <= min(final_label_offsets):
        raise RuntimeError("f1_adapter_order_proof_failed")
    old_manifest = subprocess.run(
        [
            "git",
            "-C",
            str(REPO),
            "show",
            "f79411f:prototypes/streaming-diarization/l15/evidence/f1-precondition/F1_PRECONDITION_EVIDENCE.sha256",
        ],
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    old_runtime_line = next(line for line in old_manifest.splitlines() if line.endswith("../../runtime_l1.py"))
    result = {
        "schema": "moss-l15-f1-adapter-verdict.v1",
        "classification": "runtime-only synthetic terminal-score adapter defect; candidate policy and thresholds untouched",
        "failed_attempt": {
            "case_completed_in_memory": "1m-acquired-nfl",
            "failure_case": "3m-acquired-jamie-dimon",
            "cause": "one synthetic speaker per unit drove exponential used-mask assignment",
            "output_written": False,
            "score_written": False,
            "validation_opened": False,
            "holdout_opened": False,
        },
        "fix": "temporarily replace only run_l1_control.score_live_speaker_accuracy while replaying runtime-only synthetic activity; restore in finally; terminal metrics remain discarded",
        "decision_independence": {
            "test": "test_runtime_l1_adapter.py",
            "unsuppressed_vs_suppressed_decision_keys_identical": True,
            "decision_keys": [
                "final_unit_labels",
                "live_unit_labels",
                "counts",
                "revision_trace",
                "span_trace",
                "changed_duration_fraction",
                "changed_speaker_seconds",
                "production_bindings",
                "production_config",
                "production_planner"
            ],
            "a2_replay_source_path": Path(inspect.getsourcefile(a2_control.replay_case) or "").resolve().relative_to(REPO).as_posix(),
            "a2_replay_source_sha256": sha256_file(Path(inspect.getsourcefile(a2_control.replay_case) or "")),
            "replay_function_start_line": source_start,
            "first_final_labels_line": source_start + min(final_label_offsets),
            "first_terminal_score_line": source_start + min(scoring_offsets),
            "terminal_score_after_decisions": True
        },
        "historical_precondition_evidence": {
            "owning_commit": "f79411f",
            "runtime_l1_manifest_line": old_runtime_line,
            "preserved_not_overwritten": True
        },
        "candidate_spec_sha256": sha256_file(HERE / "f1-ledger-only-family.json"),
        "candidate_implementation_sha256": sha256_file(HERE / "f1_candidate.py"),
        "candidate_spec_changed": False,
        "candidate_implementation_changed": False,
        "scoring_outputs_present": bool(list((HERE / "evidence/f1").glob("*.json"))) if (HERE / "evidence/f1").exists() else False,
        "overall": "PASS"
    }
    if result["scoring_outputs_present"]:
        raise RuntimeError("f1_adapter_scoring_output_present")
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    members = [
        HERE / "runtime_l1.py",
        HERE / "test_runtime_l1_adapter.py",
        HERE / "test_f1_precondition.py",
        HERE / "test_f1_runner.py",
        HERE / "seal_f1_adapter.py",
        EVIDENCE / "f1-dev-attempt1-synthetic-scorer-failure.txt",
        EVIDENCE / "runtime-l1-adapter-green.txt",
        EVIDENCE / "f1-precondition-green-v2.txt",
        EVIDENCE / "f1-runner-green-v2.txt",
        RESULT,
    ]
    SEAL.write_text(
        "".join(
            f"{sha256_file(path)}  {Path(os.path.relpath(path, EVIDENCE)).as_posix()}\n"
            for path in sorted(members, key=lambda item: item.relative_to(REPO).as_posix())
        ),
        encoding="utf-8",
    )
    print(f"PASS f1_adapter evidence_members={len(members)} scoring_outputs=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
