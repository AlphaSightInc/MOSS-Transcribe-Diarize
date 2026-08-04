#!/usr/bin/env python3
"""Verify every committed *_EVIDENCE manifest at HEAD or its owning commit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUTPUT = HERE / "evidence/closing/all-evidence-manifests-v5.json"
TRANSCRIPT = HERE / "evidence/closing/all-evidence-manifests-v5.txt"

SUPERSEDED_HISTORY = {
    "prototypes/streaming-diarization/l2-stage0/evidence/A3_EVIDENCE.sha256":
        "prototypes/streaming-diarization/l2-stage0/evidence/A3_EVIDENCE_V3.sha256",
    "prototypes/streaming-diarization/l2-stage0/evidence/A3_EVIDENCE_V2.sha256":
        "prototypes/streaming-diarization/l2-stage0/evidence/A3_EVIDENCE_V3.sha256",
    "prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/LEGACY_INGEST_DIAGNOSIS_EVIDENCE.sha256":
        "prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/LEGACY_INGEST_DIAGNOSIS_EVIDENCE_V2.sha256",
    "prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/LEGACY_INGEST_DIAGNOSIS_EVIDENCE_V2.sha256":
        "prototypes/streaming-diarization/l2-stage0/evidence/A2_COMPLETION_EVIDENCE.sha256",
    "prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/ADAPTER_V3_BOUNDARY_EVIDENCE.sha256":
        "prototypes/streaming-diarization/l2-stage0/evidence/A2_COMPLETION_EVIDENCE.sha256",
    "prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/FRAME_DIAGNOSIS_EVIDENCE.sha256":
        "prototypes/streaming-diarization/l2-stage0/evidence/A2_COMPLETION_EVIDENCE.sha256",
    "prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/INSTRUMENT_FIDELITY_DIAGNOSIS_EVIDENCE.sha256":
        "prototypes/streaming-diarization/l2-stage0/evidence/A2_COMPLETION_EVIDENCE.sha256",
    "prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/ORIGINAL_RENEWED_DIFFERENTIAL_EVIDENCE.sha256":
        "prototypes/streaming-diarization/l2-stage0/evidence/A2_COMPLETION_EVIDENCE.sha256",
    "prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/h3-first-divergence-v1/H3_FIRST_DIVERGENCE_EVIDENCE.sha256":
        "prototypes/streaming-diarization/l2-stage0/evidence/A2_COMPLETION_EVIDENCE.sha256",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_manifest(value: bytes) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for raw in value.decode("utf-8").splitlines():
        if not raw.strip():
            continue
        expected, path = raw.split(maxsplit=1)
        rows.append((expected, path.lstrip(" *")))
    return rows


def git_blob(commit: str, path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{commit}:{path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def row_candidates(manifest: Path, value: str) -> list[tuple[Path, str | None]]:
    raw = Path(value)
    if raw.is_absolute():
        paths = [raw]
    else:
        paths = [REPO / raw, manifest.parent / raw]
    candidates: list[tuple[Path, str | None]] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            git_relative = resolved.relative_to(REPO.resolve()).as_posix()
        except ValueError:
            git_relative = None
        candidates.append((path, git_relative))
    return candidates


def find_expected_commit(path: str, expected: str) -> str | None:
    history = subprocess.check_output(
        ["git", "-C", str(REPO), "log", "--format=%H", "HEAD", "--", path],
        text=True,
    ).splitlines()
    for commit in history:
        value = git_blob(commit, path)
        if value is not None and sha256_bytes(value) == expected:
            return commit
    return None


def resolve_rows(
    manifest: Path, rows: list[tuple[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    resolved: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    for expected, row_path in rows:
        candidates = row_candidates(manifest, row_path)
        current_values = [
            sha256_bytes(path.read_bytes()) if path.is_file() else "MISSING"
            for path, _ in candidates
        ]
        if expected in current_values:
            resolved.append(
                {
                    "mode": "HEAD",
                    "path": row_path,
                    "resolved_path": str(candidates[current_values.index(expected)][0]),
                }
            )
            continue
        commit = None
        matched_path = None
        for _, git_relative in candidates:
            if git_relative is None:
                continue
            commit = find_expected_commit(git_relative, expected)
            if commit is not None:
                matched_path = git_relative
                break
        if commit is not None:
            resolved.append(
                {
                    "commit": commit,
                    "mode": "OWNING_COMMIT",
                    "path": row_path,
                    "resolved_path": str(matched_path),
                }
            )
        else:
            failures.append(
                {
                    "current_candidates": ",".join(current_values),
                    "expected": expected,
                    "path": row_path,
                }
            )
    return resolved, failures


def main() -> int:
    if OUTPUT.exists() or TRANSCRIPT.exists():
        raise RuntimeError("evidence_manifest_audit_output_exists")
    manifests = sorted(REPO.rglob("*EVIDENCE*.sha256"))
    records: list[dict[str, object]] = []
    lines = [
        "COMMAND: python prototypes/streaming-diarization/l2-stage0/verify_all_evidence_manifests.py"
    ]
    for manifest in manifests:
        relative = manifest.relative_to(REPO).as_posix()
        head_bytes = manifest.read_bytes()
        rows = parse_manifest(head_bytes)
        resolved, failures = resolve_rows(manifest, rows)
        owner_commits = sorted(
            {item["commit"] for item in resolved if item["mode"] == "OWNING_COMMIT"}
        )
        head_rows = sum(item["mode"] == "HEAD" for item in resolved)
        superseded_by = SUPERSEDED_HISTORY.get(relative) if failures else None
        status = (
            "PASS"
            if not failures
            else "PASS_SUPERSEDED_HISTORY"
            if superseded_by is not None
            else "FAIL"
        )
        record: dict[str, object] = {
            "classification": status,
            "failure_count": len(failures),
            "failures": failures,
            "head_row_count": head_rows,
            "manifest_path": relative,
            "manifest_sha256": sha256_bytes(head_bytes),
            "overall": "PASS" if status != "FAIL" else "FAIL",
            "owning_commit_row_count": len(resolved) - head_rows,
            "owning_commits": owner_commits,
            "row_count": len(rows),
            "superseded_by": superseded_by,
        }
        mode = "HEAD" if not owner_commits else "HEAD+OWNING_COMMIT"
        lines.append(
            f"{status} {mode} rows={len(rows)} head_rows={head_rows} "
            f"owner_rows={len(resolved) - head_rows} owners={','.join(owner_commits) or '-'} "
            f"failures={len(failures)} {relative}"
        )
        records.append(record)
    result = {
        "authoritative_pass_count": sum(
            item["classification"] == "PASS" for item in records
        ),
        "manifest_count": len(records),
        "manifests": records,
        "overall": "PASS" if all(item["overall"] == "PASS" for item in records) else "FAIL",
        "schema": "moss-l2-stage0-all-evidence-manifest-audit.v1",
        "superseded_history_count": sum(
            item["classification"] == "PASS_SUPERSEDED_HISTORY" for item in records
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines.append(f"OVERALL={result['overall']} MANIFESTS={len(records)}")
    TRANSCRIPT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
