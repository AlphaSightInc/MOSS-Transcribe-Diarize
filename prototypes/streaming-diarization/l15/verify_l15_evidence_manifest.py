#!/usr/bin/env python3
"""Verify every row of the terminal L1.5 evidence manifest without writing state."""

from __future__ import annotations

import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MANIFEST = HERE / "L15_EVIDENCE.sha256"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    failures = []
    count = 0
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = REPO / relative
        count += 1
        if not path.is_file() or sha256(path) != expected:
            failures.append(relative)
    print(f"{'PASS' if not failures else 'FAIL'} L15_EVIDENCE rows={count} failures={len(failures)}")
    for failure in failures:
        print(f"FAILED {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
