from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from moss_transcribe_diarize.app.speaker_identity import (
    WeSpeakerResNet152LmAdapter,
    tier_b_provider_manifest,
)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    adapter = WeSpeakerResNet152LmAdapter(args.state_path)
    result = adapter.preflight(fixture_path=args.fixture)
    payload: dict[str, Any] = {
        "available": result.available,
        "reason": result.reason,
        "descriptor": result.descriptor,
        "expected": tier_b_provider_manifest(),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"available={str(result.available).lower()}")
        if result.reason:
            print(f"reason={result.reason}")
        for key, value in result.descriptor.items():
            if isinstance(value, dict):
                continue
            print(f"{key}={value}")
    return 0 if result.available else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only preflight for the default-off file-mode speaker identity provider.",
    )
    parser.add_argument(
        "--state-path",
        required=True,
        type=Path,
        help="Existing local WeSpeaker ResNet152-LM state file to hash and load.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="Tiny speech WAV used for deterministic embedding smoke validation; required before service enablement.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable preflight JSON.",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
