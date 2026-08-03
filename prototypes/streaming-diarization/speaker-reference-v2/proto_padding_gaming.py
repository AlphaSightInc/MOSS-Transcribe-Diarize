#!/usr/bin/env python3
"""Show that 100 ms label padding is visible as invented speaker activity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from moss_transcribe_diarize.live_speaker_accuracy import (  # noqa: E402
    SpeakerActivityInterval,
    _coverage_alignment,
    load_reference_jsonl,
    score_live_speaker_accuracy,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--reference-v2", type=Path, required=True)
    parser.add_argument("--padding-sec", type=float, default=0.1)
    args = parser.parse_args()

    evidence = args.evidence_dir
    metadata = _env(evidence / "corpus.env")
    duration = float(metadata["CORPUS_DURATION_SEC"])
    snapshot = json.loads((evidence / "speaker-final.json").read_text())
    reference = load_reference_jsonl(args.reference_v2)
    _adjustment, hypothesis = _coverage_alignment(
        reference,
        snapshot,
        declared_start_sample=int(metadata["CORPUS_START_SAMPLE"]),
        corpus_duration_sec=duration,
    )
    padded = tuple(
        SpeakerActivityInterval(
            max(0.0, item.start - args.padding_sec),
            min(duration, item.end + args.padding_sec),
            item.speaker,
        )
        for item in hypothesis
    )
    baseline = score_live_speaker_accuracy(reference, hypothesis)
    candidate = score_live_speaker_accuracy(reference, padded)
    invented = sum(item.duration for item in padded) - sum(item.duration for item in hypothesis)
    false_positive_delta = (
        candidate["false_positive_speaker_seconds"]
        - baseline["false_positive_speaker_seconds"]
    )
    detected = false_positive_delta > 0.0 and candidate["diarization_error_rate"] > baseline[
        "diarization_error_rate"
    ]
    result = {
        "schema": "moss-padding-gaming-prototype.v2",
        "padding_sec": args.padding_sec,
        "invented_label_seconds": round(invented, 6),
        "baseline": _metrics(baseline),
        "padded": _metrics(candidate),
        "false_positive_speaker_seconds_delta": round(false_positive_delta, 6),
        "verdict": "FAIL" if detected else "PASS",
        "reason": "invented label activity penalized" if detected else "padding escaped penalty",
    }
    print(json.dumps(result, sort_keys=True))
    return 3 if detected else 0


def _metrics(result: dict) -> dict:
    return {
        key: result[key]
        for key in (
            "speaker_accuracy",
            "reference_coverage",
            "speaker_activity_precision",
            "speaker_activity_recall",
            "false_positive_speaker_seconds",
            "missed_speaker_seconds",
            "confused_speaker_seconds",
            "diarization_error_rate",
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
