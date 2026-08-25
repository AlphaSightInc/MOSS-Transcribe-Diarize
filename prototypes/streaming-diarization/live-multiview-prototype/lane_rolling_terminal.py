"""THROWAWAY LOGIC PROTOTYPE: rolling10 and terminal150 transcript revision.

Question: can a 10-second staggered MOSS witness or terminal 150/120-second
MOSS pass replace short provisional spans without using golden truth to merge?

One-command state demo:
    .venv/bin/python prototypes/streaming-diarization/live-multiview-prototype/lane_rolling_terminal.py

The integrated benchmark supplies real DecodeObservation objects.  This module
only plans views, reconciles already-decoded results, and measures them.  It
never calls a model or a service.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from statistics import mean
from typing import Iterable, Mapping, Sequence

from moss_transcribe_diarize.evaluation import (
    Segment as EvaluationSegment,
    calculate_diarization,
    calculate_tbsa,
)


@dataclass(frozen=True, slots=True)
class Segment:
    start: float
    end: float
    speaker: str
    text: str

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class ViewPlan:
    arm: str
    index: int
    start: float
    end: float
    own_start: float
    own_end: float
    eligible_at: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class DecodeObservation:
    """One real decoder result; segment times are relative to its view."""

    plan: ViewPlan
    segments: tuple[Segment, ...]
    decode_started_at: float
    published_at: float
    gpu_elapsed_sec: float


@dataclass(frozen=True, slots=True)
class RevisionEvent:
    arm: str
    view_index: int
    changed: bool
    owned_start: float
    owned_end: float
    published_at: float
    correction_latency_from_audio_start: float
    processing_lag_after_view_end: float
    replaced_segments: int
    replacement_segments: int


def plan_rolling10(
    duration_sec: float,
    *,
    window_sec: float = 10.0,
    stride_sec: float = 5.0,
) -> tuple[ViewPlan, ...]:
    """Plan complete online views; stagger is explicit in ``stride_sec``.

    No short tail is decoded: terminal150 owns meeting-end cleanup.  A 60-second
    meeting therefore produces 11 views: 0-10, 5-15, ..., 50-60.
    """

    starts: list[float] = []
    cursor = 0.0
    while cursor + window_sec <= duration_sec + 1e-9:
        starts.append(cursor)
        cursor += stride_sec
    raw = [(start, min(start + window_sec, duration_sec)) for start in starts]
    return _owned_plans("rolling10", raw)


def plan_terminal150(
    duration_sec: float,
    *,
    window_sec: float = 150.0,
    stride_sec: float = 120.0,
) -> tuple[ViewPlan, ...]:
    """Mirror production file-mode 150-second windows / 120-second stride."""

    starts: list[float] = []
    cursor = 0.0
    while cursor < duration_sec:
        starts.append(cursor)
        cursor += stride_sec
    raw = [(start, min(start + window_sec, duration_sec)) for start in starts]
    return _owned_plans("terminal150", raw, eligible_at=duration_sec)


def provisional_plan(index: int, start: float, end: float, *, arm: str) -> ViewPlan:
    """Plan one non-overlapping 1.0- or 2.5-second provisional request."""

    return ViewPlan(arm, index, start, end, start, end, end)


def compose_provisional(observations: Sequence[DecodeObservation]) -> tuple[Segment, ...]:
    """Concatenate already identity-resolved short-span hypotheses."""

    output = [segment for observation in observations for segment in absolute_segments(observation)]
    return tuple(sorted(output, key=_segment_key))


def absolute_segments(observation: DecodeObservation) -> tuple[Segment, ...]:
    return tuple(
        Segment(
            start=observation.plan.start + segment.start,
            end=observation.plan.start + segment.end,
            speaker=segment.speaker,
            text=segment.text,
        )
        for segment in observation.segments
    )


def apply_witnesses(
    base: Sequence[Segment],
    observations: Sequence[DecodeObservation],
) -> tuple[tuple[Segment, ...], tuple[RevisionEvent, ...]]:
    """Replace owned regions using only hypotheses, timing, and overlap.

    Golden reference is deliberately absent from this signature.  Local speaker
    names are mapped to existing hypothesis speakers by maximum duration overlap;
    unmatched voices receive content-order names independent of ``S00`` spelling.
    """

    current = tuple(sorted(base, key=_segment_key))
    events: list[RevisionEvent] = []
    for observation in sorted(observations, key=lambda item: (item.published_at, item.plan.index)):
        candidate = absolute_segments(observation)
        mapped = _map_candidate_speakers(candidate, current, observation.plan)
        # MOSS timestamps whole speaker turns, not individual words.  Keeping a whole
        # turn merely because its midpoint is owned duplicates boundary words when the
        # adjacent staggered view times that turn differently.  Split a turn's tokens
        # uniformly over its own reported interval, then own/subtract the same token
        # units on both sides.  This is truth-blind and preserves every outside token.
        old_owned = _owned_pieces(current, observation.plan)
        new_owned = _owned_pieces(mapped, observation.plan)
        changed = _semantic_signature(old_owned) != _semantic_signature(new_owned)
        current = tuple(
            sorted(
                list(_outside_pieces(current, observation.plan)) + list(new_owned),
                key=_segment_key,
            )
        )
        events.append(
            RevisionEvent(
                arm=observation.plan.arm,
                view_index=observation.plan.index,
                changed=changed,
                owned_start=observation.plan.own_start,
                owned_end=observation.plan.own_end,
                published_at=observation.published_at,
                correction_latency_from_audio_start=max(
                    0.0, observation.published_at - observation.plan.own_start
                ),
                processing_lag_after_view_end=max(
                    0.0, observation.published_at - observation.plan.end
                ),
                replaced_segments=len(old_owned),
                replacement_segments=len(new_owned),
            )
        )
    return current, tuple(events)


def compose_terminal(
    observations: Sequence[DecodeObservation],
) -> tuple[tuple[Segment, ...], tuple[RevisionEvent, ...]]:
    """Build a file-like canonical transcript, independent of provisional text."""

    return apply_witnesses((), observations)


def score(reference: Sequence[Segment], hypothesis: Sequence[Segment]) -> dict[str, float]:
    """Truth enters only here, after hypothesis-only reconciliation."""

    ref = tuple(_evaluation_segment(item) for item in reference)
    hyp = tuple(_evaluation_segment(item) for item in hypothesis)
    tbsa = calculate_tbsa(ref, hyp)
    diarization = calculate_diarization(ref, hyp)
    return {
        "tbsa": float(tbsa["composite"]),
        "wer": float(tbsa["wer"]),
        "coverage": float(tbsa["text_coverage"]),
        "text_speaker_accuracy": float(tbsa["text_speaker_accuracy"]),
        "der": float(diarization["der"]),
        "miss": float(diarization["miss"]),
        "false_alarm": float(diarization["false_alarm"]),
        "speaker_confusion": float(diarization["speaker_confusion"]),
    }


def measure_arm(
    *,
    duration_sec: float,
    reference: Sequence[Segment],
    provisional: Sequence[DecodeObservation],
    rolling10: Sequence[DecodeObservation] = (),
    terminal150: Sequence[DecodeObservation] = (),
) -> dict[str, object]:
    """Return comparable quality, latency, GPU RTF, and work measurements."""

    current = compose_provisional(provisional)
    rolled, rolling_events = apply_witnesses(current, rolling10)
    terminal, _terminal_events = compose_terminal(terminal150) if terminal150 else ((), ())
    first_latencies = [_first_publication_latency(item) for item in provisional]
    correction_latencies = [
        item.correction_latency_from_audio_start for item in rolling_events if item.changed
    ]
    provisional_to_correction = _provisional_to_correction_latencies(
        provisional,
        rolling_events,
    )
    report: dict[str, object] = {
        "quality": {
            "current": score(reference, current),
            "rolling10": score(reference, rolled) if rolling10 else None,
            "terminal150": score(reference, terminal) if terminal150 else None,
        },
        "latency_sec": {
            "first_publication": _distribution(first_latencies),
            "rolling10_correction_from_audio_start": _distribution(correction_latencies),
            "rolling10_after_provisional_publication": _distribution(provisional_to_correction),
            "rolling10_processing_lag": _distribution(
                [item.processing_lag_after_view_end for item in rolling_events]
            ),
            "terminal_final_after_meeting": (
                max(item.published_at for item in terminal150) - duration_sec
                if terminal150
                else None
            ),
        },
        "gpu": {
            "current": _work(duration_sec, provisional),
            "rolling10_component": _work(duration_sec, rolling10),
            "terminal150_component": _work(duration_sec, terminal150),
            "current_plus_rolling10": _work(duration_sec, tuple(provisional) + tuple(rolling10)),
            "current_plus_terminal150": _work(duration_sec, tuple(provisional) + tuple(terminal150)),
            "current_plus_rolling10_plus_terminal150": _work(
                duration_sec,
                tuple(provisional) + tuple(rolling10) + tuple(terminal150),
            ),
        },
        "revisions": [asdict(item) for item in rolling_events],
    }
    return report


def measure_bases(
    *,
    duration_sec: float,
    reference: Sequence[Segment],
    provisional_bases: Mapping[str, Sequence[DecodeObservation]],
    rolling10: Sequence[DecodeObservation] = (),
    terminal150: Sequence[DecodeObservation] = (),
) -> dict[str, dict[str, object]]:
    """Score 1.0- and 2.5-second bases against the exact same witnesses."""

    return {
        name: measure_arm(
            duration_sec=duration_sec,
            reference=reference,
            provisional=observations,
            rolling10=rolling10,
            terminal150=terminal150,
        )
        for name, observations in provisional_bases.items()
    }


def _owned_plans(
    arm: str,
    raw: Sequence[tuple[float, float]],
    *,
    eligible_at: float | None = None,
) -> tuple[ViewPlan, ...]:
    plans: list[ViewPlan] = []
    for index, (start, end) in enumerate(raw):
        own_start = start if index == 0 else (start + raw[index - 1][1]) / 2.0
        own_end = end if index == len(raw) - 1 else (end + raw[index + 1][0]) / 2.0
        plans.append(
            ViewPlan(
                arm=arm,
                index=index,
                start=start,
                end=end,
                own_start=own_start,
                own_end=own_end,
                eligible_at=end if eligible_at is None else eligible_at,
            )
        )
    return tuple(plans)


def _map_candidate_speakers(
    candidate: Sequence[Segment],
    current: Sequence[Segment],
    plan: ViewPlan,
) -> tuple[Segment, ...]:
    candidate_labels = sorted(
        {item.speaker for item in candidate},
        key=lambda label: _speaker_evidence_key(candidate, label),
    )
    current_labels = sorted({item.speaker for item in current})
    weights = tuple(
        tuple(_speaker_overlap(candidate, local, current, canonical) for canonical in current_labels)
        for local in candidate_labels
    )
    matched_indexes = _maximum_positive_assignment(weights)
    mapping: dict[str, str] = {}
    fresh_ordinal = 0
    for row, label in enumerate(candidate_labels):
        column = matched_indexes[row]
        if column is not None:
            mapping[label] = current_labels[column]
        else:
            mapping[label] = f"{plan.arm}-v{plan.index}-n{fresh_ordinal}"
            fresh_ordinal += 1
    return tuple(
        Segment(item.start, item.end, mapping[item.speaker], item.text) for item in candidate
    )


def _maximum_positive_assignment(
    weights: tuple[tuple[float, ...], ...],
) -> tuple[int | None, ...]:
    if not weights:
        return ()
    column_count = len(weights[0])

    @lru_cache(maxsize=None)
    def solve(row: int, used: int) -> tuple[float, tuple[int | None, ...]]:
        if row == len(weights):
            return 0.0, ()
        best_score, tail = solve(row + 1, used)
        best = (best_score, (None,) + tail)
        for column in range(column_count):
            value = weights[row][column]
            if value <= 0.0 or used & (1 << column):
                continue
            tail_score, tail_choices = solve(row + 1, used | (1 << column))
            candidate_score = value + tail_score
            if candidate_score > best[0] + 1e-9:
                best = (candidate_score, (column,) + tail_choices)
        return best

    return solve(0, 0)[1]


def _speaker_overlap(
    candidate: Sequence[Segment],
    local: str,
    current: Sequence[Segment],
    canonical: str,
) -> float:
    return sum(
        max(0.0, min(left.end, right.end) - max(left.start, right.start))
        for left in candidate
        if left.speaker == local
        for right in current
        if right.speaker == canonical
    )


def _speaker_evidence_key(segments: Sequence[Segment], label: str) -> tuple[object, ...]:
    owned = [item for item in segments if item.speaker == label]
    return (
        min(item.start for item in owned),
        -sum(item.duration for item in owned),
        tuple((item.start, item.end, item.text) for item in owned),
    )


def _owned_pieces(segments: Sequence[Segment], plan: ViewPlan) -> tuple[Segment, ...]:
    return _select_token_pieces(segments, plan, owned=True)


def _outside_pieces(segments: Sequence[Segment], plan: ViewPlan) -> tuple[Segment, ...]:
    return _select_token_pieces(segments, plan, owned=False)


def _select_token_pieces(
    segments: Sequence[Segment],
    plan: ViewPlan,
    *,
    owned: bool,
) -> tuple[Segment, ...]:
    output: list[Segment] = []
    for segment in segments:
        tokens = segment.text.split()
        if not tokens or segment.duration <= 0.0:
            continue
        step = segment.duration / len(tokens)
        selected: list[tuple[str, float, float]] = []
        for index, token in enumerate(tokens):
            start = segment.start + index * step
            end = segment.start + (index + 1) * step
            midpoint = (start + end) / 2.0
            is_owned = plan.own_start <= midpoint < plan.own_end
            if is_owned == owned:
                selected.append((token, start, end))
            elif selected:
                output.append(
                    Segment(
                        selected[0][1],
                        selected[-1][2],
                        segment.speaker,
                        " ".join(item[0] for item in selected),
                    )
                )
                selected = []
        if selected:
            output.append(
                Segment(
                    selected[0][1],
                    selected[-1][2],
                    segment.speaker,
                    " ".join(item[0] for item in selected),
                )
            )
    return tuple(output)


def _semantic_signature(segments: Sequence[Segment]) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (round(item.start, 3), round(item.end, 3), item.speaker, " ".join(item.text.split()))
        for item in sorted(segments, key=_segment_key)
    )


def _first_publication_latency(observation: DecodeObservation) -> float:
    absolute = absolute_segments(observation)
    speech_start = min((item.start for item in absolute), default=observation.plan.start)
    return max(0.0, observation.published_at - speech_start)


def _provisional_to_correction_latencies(
    provisional: Sequence[DecodeObservation],
    revisions: Sequence[RevisionEvent],
) -> list[float]:
    """How long provisional chunks remain visible before a changed witness lands."""

    waits: list[float] = []
    for revision in revisions:
        if not revision.changed:
            continue
        for observation in provisional:
            midpoint = (observation.plan.start + observation.plan.end) / 2.0
            if revision.owned_start <= midpoint <= revision.owned_end + 1e-9:
                waits.append(max(0.0, revision.published_at - observation.published_at))
    return waits


def _work(duration_sec: float, observations: Sequence[DecodeObservation]) -> dict[str, float | int | None]:
    decoded_audio_sec = sum(item.plan.duration for item in observations)
    gpu_sec = sum(item.gpu_elapsed_sec for item in observations)
    return {
        "request_count": len(observations),
        "decoded_audio_sec": round(decoded_audio_sec, 6),
        "gpu_elapsed_sec": round(gpu_sec, 6),
        "decoder_rtf": round(gpu_sec / decoded_audio_sec, 6) if decoded_audio_sec else None,
        "gpu_load_rtf": round(gpu_sec / duration_sec, 6) if duration_sec else None,
        "audio_work_multiplier": round(decoded_audio_sec / duration_sec, 6) if duration_sec else None,
    }


def _distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "mean": round(mean(ordered), 6) if ordered else None,
        "p50": round(_percentile(ordered, 0.50), 6) if ordered else None,
        "p95": round(_percentile(ordered, 0.95), 6) if ordered else None,
        "max": round(ordered[-1], 6) if ordered else None,
    }


def _percentile(ordered: Sequence[float], quantile: float) -> float:
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _evaluation_segment(item: Segment) -> EvaluationSegment:
    return EvaluationSegment(item.start, item.end, item.speaker, item.text)


def _segment_key(item: Segment) -> tuple[float, float, str, str]:
    return item.start, item.end, item.speaker, item.text


def _demo() -> dict[str, object]:
    duration = 12.0
    reference = (
        Segment(0.0, 5.0, "Alice", "we opened the New York office"),
        Segment(5.0, 10.0, "Bob", "yes after the merger"),
    )
    provisional = (
        DecodeObservation(
            provisional_plan(0, 0.0, 2.5, arm="base2.5"),
            (Segment(0.0, 2.5, "Alice", "we opened the new"),),
            2.5,
            2.7,
            0.2,
        ),
        DecodeObservation(
            provisional_plan(1, 2.5, 5.0, arm="base2.5"),
            (Segment(0.0, 2.5, "Alice", "office"),),
            5.0,
            5.2,
            0.2,
        ),
        DecodeObservation(
            provisional_plan(2, 5.0, 7.5, arm="base2.5"),
            (Segment(0.0, 2.5, "Alice", "yes after the"),),
            7.5,
            7.7,
            0.2,
        ),
        DecodeObservation(
            provisional_plan(3, 7.5, 10.0, arm="base2.5"),
            (Segment(0.0, 2.5, "Bob", "merger"),),
            10.0,
            10.2,
            0.2,
        ),
    )
    rolling_plan = plan_rolling10(duration)[0]
    rolling = (
        DecodeObservation(
            rolling_plan,
            (
                Segment(0.0, 5.0, "local-B", "we opened the New York office"),
                Segment(5.0, 10.0, "local-A", "yes after the merger"),
            ),
            10.0,
            10.8,
            0.8,
        ),
    )
    terminal_plan = plan_terminal150(duration)[0]
    terminal = (
        DecodeObservation(
            terminal_plan,
            (
                Segment(0.0, 5.0, "renamed-9", "we opened the New York office"),
                Segment(5.0, 10.0, "renamed-2", "yes after the merger"),
            ),
            12.0,
            13.0,
            1.0,
        ),
    )
    return {
        "prototype_question": (
            "Can rolling10 or terminal150 replace short provisional spans without truth-time merge?"
        ),
        "assumption": "logic prototype; real MOSS inference is supplied by the integrated runner",
        "rolling10_plan": [asdict(item) for item in plan_rolling10(60.0)],
        "terminal150_plan": [asdict(item) for item in plan_terminal150(310.0)],
        "measurement": measure_arm(
            duration_sec=duration,
            reference=reference,
            provisional=provisional,
            rolling10=rolling,
            terminal150=terminal,
        ),
        "verdict": "synthetic wiring only; real benchmark verdict remains unmeasured",
    }


if __name__ == "__main__":
    print(json.dumps(_demo(), indent=2, sort_keys=True))
