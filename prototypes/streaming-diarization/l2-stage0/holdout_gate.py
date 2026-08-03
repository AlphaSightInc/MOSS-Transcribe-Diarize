#!/usr/bin/env python3
"""Fail closed before reading the sealed holdout manifest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from validate_inputs import ValidationError, authorize_holdout_open


BLOCKED_PROMISE = "<promise>BLOCKED</promise>"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-config", type=Path, required=True)
    parser.add_argument("--holdout-manifest", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--transcript-output", type=Path, required=True)
    args = parser.parse_args()
    candidate = json.loads(args.candidate_config.read_text(encoding="utf-8"))
    try:
        holdout = authorize_holdout_open(candidate, args.holdout_manifest)
    except ValidationError as exc:
        payload = {
            "detail": exc.detail,
            "error": exc.code,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall": "BLOCKED",
        }
        transcript = f"BLOCKED {exc.code}: {exc.detail}\n{BLOCKED_PROMISE}\n"
        status = 2
    else:
        payload = {"case_count": len(holdout["cases"]), "overall": "OPENED"}
        transcript = "OPENED holdout_manifest\n"
        status = 0
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.transcript_output.write_text(transcript, encoding="utf-8")
    print(transcript, end="")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
