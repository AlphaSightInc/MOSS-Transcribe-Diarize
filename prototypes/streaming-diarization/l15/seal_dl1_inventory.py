#!/usr/bin/env python3
"""Seal the complete DL1 inventory package with relative SHA-256 rows."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EVIDENCE_ROOT = ROOT / "evidence" / "dl1-inventory"
OUTPUT = EVIDENCE_ROOT / "DL1_INVENTORY_EVIDENCE.sha256"
REPO_ROOT = ROOT.parents[2]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    required = [
        ROOT / "dl1_inventory.py",
        ROOT / "seal_dl1_inventory.py",
        EVIDENCE_ROOT / "commands.txt",
        EVIDENCE_ROOT / "dl1-inventory.json",
        REPO_ROOT / "prototypes" / "streaming-diarization" / "NOTES.md",
    ]
    required.extend(sorted((ROOT / "data" / "dual_lane_diarization").rglob("*")))
    files = sorted({path.resolve() for path in required if path.is_file()})
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"dl1_evidence_missing:{missing}")
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    lines = []
    for path in files:
        relative = path.relative_to(EVIDENCE_ROOT.resolve()) if path.is_relative_to(EVIDENCE_ROOT.resolve()) else None
        if relative is None:
            relative_text = str(Path(*([".."] * len(EVIDENCE_ROOT.resolve().relative_to(REPO_ROOT.resolve()).parts))) / path.relative_to(REPO_ROOT.resolve()))
        else:
            relative_text = str(relative)
        lines.append(f"{sha256(path)}  {relative_text}")
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"PASS DL1_INVENTORY_EVIDENCE rows={len(lines)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
