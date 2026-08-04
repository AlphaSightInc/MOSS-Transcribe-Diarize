#!/usr/bin/env python3
"""Seal A4 operator-completion evidence without rewriting historical A4 evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUTPUT = HERE / "evidence/A4_COMPLETION_EVIDENCE.sha256"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    paths = {
        HERE / ".gitattributes",
        HERE / "complete_a4.py",
        HERE / "test_complete_a4.py",
        HERE / "write_a4_completion_evidence_manifest.py",
        HERE / "evidence/A4_EVIDENCE.sha256",
        HERE / "evidence/a4/a4-verdict.json",
        HERE / "evidence/a4/optimized/a4-runtime-optimized.json",
        HERE / "evidence/a4-completion/red-test-transcript.txt",
        HERE / "evidence/a4-completion/green-test-transcript.txt",
        HERE / "evidence/a4-completion/a4-completion-verdict.json",
        HERE / "evidence/a4-completion/a4-completion-verdict.txt",
        HERE / "evidence/a4-completion/historical-blocked-integrity.json",
    }
    missing = sorted(path for path in paths if not path.is_file())
    if missing:
        raise SystemExit("missing evidence: " + ", ".join(str(path) for path in missing))
    rows = [f"{sha256(path)}  {path.relative_to(REPO).as_posix()}" for path in sorted(paths)]
    OUTPUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"sealed={len(rows)} output={OUTPUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
