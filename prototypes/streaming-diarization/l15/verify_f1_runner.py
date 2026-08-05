#!/usr/bin/env python3
"""Seal F1 runner red/green and candidate-process isolation before scoring."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

from f1_decisions import config_grid
from runtime_fixture import sha256_file


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence/f1-runner"
AUDIT = EVIDENCE / "f1-runner-audit.json"
SEAL = EVIDENCE / "F1_RUNNER_EVIDENCE.sha256"
DECISION_CHAIN = (
    HERE / "f1_decisions.py",
    HERE / "f1_candidate.py",
    HERE / "runtime_l1.py",
)


def main() -> int:
    findings = []
    files = []
    for path in DECISION_CHAIN:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        ]
        keys = {
            node.slice.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        }
        if path.name in {"f1_decisions.py", "f1_candidate.py"}:
            if any("live_speaker_accuracy" in name for name in imports):
                findings.append(f"{path.name}:evaluator_import")
            if {"reference_path", "reference_sha256", "true_speaker"} & keys:
                findings.append(f"{path.name}:golden_key")
        if path.name == "f1_decisions.py" and any("run_f1_family" in name for name in imports):
            findings.append("f1_decisions.py:scorer_import")
        files.append(
            {
                "path": path.relative_to(REPO).as_posix(),
                "sha256": sha256_file(path),
                "imports": sorted(imports),
                "subscript_keys": sorted(keys),
            }
        )
    scoring_outputs = sorted((HERE / "evidence/f1").glob("*.json")) if (HERE / "evidence/f1").exists() else []
    if scoring_outputs:
        findings.append(f"scoring_outputs_preexisted:{[path.name for path in scoring_outputs]}")
    audit = {
        "schema": "moss-l15-f1-runner-audit.v1",
        "decision_process_chain": files,
        "decision_process_imports_scorer": False,
        "scorer_process_module": "run_f1_family.py",
        "process_order": [
            "dev-decisions",
            "dev-score-and-config-freeze",
            "validation-decisions-fresh-process",
            "validation-score",
            "timing",
            "verdict",
        ],
        "grid_configuration_count": len(config_grid()),
        "scoring_outputs_before_first_run": [path.name for path in scoring_outputs],
        "findings": findings,
        "overall": "PASS" if not findings and len(config_grid()) == 27 else "FAIL",
    }
    if audit["overall"] != "PASS":
        raise RuntimeError(f"f1_runner_audit_failed:{findings}")
    AUDIT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    members = [
        *DECISION_CHAIN,
        HERE / "run_f1_family.py",
        HERE / "test_f1_runner.py",
        HERE / "verify_f1_runner.py",
        HERE / "f1-ledger-only-family.json",
        HERE / "evidence/f1-precondition/F1_PRECONDITION_EVIDENCE.sha256",
        EVIDENCE / "red-missing-f1-runner.txt",
        EVIDENCE / "green-f1-runner-tests.txt",
        AUDIT,
    ]
    SEAL.write_text(
        "".join(
            f"{sha256_file(path)}  {Path(os.path.relpath(path, EVIDENCE)).as_posix()}\n"
            for path in sorted(members, key=lambda item: item.relative_to(REPO).as_posix())
        ),
        encoding="utf-8",
    )
    print(f"PASS f1_runner evidence_members={len(members)} grid=27 scoring_outputs=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
