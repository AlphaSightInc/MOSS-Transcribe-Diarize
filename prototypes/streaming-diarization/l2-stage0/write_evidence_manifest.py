#!/usr/bin/env python3
"""Write the A1 SHA-256 manifest over frozen inputs and raw proof outputs."""

from __future__ import annotations

import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUTPUT = HERE / "evidence/A1_EVIDENCE.sha256"
FILES = [
    "prototypes/streaming-diarization/l2-stage0/candidate-config.json",
    "prototypes/streaming-diarization/l2-stage0/corpus-manifest.json",
    "prototypes/streaming-diarization/l2-stage0/holdout-manifest.json",
    "prototypes/streaming-diarization/l2-stage0/model-manifest.json",
    "prototypes/streaming-diarization/l2-stage0/operator-questions-A1.md",
    "prototypes/streaming-diarization/l2-stage0/evidence/a1-setup.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a1-setup-repeat.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a1-validation.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/vector-rebuild.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a1-holdout-refusal.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a1-holdout-refusal-transcript.txt",
    "prototypes/streaming-diarization/l2-stage0/evidence/a1-guardrail-regression.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a1-guardrail-regression-transcript.txt",
    "prototypes/streaming-diarization/l2-stage0/evidence/A1_GUARDRAIL_REGRESSION_EVIDENCE.sha256",
    "scripts/ralph-l2-afk/evidence/a1-red-first.json",
    "scripts/ralph-l2-afk/evidence/a1-red-first-transcript.txt",
    "scripts/ralph-l2-afk/evidence/a1-green-boundaries.json",
    "scripts/ralph-l2-afk/evidence/a1-green-boundaries-transcript.txt",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    missing = [name for name in FILES if not (REPO / name).is_file()]
    if missing:
        raise SystemExit("missing A1 evidence: " + ", ".join(missing))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "".join(f"{sha256(REPO / name)}  {name}\n" for name in FILES),
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT.relative_to(REPO)} with {len(FILES)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
