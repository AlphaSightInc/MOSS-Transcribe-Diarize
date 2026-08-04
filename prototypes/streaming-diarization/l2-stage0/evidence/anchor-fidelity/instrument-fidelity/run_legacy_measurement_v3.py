#!/usr/bin/env python3
"""Run legacy measurement v3 after verifying the authorized red/green evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def find_repo(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "moss_transcribe_diarize").is_dir():
            return candidate
    raise RuntimeError("v3_repo_root_not_found")


HERE = Path(__file__).resolve().parent
REPO = find_repo(HERE)
L2 = REPO / "prototypes/streaming-diarization/l2-stage0"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(L2))

import audit_span_reason_independence as reason_audit  # noqa: E402
import run_legacy_anchor_fidelity as legacy  # noqa: E402


RED_MANIFEST = HERE / "adapter-v3-red/ADAPTER_V3_RED_EVIDENCE.sha256"
GREEN_MANIFEST = HERE / "adapter-v3-green-v2/ADAPTER_V3_GREEN_EVIDENCE.sha256"
CONTAMINATION_MANIFEST = HERE / "v2-contamination-v2/V2_CONTAMINATION_EVIDENCE.sha256"
REASON_RESULT = HERE / "adapter-v3-green-v2/reason.json"
EXPECTED = {
    "red_manifest": "74bee1d413b1edcdbf96e52956a29b6b2be93812a206faa8b841c4e41ad14884",
    "green_manifest": "a52ea7f7d5a71ee0d0bf62a90eb3a9f1e63c2f20420184d53171f873531b914a",
    "contamination_manifest": "bcc667941906a847fd2d030fac3bb3416268486c0f5d569438404bc22a1f6ba6",
    "reason_result": "4829911310afea421eeff41fd9ad09b6c6a71c125249ab864edc6ba3d9ebc52f",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def verify_manifest(path: Path) -> int:
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        target = Path(relative)
        if not target.is_absolute():
            target = REPO / target
        actual = sha256_file(target)
        if actual != expected:
            raise RuntimeError(
                f"v3_precondition_manifest_failed:{repo_path(path)}:{relative}:{actual}"
            )
        count += 1
    return count


def require_preconditions() -> dict[str, object]:
    paths = {
        "red_manifest": RED_MANIFEST,
        "green_manifest": GREEN_MANIFEST,
        "contamination_manifest": CONTAMINATION_MANIFEST,
        "reason_result": REASON_RESULT,
    }
    actual = {name: sha256_file(path) for name, path in paths.items()}
    drift = {
        name: {"expected": EXPECTED[name], "actual": actual[name]}
        for name in paths
        if actual[name] != EXPECTED[name]
    }
    if drift:
        raise RuntimeError(f"v3_precondition_hash_drift:{json.dumps(drift, sort_keys=True)}")
    return {
        "hashes": actual,
        "verified_manifest_rows": {
            "red": verify_manifest(RED_MANIFEST),
            "green": verify_manifest(GREEN_MANIFEST),
            "contamination": verify_manifest(CONTAMINATION_MANIFEST),
        },
    }


def run(output_dir: Path, audit_output: Path) -> tuple[int, dict[str, object]]:
    if audit_output.exists():
        raise RuntimeError(f"v3_audit_output_exists:{audit_output}")
    preconditions = require_preconditions()
    reason_audit.TEST_RESULT = REASON_RESULT
    audit = reason_audit.audit()
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    legacy.SPAN_REASON_AUDIT = audit_output
    legacy.SPAN_REASON_TEST = REASON_RESULT
    status, measurement = legacy.run_measurement(output_dir)
    result = {
        "audit_path": repo_path(audit_output),
        "audit_sha256": sha256_file(audit_output),
        "measurement": measurement,
        "measurement_status": status,
        "preconditions": preconditions,
        "schema": "moss-l2-stage0-legacy-measurement-v3-wrapper.v1",
    }
    wrapper_result = output_dir / "v3-wrapper-result.json"
    wrapper_result.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return status, {
        **result,
        "wrapper_result_path": repo_path(wrapper_result),
        "wrapper_result_sha256": sha256_file(wrapper_result),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        status, result = run(args.output_dir, args.audit_output)
    except Exception as exc:
        print(f"BLOCKED {exc.__class__.__name__}:{exc}")
        print("<promise>BLOCKED</promise>")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    if status:
        print("<promise>BLOCKED</promise>")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
