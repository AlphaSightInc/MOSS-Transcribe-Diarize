#!/usr/bin/env python3
"""Verify every pre-terminal L1.5 evidence manifest at HEAD or its owning commit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUTPUT = HERE / "evidence/closing/evidence-manifest-audit.json"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_manifest(path: Path) -> list[tuple[str, str]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        rows.append((expected, relative))
    return rows


def owning_commit(path: Path) -> str | None:
    relative = path.relative_to(REPO).as_posix()
    completed = subprocess.run(
        ["git", "-C", str(REPO), "log", "-1", "--format=%H", "--", relative],
        text=True,
        capture_output=True,
        check=False,
    )
    value = completed.stdout.strip()
    return value or None


def commit_blob(commit: str, path: Path) -> bytes | None:
    try:
        relative = path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return None
    completed = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{commit}:{relative}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return completed.stdout if completed.returncode == 0 else None


def main() -> int:
    if OUTPUT.exists():
        raise RuntimeError("l15_manifest_audit_exists")
    manifests = sorted(
        {
            *HERE.glob("evidence/**/*EVIDENCE*.sha256"),
            *(REPO / "scripts/ralph-l15-afk/evidence").glob("*EVIDENCE*.sha256"),
        }
    )
    results: list[dict[str, Any]] = []
    for manifest in manifests:
        if manifest.name == "L15_EVIDENCE.sha256":
            continue
        rows = parse_manifest(manifest)
        head_failed = []
        resolved = []
        for expected, relative in rows:
            target = (manifest.parent / relative).resolve()
            resolved.append((expected, target, relative))
            if not target.is_file() or sha256_bytes(target.read_bytes()) != expected:
                head_failed.append(relative)
        owner = owning_commit(manifest)
        owner_failed = []
        if head_failed and owner is not None:
            for expected, target, relative in resolved:
                payload = commit_blob(owner, target)
                if payload is None or sha256_bytes(payload) != expected:
                    owner_failed.append(relative)
        status = "HEAD_PASS" if not head_failed else (
            "OWNING_COMMIT_PASS" if owner is not None and not owner_failed else "FAIL"
        )
        results.append(
            {
                "path": manifest.relative_to(REPO).as_posix(),
                "row_count": len(rows),
                "status": status,
                "head_failed": head_failed,
                "owning_commit": owner,
                "owning_commit_failed": owner_failed,
            }
        )
    failures = [result["path"] for result in results if result["status"] == "FAIL"]
    payload = {
        "schema": "moss-l15-evidence-manifest-audit.v1",
        "manifest_count": len(results),
        "head_pass_count": sum(result["status"] == "HEAD_PASS" for result in results),
        "owning_commit_pass_count": sum(result["status"] == "OWNING_COMMIT_PASS" for result in results),
        "failures": failures,
        "manifests": results,
        "overall": "PASS" if not failures else "FAIL",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
