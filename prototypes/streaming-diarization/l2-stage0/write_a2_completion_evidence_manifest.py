#!/usr/bin/env python3
"""Seal current A2 completion and diagnosis evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUTPUT = HERE / "evidence/A2_COMPLETION_EVIDENCE.sha256"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    paths = {
        HERE / ".gitattributes",
        HERE / "a5-holdout-procedure.json",
        HERE / "l1-control-spec.json",
        HERE / "run_l1_control.py",
        HERE / "test_l1_control.py",
        HERE / "verify_a2_completion.py",
        HERE / "write_a2_completion_evidence_manifest.py",
        HERE / "evidence/A12_EVIDENCE.sha256",
        HERE / "evidence/A2_EVIDENCE.sha256",
        HERE / "evidence/A2_PATH_FIX_EVIDENCE.sha256",
        HERE / "evidence/A2_RENEWED_EVIDENCE.sha256",
        HERE / "evidence/ANCHOR_FIDELITY_EVIDENCE.sha256",
        HERE / "evidence/a12-cache-provenance-audit.json",
        HERE / "evidence/a2-completion-tests.json",
        HERE / "evidence/a2-completion-tests-transcript.txt",
        HERE / "evidence/a2-completion-verdict.json",
        HERE / "evidence/a2-completion-verdict-transcript.txt",
        HERE / "evidence/a2-l1-renewed-fixed-summary.json",
        HERE / "evidence/a2-l1-renewed-fixed-transcript.txt",
    }
    paths.update((HERE / "evidence/a2-l1-renewed-fixed-runs").glob("*.json"))
    paths.update(
        path
        for path in (HERE / "evidence/anchor-fidelity").rglob("*")
        if path.is_file()
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
