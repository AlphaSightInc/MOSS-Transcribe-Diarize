#!/usr/bin/env python3
"""Seal renewed A2 raw runs, specs, stop verdict, and holdout refusal proof."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SUMMARY = HERE / "evidence/a2-l1-renewed-fixed-summary.json"
OUTPUT = HERE / "evidence/A2_RENEWED_EVIDENCE.sha256"
STATIC_FILES = [
    "prototypes/streaming-diarization/l2-stage0/a5-holdout-procedure.json",
    "prototypes/streaming-diarization/l2-stage0/cache-rebuild-spec.json",
    "prototypes/streaming-diarization/l2-stage0/candidate-config.json",
    "prototypes/streaming-diarization/l2-stage0/corpus-manifest.json",
    "prototypes/streaming-diarization/l2-stage0/l1-control-spec.json",
    "prototypes/streaming-diarization/l2-stage0/model-manifest.json",
    "prototypes/streaming-diarization/l2-stage0/production_cache.py",
    "prototypes/streaming-diarization/l2-stage0/run_l1_control.py",
    "prototypes/streaming-diarization/l2-stage0/test_l1_control.py",
    "prototypes/streaming-diarization/l2-stage0/evidence/A12_EVIDENCE.sha256",
    "prototypes/streaming-diarization/l2-stage0/evidence/A2_PATH_FIX_EVIDENCE.sha256",
    "prototypes/streaming-diarization/l2-stage0/evidence/a2-path-fix-tests.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a2-path-fix-tests-transcript.txt",
    "prototypes/streaming-diarization/l2-stage0/evidence/a2-l1-renewed-fixed-summary.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a2-l1-renewed-fixed-transcript.txt",
    "prototypes/streaming-diarization/l2-stage0/evidence/a2-renewed-verdict.json",
    "scripts/ralph-l2-afk/evidence/a2-red-holdout.json",
    "scripts/ralph-l2-afk/evidence/a2-red-holdout-transcript.txt",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    if summary.get("failures") != ["l1_accepted_alphabet_band_failed"]:
        raise SystemExit("renewed A2 failure is not the predeclared alphabet gate")
    if len(summary.get("cases", [])) != 6:
        raise SystemExit("renewed A2 does not contain six cases")
    if any(not case.get("deterministic") for case in summary["cases"]):
        raise SystemExit("renewed A2 contains a nondeterministic case")
    run_files = [run["path"] for case in summary["cases"] for run in case["runs"]]
    files = STATIC_FILES + run_files
    missing = [name for name in files if not (REPO / name).is_file()]
    if missing:
        raise SystemExit("missing renewed A2 evidence: " + ", ".join(missing))
    OUTPUT.write_text(
        "".join(f"{sha256(REPO / name)}  {name}\n" for name in files),
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT.relative_to(REPO)} with {len(files)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
