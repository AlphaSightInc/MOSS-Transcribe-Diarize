#!/usr/bin/env python3
"""Seal A1.2 cache-remediation inputs, raw proofs, and versioned cache files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUTPUT = HERE / "evidence/A12_EVIDENCE.sha256"
AUDIT = HERE / "evidence/a12-cache-provenance-audit.json"
STATIC_FILES = [
    "scripts/ralph-l2-afk/contract.json",
    "prototypes/streaming-diarization/l2-stage0/a5-holdout-procedure.json",
    "prototypes/streaming-diarization/l2-stage0/cache-rebuild-spec.json",
    "prototypes/streaming-diarization/l2-stage0/candidate-config.json",
    "prototypes/streaming-diarization/l2-stage0/corpus-manifest.json",
    "prototypes/streaming-diarization/l2-stage0/holdout-manifest.json",
    "prototypes/streaming-diarization/l2-stage0/l1-control-spec.json",
    "prototypes/streaming-diarization/l2-stage0/model-manifest.json",
    "prototypes/streaming-diarization/l2-stage0/production_cache.py",
    "prototypes/streaming-diarization/l2-stage0/rebuild_caches.py",
    "prototypes/streaming-diarization/l2-stage0/run_l1_control.py",
    "prototypes/streaming-diarization/l2-stage0/test_l1_control.py",
    "prototypes/streaming-diarization/l2-stage0/test_production_cache.py",
    "prototypes/streaming-diarization/l2-stage0/test_validate_inputs.py",
    "prototypes/streaming-diarization/l2-stage0/validate_inputs.py",
    "prototypes/streaming-diarization/l2-stage0/evidence/a12-cache-provenance-audit.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a12-cache-rebuild-transcript.txt",
    "prototypes/streaming-diarization/l2-stage0/evidence/a12-red-holdout-cache-rebuild.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a12-red-holdout-cache-rebuild-transcript.txt",
    "prototypes/streaming-diarization/l2-stage0/evidence/a12-renewed-a1-validation.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a12-renewed-a1-validation-final.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a1-a12-renewed-green.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a1-a12-renewed-green-transcript.txt",
    "prototypes/streaming-diarization/l2-stage0/evidence/a1-a12-renewed-green-fixed.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a1-a12-renewed-green-fixed-transcript.txt",
    "prototypes/streaming-diarization/l2-stage0/evidence/a1-a12-renewed-green-final.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a1-a12-renewed-green-final-transcript.txt",
    "prototypes/streaming-diarization/l2-stage0/evidence/a2-renewed-green-tests.json",
    "prototypes/streaming-diarization/l2-stage0/evidence/a2-renewed-green-tests-transcript.txt",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    if audit.get("overall") != "PASS" or audit.get("selected_case_count") != 16:
        raise SystemExit("A1.2 audit is not a 16-case PASS")
    if any(case.get("self_replan", {}).get("self_replan") != "PASS" for case in audit["cases"]):
        raise SystemExit("A1.2 audit contains a self-replan failure")
    cache_files = [case["new_cache_path"] for case in audit["cases"]]
    files = STATIC_FILES + cache_files
    missing = [name for name in files if not (REPO / name).is_file()]
    if missing:
        raise SystemExit("missing A1.2 evidence: " + ", ".join(missing))
    OUTPUT.write_text(
        "".join(f"{sha256(REPO / name)}  {name}\n" for name in files),
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT.relative_to(REPO)} with {len(files)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
