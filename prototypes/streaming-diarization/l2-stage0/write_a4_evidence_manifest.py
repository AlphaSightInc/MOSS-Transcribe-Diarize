#!/usr/bin/env python3
"""Seal A4 runtime evidence and owning prototype sources."""

from __future__ import annotations

import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUTPUT = HERE / "evidence/A4_EVIDENCE.sha256"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    paths = {
        HERE / "corpus-manifest.json",
        HERE / "evaluate_runtime.py",
        HERE / "lifecycle_prototype.py",
        HERE / "measure_runtime.py",
        HERE / "model-manifest.json",
        HERE / "write_a4_evidence_manifest.py",
    }
    paths.update(path for path in (HERE / "evidence/a4").rglob("*") if path.is_file())
    missing = sorted(path for path in paths if not path.is_file())
    if missing:
        raise SystemExit("missing evidence: " + ", ".join(str(path) for path in missing))
    rows = [f"{sha256(path)}  {path.relative_to(REPO).as_posix()}" for path in sorted(paths)]
    OUTPUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"sealed={len(rows)} output={OUTPUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
