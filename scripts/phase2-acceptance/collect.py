#!/usr/bin/env python3
"""Reduce one fresh directory of raw Phase-2 observations into a candidate-bound report."""

from __future__ import annotations

import os
from pathlib import Path

from moss_transcribe_diarize.phase2_acceptance_collect import collect_layer, write_collected_report


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def main() -> int:
    payload = collect_layer(
        layer=_required("MOSS_ACCEPTANCE_LAYER"),
        candidate_sha=_required("MOSS_ACCEPTANCE_CANDIDATE_SHA"),
        raw_dir=Path(_required("MOSS_ACCEPTANCE_RAW_DIR")),
    )
    write_collected_report(payload, Path(_required("MOSS_ACCEPTANCE_REPORT_PATH")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
