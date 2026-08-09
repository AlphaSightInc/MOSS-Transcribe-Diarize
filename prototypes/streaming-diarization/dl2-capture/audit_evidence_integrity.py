#!/usr/bin/env python3
"""Audit DL2 evidence manifests without rewriting historical seals."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROW_RE = re.compile(r"^([0-9a-f]{64})  (.+)$")
MUTABLE_NAMES = {
    "NOTES.md",
    "capture_harness.py",
    "post_session.py",
    "test_capture_harness.py",
    "test_post_session.py",
    "session-blueprint.json",
    "operator-checklist-card.md",
    "operator-session-block-20260806.md",
    "grant.json",
    "program-ledger.json",
    "session-manifest.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_candidates(root: Path, manifest: Path, relative: str) -> list[Path]:
    candidates = [manifest.parent / relative, root / relative]
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def session_manifest_for(path: Path, root: Path) -> Path | None:
    try:
        relative = path.resolve().relative_to((root / "program" / "sessions").resolve())
    except ValueError:
        return None
    if not relative.parts:
        return None
    return root / "program" / "sessions" / relative.parts[0] / "session-manifest.json"


def authorized_raw_deletion(path: Path, root: Path) -> bool:
    session_manifest = session_manifest_for(path, root)
    if session_manifest is None or not session_manifest.is_file():
        return False
    relative = path.resolve().relative_to(session_manifest.parent.resolve())
    if not relative.parts or relative.parts[0] not in {"raw", "audio"}:
        return False
    try:
        payload = json.loads(session_manifest.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    cleanup = payload.get("raw_cleanup") or {}
    return (
        payload.get("state") == "audit_ready_raw_deleted"
        and relative.parts[0] in cleanup.get("local_removed", [])
        and cleanup.get("remote_deleted") is True
    )


def is_historical_mutable_path(path: Path) -> bool:
    return path.name in MUTABLE_NAMES


def is_terminal_authority(manifest_rel: str) -> bool:
    if manifest_rel.startswith("program/sessions/") and "/derived" in manifest_rel:
        return True
    prefixes = (
        "evidence/block-close-raw-cleanup-20260809/",
        "evidence/block-close-deprovision-20260809/",
        "evidence/s05-recovery-boundary/",
    )
    return manifest_rel.startswith(prefixes)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output.resolve()
    manifests = sorted(
        path
        for path in root.rglob("*EVIDENCE*.sha256")
        if output.parent not in path.parents
    )
    totals: Counter[str] = Counter()
    manifest_results = []
    terminal_nonpass = []

    for manifest in manifests:
        manifest_rel = manifest.relative_to(root).as_posix()
        counts: Counter[str] = Counter()
        exceptions = []
        for line_number, line in enumerate(manifest.read_text().splitlines(), start=1):
            match = ROW_RE.match(line)
            if not match:
                category = "MALFORMED_ROW"
                record = {"line": line_number, "raw": line}
            else:
                expected, relative = match.groups()
                candidates = resolve_candidates(root, manifest, relative)
                matching = next(
                    (candidate for candidate in candidates if candidate.is_file() and sha256(candidate) == expected),
                    None,
                )
                existing = next((candidate for candidate in candidates if candidate.is_file()), None)
                target = matching or existing or candidates[0]
                if matching is not None:
                    category = "PASS"
                    record = None
                elif existing is None and any(
                    authorized_raw_deletion(candidate, root) for candidate in candidates
                ):
                    category = "AUTHORIZED_RAW_DELETION"
                    target = next(
                        candidate
                        for candidate in candidates
                        if session_manifest_for(candidate, root) is not None
                    )
                    record = {
                        "line": line_number,
                        "path": relative,
                        "expected_sha256": expected,
                        "resolved_path": str(target),
                    }
                elif existing is not None and is_historical_mutable_path(existing):
                    category = "HISTORICAL_MUTABLE_PATH_DRIFT"
                    record = {
                        "line": line_number,
                        "path": relative,
                        "expected_sha256": expected,
                        "actual_sha256": sha256(existing),
                        "resolved_path": str(existing),
                    }
                elif existing is None:
                    category = "MISSING_UNCLASSIFIED"
                    record = {
                        "line": line_number,
                        "path": relative,
                        "expected_sha256": expected,
                        "candidate_paths": [str(candidate) for candidate in candidates],
                    }
                else:
                    category = "HASH_MISMATCH_UNCLASSIFIED"
                    record = {
                        "line": line_number,
                        "path": relative,
                        "expected_sha256": expected,
                        "actual_sha256": sha256(existing),
                        "resolved_path": str(existing),
                    }
            counts[category] += 1
            totals[category] += 1
            if record is not None:
                record["category"] = category
                exceptions.append(record)

        terminal = is_terminal_authority(manifest_rel)
        if terminal and any(category != "PASS" for category in counts):
            terminal_nonpass.append(manifest_rel)
        manifest_results.append(
            {
                "manifest": manifest_rel,
                "manifest_sha256": sha256(manifest),
                "terminal_authority": terminal,
                "counts": dict(sorted(counts.items())),
                "exceptions": exceptions,
            }
        )

    unclassified = sum(
        totals[name]
        for name in ("MALFORMED_ROW", "MISSING_UNCLASSIFIED", "HASH_MISMATCH_UNCLASSIFIED")
    )
    verdict = (
        "PASS_WITH_DISCLOSED_HISTORICAL_DRIFT"
        if not terminal_nonpass and not unclassified
        else "FAIL"
    )
    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "root": str(root),
        "verdict": verdict,
        "policy": {
            "terminal_authority_must_pass": True,
            "authorized_raw_deletion_requires_session_manifest_cleanup_record": True,
            "historical_mutable_path_drift_is_disclosed_not_rewritten": True,
            "historical_mutable_rows_have_no_owning_commit_before_first_harness_commit": True,
        },
        "manifest_count": len(manifests),
        "row_count": sum(totals.values()),
        "totals": dict(sorted(totals.items())),
        "terminal_authority_nonpass": terminal_nonpass,
        "manifests": manifest_results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: payload[key] for key in ("verdict", "manifest_count", "row_count", "totals", "terminal_authority_nonpass")}, indent=2))
    return 0 if verdict != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
