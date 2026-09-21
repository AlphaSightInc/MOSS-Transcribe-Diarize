"""THROWAWAY: extract the retained 180 s S9 source rows and word-end template.

One command:
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \\
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \\
  prototypes/headed-session/prepare_s9_reference.py \\
  --source /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/interview_adam_frank_180s/reference.jsonl \\
  --output-dir evidence/round4/headed-session

This makes a human-work template. It does not infer any word time and it does not
read, play, or modify audio.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from tools.qualify.visible_words import reference_words_from_intervals


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    source_rows = [json.loads(line) for line in args.source.read_text().splitlines() if line]
    if not source_rows or float(source_rows[-1]["end"]) != 180.0:
        raise ValueError("S9 source must be the complete retained 180-second reference")
    intervals = []
    speakers: dict[str, str] = {}
    for index, row in enumerate(source_rows):
        source_id = f"adam-180-{index:02d}"
        intervals.append({
            "id": source_id,
            "text": str(row["text"]),
            "start": float(row["start"]),
            "end": float(row["end"]),
        })
        speakers[source_id] = str(row["speaker"])
    words = reference_words_from_intervals(intervals)
    template = [
        {
            "id": word.id,
            "source_interval_id": word.source_interval_id,
            "speaker": speakers[word.source_interval_id],
            "text": word.text,
            "phrase_start_sec": word.source_start_sec,
            "phrase_end_sec": word.source_end_sec,
            "word_end_sec": None,
            "alignment_status": "UNCONFIRMED",
        }
        for word in words
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(args.output_dir / "s9-adam-frank-180s-source-rows.jsonl", source_rows)
    _write_jsonl(args.output_dir / "s9-adam-frank-180s-word-end-template.jsonl", template)
    print(json.dumps({
        "clip": "interview_adam_frank_180s",
        "seconds": 180,
        "source_rows": len(source_rows),
        "word_rows": len(template),
        "unconfirmed_word_ends": sum(row["word_end_sec"] is None for row in template),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
