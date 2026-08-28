#!/usr/bin/env python3
"""Run the fixed candidate-owned external measurement families for one layer."""

from __future__ import annotations

import json
import os
from pathlib import Path

from moss_transcribe_diarize.phase2_acceptance_measure import measure_layer


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def main() -> int:
    config = json.loads(_required("MOSS_ACCEPTANCE_MEASUREMENT_CONFIG"))
    if not isinstance(config, dict):
        raise SystemExit("measurement config must be an object")
    state = measure_layer(
        layer=_required("MOSS_ACCEPTANCE_LAYER"),
        candidate_sha=_required("MOSS_ACCEPTANCE_CANDIDATE_SHA"),
        config=config,
        raw_dir=Path(_required("MOSS_ACCEPTANCE_RAW_DIR")),
    )
    print(json.dumps(state, sort_keys=True))
    return 0 if state["qualified"] is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
