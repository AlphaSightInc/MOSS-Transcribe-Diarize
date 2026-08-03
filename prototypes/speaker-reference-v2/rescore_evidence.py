#!/usr/bin/env python3
"""Rescore immutable live evidence against its original reference and frozen v2."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from moss_transcribe_diarize.live_speaker_accuracy import evaluate_live_speaker_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-v2", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, action="append", required=True)
    args = parser.parse_args()
    output = []
    for evidence in args.evidence:
        old = evaluate_live_speaker_evidence(evidence)
        with tempfile.TemporaryDirectory(prefix="moss-rescore-") as scratch:
            target = Path(scratch)
            shutil.copy2(evidence / "speaker-final.json", target / "speaker-final.json")
            shutil.copy2(args.reference_v2, target / "speaker-reference.jsonl")
            values = _env(evidence / "corpus.env")
            values["CORPUS_REFERENCE_SHA256"] = hashlib.sha256(
                args.reference_v2.read_bytes()
            ).hexdigest()
            values["CORPUS_REFERENCE_SEGMENTS"] = str(
                sum(1 for line in args.reference_v2.read_text().splitlines() if line)
            )
            (target / "corpus.env").write_text(
                "".join(f"{key}={value}\n" for key, value in values.items())
            )
            new = evaluate_live_speaker_evidence(target)
        output.append(
            {
                "evidence": str(evidence.resolve()),
                "original_reference": _metrics(old),
                "reference_v2": _metrics(new),
            }
        )
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def _metrics(result: dict) -> dict:
    return {
        key: result[key]
        for key in (
            "reference_sha256",
            "speaker_accuracy",
            "reference_coverage",
            "speaker_activity_precision",
            "speaker_activity_recall",
            "false_positive_speaker_seconds",
            "missed_speaker_seconds",
            "confused_speaker_seconds",
            "diarization_error_rate",
            "speaker_mapping",
            "speaker_correctness",
            "two_sided_mapping",
            "corpus_alignment_adjustment_sec",
        )
    }


def _env(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


if __name__ == "__main__":
    raise SystemExit(main())
