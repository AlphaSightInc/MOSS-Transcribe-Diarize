"""Turn a human-completed S9 word-end template into headed-instrument JSONL.

This is a custody check, not an aligner. It accepts only rows the human has marked
CONFIRMED, retains word IDs/text, and derives each word start from the phrase start
or preceding confirmed word end. It never invents a time.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Sequence


def _number(row: dict[str, object], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool):
        raise ValueError(f"{row.get('id', '<unknown>')}: {key} is not a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{row.get('id', '<unknown>')}: {key} is not a number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{row.get('id', '<unknown>')}: {key} is not finite")
    return result


def complete(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    if not rows:
        raise ValueError("completed template is empty")
    output: list[dict[str, object]] = []
    prior_end: dict[str, float] = {}
    for row in rows:
        identifier = row.get("id")
        source_id = row.get("source_interval_id")
        text = row.get("text")
        if not isinstance(identifier, str) or not isinstance(source_id, str) or not isinstance(text, str):
            raise ValueError("each row needs string id, source_interval_id, and text")
        if row.get("alignment_status") != "CONFIRMED":
            raise ValueError(f"{identifier}: alignment_status is not CONFIRMED")
        phrase_start = _number(row, "phrase_start_sec")
        phrase_end = _number(row, "phrase_end_sec")
        word_end = _number(row, "word_end_sec")
        if phrase_end < phrase_start or not phrase_start <= word_end <= phrase_end:
            raise ValueError(f"{identifier}: word end is outside its phrase bounds")
        start = prior_end.get(source_id, phrase_start)
        if word_end < start:
            raise ValueError(f"{identifier}: word end regresses within its phrase")
        output.append({"id": identifier, "text": text, "start": start, "end": word_end})
        prior_end[source_id] = word_end
    return output


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--completed-template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output must not already exist")
    rows = [json.loads(line) for line in args.completed_template.read_text().splitlines() if line]
    output = complete(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in output))
    print(json.dumps({"confirmed_words": len(output), "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
