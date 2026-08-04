#!/usr/bin/env python3
"""Seal all Campaign-A raw evidence and terminal A6 artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DESTINATION = HERE / "L2_STAGE0_EVIDENCE.sha256"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def repo_path(path: Path) -> str:
    return path.resolve().relative_to(REPO.resolve()).as_posix()


def main() -> int:
    if DESTINATION.exists():
        raise RuntimeError("a6_evidence_manifest_already_exists")
    paths: set[Path] = set()
    for root in (
        REPO / "scripts/ralph-l2-afk/evidence",
        HERE / "evidence",
    ):
        paths.update(path for path in root.rglob("*") if path.is_file())
    paths.update(path for path in HERE.iterdir() if path.is_file())
    paths.update(
        {
            REPO / ".gitattributes",
            REPO / "docs/adr/0002-two-tier-diarization-fingerprint-album.md",
            REPO / "docs/design-streaming-diarization.md",
            REPO / "docs/plans/r1-stage0-minimum-seam-0803.md",
            REPO / "scripts/ralph-l2-afk/contract.json",
            REPO / "scripts/ralph-l2-afk/guardrails.py",
            REPO / "scripts/ralph-l2-afk/launch.py",
        }
    )
    audit = json.loads(
        (HERE / "evidence/a5-holdout-opening/cache-provenance-audit.json").read_text(
            encoding="utf-8"
        )
    )
    paths.update(REPO / case["new_cache_path"] for case in audit["cases"])
    paths.discard(DESTINATION)
    missing = [path for path in sorted(paths) if not path.is_file()]
    if missing:
        raise RuntimeError("a6_evidence_missing:" + ",".join(map(str, missing)))
    rows = [f"{sha256(path)}  {repo_path(path)}" for path in sorted(paths)]
    with DESTINATION.open("x", encoding="utf-8") as handle:
        handle.write("\n".join(rows) + "\n")
    print(
        json.dumps(
            {
                "manifest_sha256": sha256(DESTINATION),
                "overall": "PASS",
                "path_count": len(rows),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
