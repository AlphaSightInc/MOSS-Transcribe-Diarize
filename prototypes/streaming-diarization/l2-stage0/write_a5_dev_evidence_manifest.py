#!/usr/bin/env python3
"""Seal the complete A5 development/validation and freeze-proposal record."""

from __future__ import annotations

import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUTPUT = HERE / "evidence/A5_DEV_EVIDENCE.sha256"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    paths = {
        HERE / "a5-dev-candidate-family-v1.json",
        HERE / "a5-dev-candidate-family-v2.json",
        HERE / "a5-dev-candidate-family-v3.json",
        HERE / "a5-dev-candidate-family-v4.json",
        HERE / "a5-holdout-procedure.json",
        HERE / "candidate-config.json",
        HERE / "candidate_engine.py",
        HERE / "corpus-manifest.json",
        HERE / "l1-control-spec.json",
        HERE / "model-manifest.json",
        HERE / "run_candidates.py",
        HERE / "test_candidates.py",
        HERE / "test_continuity_candidate.py",
        HERE / "test_joint_span_candidate.py",
        HERE / "test_span_local_candidate.py",
        HERE / "write_a5_dev_evidence_manifest.py",
        HERE / "evidence/a5-dev-freeze-proposal.json",
        HERE / "evidence/a5-dev-freeze-proposal.txt",
        HERE / "evidence/a5-dev-freeze-proposal-verification-attempt1-failure.txt",
        HERE / "evidence/a5-dev-freeze-proposal-verification.txt",
    }
    for directory in (
        "a5-dev-v1-attempt0",
        "a5-dev-v1-attempt1",
        "a5-dev-v1",
        "a5-dev-v2",
        "a5-dev-v3",
        "a5-dev-v4",
        "a5-green",
        "a5-red",
        "a5-v2-green",
        "a5-v2-red",
        "a5-v3-green",
        "a5-v3-red",
        "a5-v4-green",
        "a5-v4-red",
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
