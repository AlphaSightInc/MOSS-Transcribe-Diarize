"""Falsify terminal overlap normalization with deterministic decoder-shaped segments.

One command, no service or GPU:

    PYTHONPATH=. .venv/bin/python prototypes/streaming-diarization/contained-interruption/probe.py

The candidate is intentionally local to this prototype. Production is imported only for the
baseline. Every input and output segment is printed so word loss cannot hide in a score.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Sequence

from moss_transcribe_diarize.app.live_transcript_convergence import resolve_segment_overlaps


Placed = tuple[str, int, int, str]


@dataclass(frozen=True, slots=True)
class CandidateResolution:
    segments: tuple[Placed, ...]
    merged: int
    dropped: int
    displaced_samples: int


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[\w']+", text.casefold()))


def _contains_words(container: tuple[str, ...], contained: tuple[str, ...]) -> bool:
    if not contained or len(contained) > len(container):
        return False
    width = len(contained)
    return any(container[index : index + width] == contained for index in range(len(container) - width + 1))


def _duplicate_content(left: str, right: str) -> bool:
    left_words = _tokens(left)
    right_words = _tokens(right)
    return _contains_words(left_words, right_words) or _contains_words(right_words, left_words)


def candidate(placed: Sequence[Placed]) -> CandidateResolution:
    """Merge same-track seams, suppress contained duplicates, retain concurrent speech."""

    out: list[Placed] = []
    merged = dropped = displaced = 0
    for item in sorted(placed, key=lambda value: (value[1], value[2])):
        speaker, start, end, text = item

        # Window seams can bridge an interruption, so find every overlapping segment from
        # this local track rather than looking only at the immediately previous segment.
        same = [
            index
            for index, prior in enumerate(out)
            if prior[0] == speaker and start < prior[2] and prior[1] < end
        ]
        if same:
            pieces = [out[index] for index in same] + [item]
            first = min(same)
            joined = (
                speaker,
                min(piece[1] for piece in pieces),
                max(piece[2] for piece in pieces),
                " ".join(piece[3] for piece in sorted(pieces, key=lambda value: (value[1], value[2]))),
            )
            for index in reversed(same):
                out.pop(index)
            out.insert(first, joined)
            merged += len(same)
            continue

        discard_new = False
        discard_old: list[int] = []
        for index, prior in enumerate(out):
            if speaker == prior[0] or start >= prior[2] or prior[1] >= end:
                continue
            prior_contains_new = prior[1] <= start and end <= prior[2]
            new_contains_prior = start <= prior[1] and prior[2] <= end
            if not (prior_contains_new or new_contains_prior) or not _duplicate_content(prior[3], text):
                continue
            if prior_contains_new:
                discard_new = True
                dropped += 1
                displaced += end - start
                break
            discard_old.append(index)
        if discard_new:
            continue
        for index in reversed(discard_old):
            prior = out.pop(index)
            dropped += 1
            displaced += prior[2] - prior[1]
        out.append(item)
        out.sort(key=lambda value: (value[1], value[2]))

    return CandidateResolution(tuple(out), merged, dropped, displaced)


CASES: dict[str, tuple[Placed, ...]] = {
    "contained_distinct_interruption": (
        ("A", 0, 200, "the outer speaker continues"),
        ("B", 50, 100, "excuse me"),
    ),
    "contained_cross_label_duplicate": (
        ("A", 0, 200, "material was gravitationally squeezed out"),
        ("B", 50, 100, "gravitationally squeezed"),
    ),
    "retained_same_track_seam": (
        ("S01", 2_099_040, 2_180_640, "when two stars passed by each other closely"),
        ("S01", 2_143_200, 2_185_920, "and then material was gravitationally squeezed out."),
    ),
    "partial_distinct_interruption": (
        ("A", 0, 160, "the outer speaker"),
        ("B", 120, 200, "brief interruption"),
    ),
    "clean_non_overlap": (("A", 0, 100, "one"), ("B", 100, 200, "two")),
}


def _words(segments: Sequence[Placed]) -> int:
    return sum(len(_tokens(segment[3])) for segment in segments)


def main() -> None:
    rows = {}
    for name, inputs in CASES.items():
        baseline = resolve_segment_overlaps(inputs)
        proposed = candidate(inputs)
        rows[name] = {
            "input": inputs,
            "input_words": _words(inputs),
            "current": asdict(baseline),
            "current_words": _words(baseline.segments),
            "candidate": asdict(proposed),
            "candidate_words": _words(proposed.segments),
        }

    assertions = {
        "distinct_contained_words_retained": rows["contained_distinct_interruption"]["candidate_words"]
        == rows["contained_distinct_interruption"]["input_words"],
        "cross_label_duplicate_suppressed": len(
            rows["contained_cross_label_duplicate"]["candidate"]["segments"]
        )
        == 1,
        "real_same_track_seam_unchanged": rows["retained_same_track_seam"]["candidate"]
        == rows["retained_same_track_seam"]["current"],
        "partial_distinct_words_retained": rows["partial_distinct_interruption"]["candidate_words"]
        == rows["partial_distinct_interruption"]["input_words"],
        "clean_case_unchanged": rows["clean_non_overlap"]["candidate"]["segments"]
        == rows["clean_non_overlap"]["input"],
    }
    print(json.dumps({"cases": rows, "assertions": assertions}, indent=2))
    if not all(assertions.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
