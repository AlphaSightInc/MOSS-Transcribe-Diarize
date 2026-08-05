#!/usr/bin/env python3
"""Verify/seal the D8-safe runtime fixture boundary without opening golden files."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from runtime_fixture import (  # noqa: E402
    plan_runtime_asr,
    planner_bindings,
    runtime_shape,
    sha256_file,
    validate_runtime_cache,
)


MANIFEST = HERE / "runtime-input-manifest.json"
EVIDENCE = HERE / "evidence" / "runtime-fixture"
SEAL = EVIDENCE / "RUNTIME_FIXTURE_EVIDENCE.sha256"
AUDIT = EVIDENCE / "full-chain-audit.json"
CHAIN = (
    HERE / "collect_runtime_asr.py",
    HERE / "runtime_fixture.py",
    HERE / "build_runtime_fixtures.py",
)
FORBIDDEN_KEYS = {"reference", "reference_path", "reference_sha256", "true_speaker"}
FORBIDDEN_IMPORTS = {"validate_inputs", "live_speaker_accuracy"}


def source_audit() -> dict[str, object]:
    files = []
    overall_keys: set[str] = set()
    overall_imports: set[str] = set()
    for path in CHAIN:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        keys = {
            node.slice.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        }
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")])
        }
        overall_keys.update(keys)
        overall_imports.update(imports)
        files.append(
            {
                "path": path.relative_to(REPO).as_posix(),
                "sha256": sha256_file(path),
                "subscript_keys": sorted(keys),
                "imports": sorted(imports),
            }
        )
    forbidden_keys_found = sorted(FORBIDDEN_KEYS & overall_keys)
    forbidden_imports_found = sorted(
        item for item in overall_imports if any(name in item for name in FORBIDDEN_IMPORTS)
    )
    return {
        "files": files,
        "forbidden_subscript_keys": sorted(FORBIDDEN_KEYS),
        "forbidden_subscript_keys_found": forbidden_keys_found,
        "forbidden_import_names": sorted(FORBIDDEN_IMPORTS),
        "forbidden_import_names_found": forbidden_imports_found,
        "passed": not forbidden_keys_found and not forbidden_imports_found,
    }


def manifest_path_audit(payload: object) -> list[str]:
    findings: list[str] = []

    def walk(value: object, pointer: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in FORBIDDEN_KEYS:
                    findings.append(f"{pointer}/{key}:forbidden_key")
                walk(item, f"{pointer}/{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{pointer}/{index}")
        elif isinstance(value, str) and ("/reference" in value or "golden" in value.lower()):
            findings.append(f"{pointer}:forbidden_value:{value}")

    walk(payload, "")
    return findings


def verify() -> tuple[dict[str, object], list[Path]]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload["overall"] != "PASS" or payload["case_count"] != 16:
        raise RuntimeError("runtime_fixture_manifest_state")
    if payload["golden_paths_present"] or payload["holdout_cases_present"]:
        raise RuntimeError("runtime_fixture_forbidden_scope")
    if payload["production_planner"] != planner_bindings():
        raise RuntimeError("runtime_fixture_planner_binding_drift")
    path_findings = manifest_path_audit(payload)
    if path_findings:
        raise RuntimeError(f"runtime_fixture_manifest_path_leak:{path_findings}")
    sources = source_audit()
    if not sources["passed"]:
        raise RuntimeError(f"runtime_fixture_source_leak:{sources}")
    members = [
        *CHAIN,
        HERE / "test_runtime_fixture.py",
        HERE / "verify_runtime_fixtures.py",
        MANIFEST,
        EVIDENCE / "red-missing-runtime-fixture.txt",
        EVIDENCE / "green-runtime-fixture-tests.txt",
        EVIDENCE / "build-transcript.txt",
    ]
    cases = []
    for case in payload["cases"]:
        case_id = case["case_id"]
        if case["split"] not in {"development", "validation"}:
            raise RuntimeError(f"runtime_fixture_split:{case_id}")
        segments_path = REPO / case["asr_segments_path"]
        cache_path = REPO / case["runtime_cache_path"]
        if sha256_file(segments_path) != case["asr_segments_sha256"]:
            raise RuntimeError(f"runtime_fixture_asr_hash:{case_id}")
        if sha256_file(cache_path) != case["runtime_cache_sha256"]:
            raise RuntimeError(f"runtime_fixture_cache_hash:{case_id}")
        segments = json.loads(segments_path.read_text(encoding="utf-8"))["segments"]
        plan = plan_runtime_asr(segments, total_samples=int(case["total_samples"]))
        shape_hash = hashlib.sha256(
            json.dumps(runtime_shape(plan), separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if shape_hash != case["runtime_shape_sha256"]:
            raise RuntimeError(f"runtime_fixture_shape_hash:{case_id}")
        fidelity = validate_runtime_cache(cache_path, plan)
        if fidelity != case["self_replan"]:
            raise RuntimeError(f"runtime_fixture_replan_record:{case_id}")
        members.extend((segments_path, cache_path))
        cases.append(
            {
                "case_id": case_id,
                "split": case["split"],
                "runtime_shape_sha256": shape_hash,
                "runtime_cache_sha256": case["runtime_cache_sha256"],
                "self_replan": fidelity["self_replan"],
            }
        )
    audit = {
        "schema": "moss-l15-full-chain-input-audit.v1",
        "chain_order": [path.relative_to(REPO).as_posix() for path in CHAIN],
        "case_count": len(cases),
        "cases": cases,
        "manifest_path_findings": path_findings,
        "source_audit": sources,
        "candidate_receives_runtime_manifest_only": True,
        "evaluation_truth_loaded_after_decisions": "enforced later by each family runner",
        "label_perturbation": "synthetic runtime shape proof green; per-family decision proof required",
        "overall": "PASS",
    }
    members = sorted(set(members), key=lambda path: path.relative_to(REPO).as_posix())
    return audit, members


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seal", action="store_true")
    args = parser.parse_args()
    audit, members = verify()
    if args.seal:
        AUDIT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        members.append(AUDIT)
        members = sorted(set(members), key=lambda path: path.relative_to(REPO).as_posix())
        SEAL.write_text(
            "".join(
                f"{sha256_file(path)}  {Path(os.path.relpath(path, EVIDENCE)).as_posix()}\n"
                for path in members
            ),
            encoding="utf-8",
        )
    if not SEAL.is_file():
        raise RuntimeError("runtime_fixture_evidence_manifest_absent")
    for line in SEAL.read_text(encoding="utf-8").splitlines():
        expected_hash, relative = line.split("  ", 1)
        if sha256_file(EVIDENCE / relative) != expected_hash:
            raise RuntimeError(f"runtime_fixture_evidence_hash:{relative}")
    print(f"PASS runtime_fixture cases=16 evidence_members={len(SEAL.read_text().splitlines())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
