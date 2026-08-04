#!/usr/bin/env python3
"""Write the post-verdict keeper-closing SHA-256 index."""

from __future__ import annotations

import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CLOSING = HERE / "evidence/closing"
OUTPUT = CLOSING / "KEEPER_CLOSING.sha256"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUTPUT.exists():
        raise RuntimeError("keeper_closing_manifest_exists")
    paths = [
        REPO / "docs/adr/0002-two-tier-diarization-fingerprint-album.md",
        REPO / "docs/design-streaming-diarization.md",
        REPO / "prototypes/streaming-diarization/NOTES.md",
        REPO / "scripts/ralph-l2-afk/README.md",
        HERE / "README.md",
        HERE / "L2_STAGE0_EVIDENCE.sha256",
        HERE / "L2_STAGE0_VERDICT.json",
        HERE / "L2_STAGE0_VERDICT_ADDENDUM.json",
        HERE / "L2_STAGE0_VERDICT_ADDENDUM.md",
        HERE / "L2_STAGE0_VERDICT_ADDENDUM.sha256",
        HERE / "SEAM_INVENTORY.md",
        HERE / "candidate-config.json",
        HERE / "a5-dev-candidate-family-v4.json",
        HERE / "run_candidates.py",
        HERE / "verify_all_evidence_manifests.py",
        HERE / "write_verdict_addendum_manifest.py",
        HERE / "write_keeper_closing_manifest.py",
        REPO / "scripts/ralph-l2-afk/contract.json",
    ]
    paths.extend(path for path in sorted(CLOSING.iterdir()) if path != OUTPUT)
    unique = sorted(set(paths), key=lambda path: path.relative_to(REPO).as_posix())
    missing = [path for path in unique if not path.is_file()]
    if missing:
        raise RuntimeError(f"keeper_closing_input_missing:{missing}")
    lines = [
        f"{sha256(path)}  {path.relative_to(REPO).as_posix()}" for path in unique
    ]
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"WROTE {OUTPUT.relative_to(REPO)} rows={len(lines)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
