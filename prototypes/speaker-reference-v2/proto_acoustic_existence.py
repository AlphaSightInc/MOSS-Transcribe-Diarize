#!/usr/bin/env python3
"""Measure a deletion-capable reference-existence gate against independent ASR."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from moss_transcribe_diarize.speaker_reference import normalize_reference_text  # noqa: E402
from moss_transcribe_diarize.transcript_parser import parse_transcript  # noqa: E402


@dataclass(frozen=True)
class Match:
    score: float
    reference_recall: float
    asr_precision: float
    asr_text: str


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asr", type=Path)
    parser.add_argument("--asr-dir", type=Path)
    parser.add_argument("--positive-reference", type=Path, required=True)
    parser.add_argument("--negative-reference", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.65)
    parser.add_argument("--slack-sec", type=float, default=1.5)
    args = parser.parse_args()

    if (args.asr is None) == (args.asr_dir is None):
        parser.error("exactly one of --asr or --asr-dir is required")

    segments = _load_asr(args.asr, args.asr_dir)
    authoritative = _read_jsonl(args.positive_reference)
    negative = _read_jsonl(args.negative_reference)

    false_rejects = 0
    accepted_absent: list[dict[str, Any]] = []
    for present, rows in ((True, authoritative), (False, negative)):
        for index, row in enumerate(rows, start=1):
            match = score_existence(row, segments, slack_sec=args.slack_sec)
            accepted = match.score >= args.threshold
            _start, _end, text = _row_fields(row)
            if present and not accepted:
                false_rejects += 1
            if not present and accepted:
                accepted_absent.append({"record": index, "text": text, **asdict(match)})
            print(
                json.dumps(
                    {
                        "record": index,
                        "known_present": present,
                        "accepted": accepted,
                        "text": text,
                        **asdict(match),
                    },
                    sort_keys=True,
                )
            )

    absent_count = len(negative)
    verdict = not false_rejects and absent_count > 0 and not accepted_absent
    print(
        json.dumps(
            {
                "schema": "moss-acoustic-existence-prototype.v1",
                "independent_asr_segments": len(segments),
                "known_present": len(authoritative),
                "known_absent": absent_count,
                "false_rejects": false_rejects,
                "accepted_absent": accepted_absent,
                "threshold": args.threshold,
                "slack_sec": args.slack_sec,
                "verdict": "PASS" if verdict else "FAIL",
            },
            sort_keys=True,
        )
    )
    return 0 if verdict else 3


def score_existence(row: dict[str, Any], segments: list[Any], *, slack_sec: float) -> Match:
    start, end, text = _row_fields(row)
    reference_tokens = normalize_reference_text(text).split()
    nearby = [
        segment
        for segment in segments
        if segment.end >= start - slack_sec
        and segment.start <= end + slack_sec
    ]
    asr_tokens = normalize_reference_text(" ".join(segment.text for segment in nearby)).split()
    if not reference_tokens or not asr_tokens:
        return Match(0.0, 0.0, 0.0, "")

    best = Match(0.0, 0.0, 0.0, "")
    minimum = max(1, len(reference_tokens) - 4)
    maximum = min(len(asr_tokens), len(reference_tokens) + 4)
    for width in range(minimum, maximum + 1):
        for first in range(0, len(asr_tokens) - width + 1):
            window = asr_tokens[first : first + width]
            matches = sum(
                block.size
                for block in SequenceMatcher(None, reference_tokens, window, autojunk=False).get_matching_blocks()
            )
            recall = matches / len(reference_tokens)
            precision = matches / len(window)
            score = 0.0 if not matches else 2.0 * recall * precision / (recall + precision)
            if score > best.score:
                best = Match(score, recall, precision, " ".join(window))
    return best


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _key(row: dict[str, Any]) -> tuple[str, str]:
    if row.get("schema") == "moss-speaker-reference.v2":
        return (
            str(row["speaker_activity"]["speaker"]),
            normalize_reference_text(row["transcript"]["text"]),
        )
    return str(row["speaker"]), normalize_reference_text(row["text"])


def _row_fields(row: dict[str, Any]) -> tuple[float, float, str]:
    if row.get("schema") == "moss-speaker-reference.v2":
        return (
            float(row["speaker_activity"]["start"]),
            float(row["speaker_activity"]["end"]),
            str(row["transcript"]["text"]),
        )
    return float(row["start"]), float(row["end"]), str(row["text"])


def _load_asr(asr: Path | None, asr_dir: Path | None) -> list[Any]:
    if asr is not None:
        payload = json.loads(asr.read_text(encoding="utf-8"))
        return parse_transcript(payload.get("text") or payload["transcript"])
    assert asr_dir is not None
    combined = []
    for chunk in sorted(asr_dir.glob("audio-*.json")):
        offset = int(chunk.stem.rsplit("-", 1)[1]) * 60.0
        payload = json.loads(chunk.read_text(encoding="utf-8"))
        for segment in parse_transcript(payload["text"]):
            combined.append(
                type(segment)(
                    start=segment.start + offset,
                    end=segment.end + offset,
                    speaker=segment.speaker,
                    text=segment.text,
                )
            )
    return combined


if __name__ == "__main__":
    raise SystemExit(main())
