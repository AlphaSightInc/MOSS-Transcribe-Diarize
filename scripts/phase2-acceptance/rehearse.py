#!/usr/bin/env python3
"""Run the fixed isolated cutover/whole-restore rehearsal."""

from __future__ import annotations

import os
from pathlib import Path

from moss_transcribe_diarize.phase2_cutover_rehearsal import rehearse, write_rehearsal


def _path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return Path(value)


def main() -> int:
    output = _path("MOSS_REHEARSAL_OUTPUT")
    payload = rehearse(
        original_fixture=_path("MOSS_REHEARSAL_ORIGINAL_FIXTURE"),
        candidate_manifest=_path("MOSS_REHEARSAL_CANDIDATE_MANIFEST"),
    )
    write_rehearsal(payload, output)
    return 0 if payload["passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
