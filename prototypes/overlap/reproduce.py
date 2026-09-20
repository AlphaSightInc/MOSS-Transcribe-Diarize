"""Reproduce R4-6 word edits from retained transcript layers.

One command:
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python prototypes/overlap/reproduce.py \
  --reference evidence/round4/overlap/bill-reference-source.jsonl \
  --published evidence/round4/overlap/s17-demo-overlap-published.json \
  --lane system --expect 13,2,6,5

The scorer is the production ``lane_word_oracle.distance`` scorer.  This
prototype adds only a deterministic backtrace so each edit can be inspected.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from moss_transcribe_diarize.lane_word_oracle import distance, words


Score = tuple[int, int, int, int]


def _add(score: Score, operation: str) -> Score:
    total, substitutions, omissions, additions = score
    if operation == "substitution":
        substitutions += 1
    elif operation == "omission":
        omissions += 1
    elif operation == "addition":
        additions += 1
    else:  # pragma: no cover - prototype-internal contract
        raise ValueError(operation)
    return total + 1, substitutions, omissions, additions


def align(reference: list[str], hypothesis: list[str]) -> tuple[Score, list[dict[str, Any]]]:
    """Return the production score tuple and one stable minimum-cost backtrace."""
    scores: list[list[Score]] = [[(0, 0, 0, 0)] * (len(hypothesis) + 1)
                                 for _ in range(len(reference) + 1)]
    parents: list[list[tuple[int, int, str] | None]] = [
        [None] * (len(hypothesis) + 1) for _ in range(len(reference) + 1)
    ]
    for i in range(1, len(reference) + 1):
        scores[i][0] = (i, 0, i, 0)
        parents[i][0] = (i - 1, 0, "omission")
    for j in range(1, len(hypothesis) + 1):
        scores[0][j] = (j, 0, 0, j)
        parents[0][j] = (0, j - 1, "addition")

    for i, reference_word in enumerate(reference, 1):
        for j, hypothesis_word in enumerate(hypothesis, 1):
            if reference_word == hypothesis_word:
                scores[i][j] = scores[i - 1][j - 1]
                parents[i][j] = (i - 1, j - 1, "match")
                continue
            candidates = (
                (_add(scores[i - 1][j - 1], "substitution"), i - 1, j - 1, "substitution"),
                (_add(scores[i - 1][j], "omission"), i - 1, j, "omission"),
                (_add(scores[i][j - 1], "addition"), i, j - 1, "addition"),
            )
            chosen = min(candidates, key=lambda item: item[0])
            scores[i][j] = chosen[0]
            parents[i][j] = chosen[1:]

    operations: list[dict[str, Any]] = []
    i, j = len(reference), len(hypothesis)
    while i or j:
        parent = parents[i][j]
        if parent is None:  # pragma: no cover - impossible for a non-origin cell
            raise AssertionError((i, j))
        previous_i, previous_j, operation = parent
        operations.append(
            {
                "operation": operation,
                "reference_index": i - 1 if i != previous_i else None,
                "hypothesis_index": j - 1 if j != previous_j else None,
                "reference_word": reference[i - 1] if i != previous_i else None,
                "hypothesis_word": hypothesis[j - 1] if j != previous_j else None,
            }
        )
        i, j = previous_i, previous_j
    operations.reverse()
    return scores[-1][-1], operations


def _reference(path: Path) -> tuple[dict[str, Any], list[str]]:
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if len(records) != 1:
        raise ValueError(f"expected exactly one retained reference record, got {len(records)}")
    record = records[0]
    return record, words(record["text"])


def _hypothesis(path: Path, lane: str) -> list[str]:
    document = json.loads(path.read_text())
    if isinstance(document, dict):
        segments = document.get("segments") or document.get("parsed_segments") or document
    else:
        segments = document
    return words(" ".join(
        str(segment.get("text", ""))
        for segment in segments
        if segment.get("source_lane", lane) == lane
    ))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--published", type=Path, required=True)
    parser.add_argument("--lane", choices=("system", "microphone"), required=True)
    parser.add_argument("--expect", help="total,substitutions,omissions,additions")
    args = parser.parse_args()

    record, reference = _reference(args.reference)
    hypothesis = _hypothesis(args.published, args.lane)
    score, operations = align(reference, hypothesis)
    production = distance(reference, hypothesis)
    expected_score = (
        production["substitutions"] + production["omissions"] + production["additions"],
        production["substitutions"],
        production["omissions"],
        production["additions"],
    )
    if score != expected_score:
        raise AssertionError({"backtrace": score, "production": expected_score})
    if args.expect and score != tuple(int(value) for value in args.expect.split(",")):
        raise AssertionError({"actual": score, "expected": args.expect})

    interval = {"start": record["start"], "end": record["end"], "granularity": "record"}
    edits = []
    for operation in operations:
        if operation["operation"] == "match":
            continue
        edits.append({**operation, "reference_interval": interval})
    result = {
        "schema": "moss-r4-6-alignment.v1",
        "reference": str(args.reference),
        "published": str(args.published),
        "lane": args.lane,
        "reference_interval": interval,
        "score": production,
        "edits": edits,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
