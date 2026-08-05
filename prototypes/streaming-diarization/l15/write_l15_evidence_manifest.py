#!/usr/bin/env python3
"""Seal all L1.5 raw evidence, terminal artifacts, and cited frame evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
L2 = REPO / "prototypes/streaming-diarization/l2-stage0"
DESTINATION = HERE / "L15_EVIDENCE.sha256"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def include_tree(root: Path) -> set[Path]:
    return {
        path
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }


def main() -> int:
    if DESTINATION.exists():
        raise RuntimeError("l15_evidence_manifest_exists")
    paths = include_tree(HERE)
    paths.update(include_tree(REPO / "scripts/ralph-l15-afk"))
    paths.update(
        {
            REPO / ".gitattributes",
            REPO / "docs/design-streaming-diarization.md",
            REPO / "docs/plans/l15-live-uplift-0804.md",
            REPO / "prototypes/streaming-diarization/NOTES.md",
            REPO / "prototypes/streaming-diarization/README.md",
            L2 / "evidence/a5-dev-v4/a5-dev-validation.json",
            L2 / "evidence/A5_DEV_EVIDENCE.sha256",
            L2 / "evidence/a5-holdout-opening/a5-holdout-summary.json",
            L2 / "evidence/a5-holdout-opening/A5_HOLDOUT_EVIDENCE.sha256",
        }
    )
    paths.discard(DESTINATION)
    required = {
        HERE / "L15_VERDICT.json",
        HERE / "evidence/closing/closing-gates.json",
        HERE / "evidence/closing/l15-verdict-verification.json",
        HERE / "evidence/closing/evidence-manifest-audit.json",
    }
    missing = [path for path in sorted(paths | required) if not path.is_file()]
    if missing:
        raise RuntimeError("l15_evidence_missing:" + ",".join(map(str, missing)))
    paths.update(required)
    rows = [
        f"{sha256(path)}  {path.resolve().relative_to(REPO.resolve()).as_posix()}"
        for path in sorted(paths)
    ]
    DESTINATION.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "manifest_sha256": sha256(DESTINATION),
                "path_count": len(rows),
                "overall": "PASS",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
