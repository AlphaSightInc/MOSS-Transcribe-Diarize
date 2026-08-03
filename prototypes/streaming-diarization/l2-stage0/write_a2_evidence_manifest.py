#!/usr/bin/env python3
"""Write the A2 SHA-256 manifest over specs, runner, tests, and raw outputs."""

from __future__ import annotations

import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUTPUT = HERE / "evidence/A2_EVIDENCE.sha256"
FILES = [
    "prototypes/streaming-diarization/l2-stage0/a5-holdout-procedure.json",
    "prototypes/streaming-diarization/l2-stage0/candidate-config.json",
    "prototypes/streaming-diarization/l2-stage0/corpus-manifest.json",
    "prototypes/streaming-diarization/l2-stage0/l1-control-spec.json",
    "prototypes/streaming-diarization/l2-stage0/run_l1_control.py",
    "prototypes/streaming-diarization/l2-stage0/run_l1_tests.py",
    "prototypes/streaming-diarization/l2-stage0/test_l1_control.py",
    "prototypes/streaming-diarization/l2-stage0/evidence/a2-l1-summary.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a2-l1-transcript.txt",
    "scripts/ralph-l2-afk/evidence/a2-red-holdout.json",
    "scripts/ralph-l2-afk/evidence/a2-red-holdout-transcript.txt",
    "scripts/ralph-l2-afk/evidence/a2-green-tests.json",
    "scripts/ralph-l2-afk/evidence/a2-green-tests-transcript.txt",
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
        raise SystemExit("missing A2 evidence: " + ", ".join(missing))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "".join(f"{sha256(REPO / name)}  {name}\n" for name in FILES),
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT.relative_to(REPO)} with {len(FILES)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
