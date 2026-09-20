"""Qualification-only source-word visibility measurement.

This module consumes content-bearing observations but emits only the caller's
requested receipt. Product code does not import it and it defines no latency bar.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from moss_transcribe_diarize.lane_word_oracle import distance, words


@dataclass(frozen=True, slots=True)
class ReferenceWord:
    id: str
    text: str
    source_end_sec: float
    source_start_sec: float = 0.0
    source_interval_id: str | None = None

    def __post_init__(self) -> None:
        normalized = words(self.text)
        if not self.id or len(normalized) != 1 or normalized[0] != self.text:
            raise ValueError("reference words require a unique id and one normalized token")
        if self.source_interval_id is not None and not self.source_interval_id:
            raise ValueError("reference source_interval_id must be non-empty when present")
        if not math.isfinite(self.source_end_sec) or self.source_end_sec < 0:
            raise ValueError("reference source_end_sec must be finite and non-negative")
        if (
            not math.isfinite(self.source_start_sec)
            or self.source_start_sec < 0
            or self.source_start_sec >= self.source_end_sec
        ):
            raise ValueError("reference source interval must have positive duration")


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    source_start_sec: float
    source_end_sec: float
    text: str

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.source_start_sec)
            or not math.isfinite(self.source_end_sec)
            or self.source_start_sec < 0
            or self.source_start_sec >= self.source_end_sec
        ):
            raise ValueError("transcript segment source interval must have positive duration")


@dataclass(frozen=True, slots=True)
class TranscriptObservation:
    elapsed_sec: float
    segments: tuple[TranscriptSegment, ...]

    def __post_init__(self) -> None:
        if not math.isfinite(self.elapsed_sec) or self.elapsed_sec < 0:
            raise ValueError("observation elapsed_sec must be finite and non-negative")
        if any(
            later.source_start_sec < earlier.source_start_sec
            for earlier, later in zip(self.segments, self.segments[1:])
        ):
            raise ValueError("transcript segments must be source ordered")


def reference_words_from_intervals(
    intervals: Iterable[Mapping[str, object]],
) -> tuple[ReferenceWord, ...]:
    """Expand source-authored intervals without inventing per-word timestamps."""

    result: list[ReferenceWord] = []
    seen: set[str] = set()
    for interval in intervals:
        interval_id = interval.get("id")
        text = interval.get("text")
        start = interval.get("start")
        end = interval.get("end")
        if not isinstance(interval_id, str) or not isinstance(text, str):
            raise ValueError("each source interval requires string id and text")
        if (
            not isinstance(start, (int, float))
            or isinstance(start, bool)
            or not isinstance(end, (int, float))
            or isinstance(end, bool)
        ):
            raise ValueError("each source interval requires numeric start and end")
        for index, token in enumerate(words(text)):
            word_id = f"{interval_id}:{index}"
            if word_id in seen:
                raise ValueError(f"duplicate reference word id: {word_id}")
            seen.add(word_id)
            result.append(
                ReferenceWord(
                    word_id,
                    token,
                    float(end),
                    float(start),
                    source_interval_id=interval_id,
                )
            )
    if not result:
        raise ValueError("reference population must contain at least one word")
    return tuple(result)


def _overlaps(reference: ReferenceWord, observed: TranscriptSegment) -> bool:
    return (
        observed.source_start_sec < reference.source_end_sec
        and observed.source_end_sec > reference.source_start_sec
    )


def _observed_words(
    observation: TranscriptObservation,
) -> list[tuple[str, TranscriptSegment]]:
    return [
        (token, segment)
        for segment in observation.segments
        for token in words(segment.text)
    ]


def _ordered_statuses(
    reference: Sequence[ReferenceWord],
    hypothesis: Sequence[tuple[str, TranscriptSegment]],
) -> list[str]:
    """Return exact ordered-Levenshtein status for every reference occurrence."""

    width = len(hypothesis) + 1
    back = bytearray((len(reference) + 1) * width)
    previous = [(j, 0, 0, j) for j in range(width)]
    for j in range(1, width):
        back[j] = 3  # hypothesis addition
    for i, expected in enumerate(reference, 1):
        current = [(i, 0, i, 0)]
        back[i * width] = 2  # reference deletion
        for j, (observed, segment) in enumerate(hypothesis, 1):
            if expected.text == observed and _overlaps(expected, segment):
                current.append(previous[j - 1])
                back[i * width + j] = 0
                continue
            candidates: list[tuple[tuple[int, int, int, int], int]] = []
            for cell, operation in (
                (previous[j - 1], 1),
                (previous[j], 2),
                (current[j - 1], 3),
            ):
                value = list(cell)
                value[0] += 1
                value[operation] += 1
                candidates.append((tuple(value), operation))
            score, operation = min(candidates, key=lambda candidate: candidate[0])
            current.append(score)
            back[i * width + j] = operation
        previous = current

    statuses = ["missing"] * len(reference)
    i, j = len(reference), len(hypothesis)
    while i or j:
        operation = back[i * width + j]
        if operation == 0:
            statuses[i - 1] = "correct"
            i -= 1
            j -= 1
        elif operation == 1:
            statuses[i - 1] = "wrong"
            i -= 1
            j -= 1
        elif operation == 2:
            statuses[i - 1] = "missing"
            i -= 1
        else:
            j -= 1
    return statuses


def evaluate_visible_word_stream(
    references: Sequence[ReferenceWord],
    observations: Sequence[TranscriptObservation],
    *,
    clock_name: str,
) -> dict[str, Any]:
    if not references or not observations:
        raise ValueError("visible-word evidence requires references and observations")
    if len({reference.id for reference in references}) != len(references):
        raise ValueError("reference word ids must be unique")
    if not clock_name:
        raise ValueError("clock_name must be non-empty")
    if any(
        later.elapsed_sec < earlier.elapsed_sec
        for earlier, later in zip(observations, observations[1:])
    ):
        raise ValueError("observations must be monotonic")

    observed = [_observed_words(observation) for observation in observations]
    states = []
    for observation, tokens in zip(observations, observed):
        statuses = _ordered_statuses(references, tokens)
        states.append(
            [
                "missing"
                if observation.elapsed_sec < reference.source_end_sec
                else status
                for reference, status in zip(references, statuses)
            ]
        )
    word_rows = []
    for index, reference in enumerate(references):
        history = [state[index] for state in states]
        final_status = history[-1]
        first_index = next(
            (position for position, status in enumerate(history) if status == "correct"),
            None,
        ) if final_status == "correct" else None
        stable_index = next(
            (
                position
                for position, status in enumerate(history)
                if status == "correct"
                and all(later == "correct" for later in history[position:])
            ),
            None,
        )
        first_sec = observations[first_index].elapsed_sec if first_index is not None else None
        stable_sec = observations[stable_index].elapsed_sec if stable_index is not None else None
        word_rows.append(
            {
                "reference_word_id": reference.id,
                "source_start_sec": reference.source_start_sec,
                "source_end_sec": reference.source_end_sec,
                "final_status": final_status,
                "final_wrong": final_status == "wrong",
                "final_missing": final_status == "missing",
                "first_correct_sec": first_sec,
                "stable_correct_sec": stable_sec,
            }
        )
    final_observed = [token for token, _ in observed[-1]]
    result = {
        "schema": "moss-visible-words.v2",
        "clock": clock_name,
        "full_denominator": len(references),
        "observation_count": len(observations),
        "final_correct": sum(row["final_status"] == "correct" for row in word_rows),
        "final_wrong": sum(row["final_wrong"] for row in word_rows),
        "final_missing": sum(row["final_missing"] for row in word_rows),
        "ordered_word_score": distance(
            [reference.text for reference in references], final_observed
        ),
        "words": word_rows,
        "phrase_end_diagnostics": _phrase_end_diagnostics(
            references, states, observations
        ),
    }
    return result


def _phrase_end_diagnostics(
    references: Sequence[ReferenceWord],
    states: Sequence[Sequence[str]],
    observations: Sequence[TranscriptObservation],
) -> dict[str, object]:
    groups: list[tuple[str, list[int]]] = []
    group_by_id: dict[str, list[int]] = {}
    for index, reference in enumerate(references):
        interval_id = reference.source_interval_id or reference.id
        indexes = group_by_id.get(interval_id)
        if indexes is None:
            indexes = []
            group_by_id[interval_id] = indexes
            groups.append((interval_id, indexes))
        elif groups[-1][0] != interval_id:
            raise ValueError("reference source intervals must be contiguous")
        indexes.append(index)

    phrase_rows = []
    for interval_id, indexes in groups:
        first_reference = references[indexes[0]]
        if any(
            reference.source_start_sec != first_reference.source_start_sec
            or reference.source_end_sec != first_reference.source_end_sec
            for reference in (references[index] for index in indexes[1:])
        ):
            raise ValueError("words in a reference source interval must share its span")
        history = [
            all(state[index] == "correct" for index in indexes) for state in states
        ]
        final_complete = history[-1]
        first_index = (
            next((index for index, complete in enumerate(history) if complete), None)
            if final_complete
            else None
        )
        stable_index = next(
            (
                index
                for index, complete in enumerate(history)
                if complete and all(history[index:])
            ),
            None,
        )
        first_sec = observations[first_index].elapsed_sec if first_index is not None else None
        stable_sec = observations[stable_index].elapsed_sec if stable_index is not None else None
        phrase_rows.append(
            {
                "reference_interval_id": interval_id,
                "source_start_sec": first_reference.source_start_sec,
                "source_end_sec": first_reference.source_end_sec,
                "word_count": len(indexes),
                "final_complete": final_complete,
                "first_complete_sec": first_sec,
                "first_complete_delay_sec": (
                    None
                    if first_sec is None
                    else first_sec - first_reference.source_end_sec
                ),
                "stable_complete_sec": stable_sec,
                "stable_complete_delay_sec": (
                    None
                    if stable_sec is None
                    else stable_sec - first_reference.source_end_sec
                ),
            }
        )
    return {
        "basis": "source-interval end; not per-word latency",
        "full_denominator": len(phrase_rows),
        "phrases": phrase_rows,
        "first_complete_distribution": _latency_distribution(
            phrase_rows, "first_complete_delay_sec"
        ),
        "stable_complete_distribution": _latency_distribution(
            phrase_rows, "stable_complete_delay_sec"
        ),
    }


def _type7(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _latency_distribution(rows: Sequence[Mapping[str, object]], field: str) -> dict[str, object]:
    values = [float(row[field]) for row in rows if isinstance(row.get(field), (int, float))]
    complete = len(values) == len(rows)
    return {
        "full_denominator": len(rows),
        "finite_count": len(values),
        "null_count": len(rows) - len(values),
        "population_p50_sec": _type7(values, 0.5) if complete else None,
        "population_p95_sec": _type7(values, 0.95) if complete else None,
        "finite_only": (
            None
            if not values
            else {
                "minimum_sec": min(values),
                "p50_sec": _type7(values, 0.5),
                "p95_sec": _type7(values, 0.95),
                "maximum_sec": max(values),
            }
        ),
    }


def evaluate_visible_word_surfaces(
    references: Sequence[ReferenceWord],
    *,
    api_observations: Sequence[TranscriptObservation],
    rendered_observations: Sequence[TranscriptObservation],
    rendered_unmeasured_reason: str | None = None,
    decoder_queue_clocks: Sequence[Mapping[str, object]] = (),
) -> dict[str, Any]:
    """Keep browser/API observations and server clocks as separate projections."""

    rendered: dict[str, Any]
    if rendered_unmeasured_reason is None:
        rendered = evaluate_visible_word_stream(
            references, rendered_observations, clock_name="rendered_dom"
        )
    else:
        rendered = {
            "status": "UNMEASURED",
            "reason": rendered_unmeasured_reason,
            "full_denominator": len(references),
        }
    return {
        "schema": "moss-visible-word-surfaces.v2",
        "full_denominator": len(references),
        "api": evaluate_visible_word_stream(
            references, api_observations, clock_name="api_arrival"
        ),
        "rendered_dom": rendered,
        "decoder_queue_clocks": [dict(row) for row in decoder_queue_clocks],
        "clock_relation": "separate; no cross-clock subtraction",
    }


def require_visible_word_evidence(result: Mapping[str, object]) -> None:
    rows = result.get("words")
    denominator = result.get("full_denominator")
    if (
        not isinstance(rows, list)
        or not isinstance(denominator, int)
        or isinstance(denominator, bool)
        or denominator <= 0
        or len(rows) != denominator
        or any(not isinstance(row, dict) or "reference_word_id" not in row for row in rows)
    ):
        raise ValueError(
            "visible-word evidence requires an ordered reference-word denominator"
        )


def visible_word_percentile(
    result: Mapping[str, object], *, field: str, quantile: float
) -> float:
    """Return a percentile only when every reference word has a finite value."""

    require_visible_word_evidence(result)
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between zero and one")
    rows = result["words"]
    assert isinstance(rows, list)
    values = [row.get(field) for row in rows]
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        for value in values
    ):
        raise ValueError("percentile requires finite values for the full denominator")
    return _type7([float(value) for value in values], quantile)


def _observations(rows: object) -> tuple[TranscriptObservation, ...]:
    if not isinstance(rows, list):
        raise ValueError("observations must be a list")
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("segments"), list):
            raise ValueError("each observation requires source-timed segments")
        result.append(
            TranscriptObservation(
                float(row["elapsed_sec"]),
                tuple(
                    TranscriptSegment(
                        float(segment["start"]),
                        float(segment["end"]),
                        str(segment["text"]),
                    )
                    for segment in row["segments"]
                ),
            )
        )
    return tuple(result)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = json.loads(args.input.read_text())
    intervals = payload.get("reference_intervals")
    if not isinstance(intervals, list):
        parser.error("input requires reference_intervals")
    result = evaluate_visible_word_surfaces(
        reference_words_from_intervals(intervals),
        api_observations=_observations(payload.get("api_observations")),
        rendered_observations=_observations(payload.get("rendered_observations")),
        decoder_queue_clocks=payload.get("decoder_queue_clocks", ()),
    )
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ReferenceWord",
    "TranscriptSegment",
    "TranscriptObservation",
    "evaluate_visible_word_stream",
    "evaluate_visible_word_surfaces",
    "reference_words_from_intervals",
    "require_visible_word_evidence",
    "visible_word_percentile",
]
