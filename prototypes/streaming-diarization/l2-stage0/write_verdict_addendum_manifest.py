#!/usr/bin/env python3
"""Seal the post-verdict independent-review correction."""

from __future__ import annotations

import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "L2_STAGE0_VERDICT_ADDENDUM.sha256"
INPUTS = (
    HERE / "L2_STAGE0_VERDICT_ADDENDUM.json",
    HERE / "L2_STAGE0_VERDICT_ADDENDUM.md",
)


def main() -> int:
    if OUTPUT.exists():
        raise RuntimeError("verdict_addendum_manifest_exists")
    rows = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in INPUTS
    ]
    OUTPUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"WROTE {OUTPUT.name} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
