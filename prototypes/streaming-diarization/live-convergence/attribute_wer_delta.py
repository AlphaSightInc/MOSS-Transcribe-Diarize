"""Attribute a live-WER delta to individual published segments, by re-scoring without them.

The preregistered M1 protocol says a per-case delta is attributed *before* it is called a
regression or an improvement. Arithmetic that merely lines up is not attribution; this
re-scores the real hypothesis with a named segment withheld, on the same scorer the drivers
use, so each segment's WER cost is measured.

  python attribute_wer_delta.py <hypothesis.jsonl> --case lex_bill_ackman \
      [--drop-start 49.75 --drop-end 50.0] ...

Prints the scored WER of the full hypothesis and of the hypothesis with each named segment
withheld. Exit 0 always -- this is a measurement, not a gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.evaluation import Segment, calculate_tbsa  # noqa: E402

SAMPLES = REPO / "prototypes/streaming-diarization/data/real/benchmark_diarization_1min/samples"


def load(path: Path) -> list[Segment]:
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out.append(
            Segment(
                start=float(row["start"]),
                end=float(row["end"]),
                speaker=str(row["speaker"]),
                text=str(row.get("text") or ""),
            )
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("hypothesis", type=Path)
    parser.add_argument("--case", required=True)
    parser.add_argument(
        "--drop",
        action="append",
        default=[],
        metavar="START:END",
        help="withhold the segment starting at START and ending at END (seconds), repeatable",
    )
    args = parser.parse_args()

    reference = load(SAMPLES / args.case / "reference.jsonl")
    hypothesis = load(args.hypothesis)
    full = calculate_tbsa(reference, hypothesis)
    print(f"case            {args.case}")
    print(f"hypothesis      {args.hypothesis}  ({len(hypothesis)} segments)")
    print(f"full WER        {full['wer']:.6f}")

    for spec in args.drop:
        start_s, end_s = (float(x) for x in spec.split(":"))
        kept = [s for s in hypothesis if not (abs(s.start - start_s) < 0.02 and abs(s.end - end_s) < 0.02)]
        dropped = [s for s in hypothesis if s not in kept]
        if not dropped:
            print(f"  drop {spec}: NO SEGMENT MATCHED")
            continue
        scored = calculate_tbsa(reference, kept)
        for seg in dropped:
            print(f"  withheld [{seg.start:.2f},{seg.end:.2f}] {seg.speaker} {seg.text!r}")
        print(
            f"  WER without it  {scored['wer']:.6f}   "
            f"(this segment is worth {full['wer'] - scored['wer']:+.6f})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
