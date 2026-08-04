#!/usr/bin/env python3
"""Seal A3 lifecycle prototype evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUTPUT = HERE / "evidence/A3_EVIDENCE_V3.sha256"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    paths = {
        HERE / "evaluate_lifecycle.py",
        HERE / "lifecycle_prototype.py",
        HERE / "run_lifecycle_tests.py",
        HERE / "test_lifecycle_prototype.py",
        HERE / "write_a3_evidence_manifest.py",
    }
    for directory in (
        "a3-red",
        "a3-green",
        "a3-negative-red",
        "a3-negative-controls",
        "a3-verdict",
    ):
        paths.update(
            path for path in (HERE / "evidence" / directory).rglob("*") if path.is_file()
        )
    missing = sorted(path for path in paths if not path.is_file())
    if missing:
        raise SystemExit("missing evidence: " + ", ".join(str(path) for path in missing))
    rows = [f"{sha256(path)}  {path.relative_to(REPO).as_posix()}" for path in sorted(paths)]
    OUTPUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"sealed={len(rows)} output={OUTPUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
