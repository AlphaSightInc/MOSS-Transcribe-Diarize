#!/usr/bin/env python3
"""Validate a versioned speaker reference and emit one machine-readable verdict."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from moss_transcribe_diarize.speaker_reference import (  # noqa: E402
    AcousticReferenceValidation,
    validate_speaker_reference,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("--lineage", type=Path)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--expected-audio-sha256")
    parser.add_argument("--acoustic-evidence", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--require-acoustic-existence", action="store_true")
    args = parser.parse_args()
    result = validate_speaker_reference(
        args.reference,
        lineage_path=args.lineage,
        acoustic=AcousticReferenceValidation(
            evidence_path=args.acoustic_evidence,
            audio_path=args.audio,
            expected_audio_sha256=args.expected_audio_sha256,
            required=args.require_acoustic_existence,
        ),
        audit_path=args.audit,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["verdict"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
