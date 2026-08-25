"""THROWAWAY LOGIC PROTOTYPE: five-second seam witnesses.

Question: can a five-second MOSS view centered on a short-span seam replace
2.5-second or 1.0-second provisional output without consulting golden truth?

One-command state demo:
    .venv/bin/python prototypes/streaming-diarization/live-multiview-prototype/lane_seam5.py

The integrated runner supplies real, already-decoded MOSS observations. This
file plans requests, reconciles hypotheses, and measures results. It never calls
a model or service. Segment times are absolute unless a witness explicitly says
``timestamps: relative``.
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.evaluation import (  # noqa: E402
    Segment as EvaluationSegment,
    calculate_diarization,
    calculate_tbsa,
)


SEAM_WINDOW_SEC = 5.0


def build_seam5_windows(
    duration_sec: float,
    provisional_cap_sec: float,
) -> list[dict[str, float | int | str]]:
    """Plan full five-second views centered on real provisional seams.

    Edge seams without 2.5 seconds of context on both sides stay provisional.
    Each witness owns one provisional-cap-wide interval. Adjacent ownership
    intervals touch but do not overlap.
    """

    half_window = SEAM_WINDOW_SEC / 2.0
    windows: list[dict[str, float | int | str]] = []
    seam_index = 1
    while seam_index * provisional_cap_sec < duration_sec - 1e-9:
        seam = seam_index * provisional_cap_sec
        if seam >= half_window - 1e-9 and seam <= duration_sec - half_window + 1e-9:
            windows.append(
                {
                    "arm": "seam5",
                    "index": len(windows),
                    "seam": round(seam, 9),
                    "window_start": round(seam - half_window, 9),
                    "window_end": round(seam + half_window, 9),
                    "ownership_start": round(seam - provisional_cap_sec / 2.0, 9),
                    "ownership_end": round(seam + provisional_cap_sec / 2.0, 9),
                    "eligible_at": round(seam + half_window, 9),
                    "timestamps": "absolute",
                }
            )
        seam_index += 1
    return windows


def reconcile_seam5(
    provisional_segments: Sequence[Mapping[str, Any] | Any],
    witness_decodes: Sequence[Mapping[str, Any] | Any],
    *,
    provisional_cap_sec: float,
    duration_sec: float | None = None,
) -> dict[str, Any]:
    """Truth-blind seam replacement with a complete decision trace.

    A usable witness replaces only segments whose midpoint belongs to its
    seam-centered ownership interval. Empty ownership crops are skipped, so a
    bad witness cannot erase provisional text. Witness-local speaker names are
    first matched to the preceding overlapping witness, then to provisional
    speakers, using one-to-one maximum duration overlap. Remaining voices get
    stable fresh names.
    """

    provisional = [_segment_record(item, origin="provisional") for item in provisional_segments]
    current = sorted(provisional, key=_segment_key)
    witnesses = sorted(
        [_witness_record(item, provisional_cap_sec, duration_sec) for item in witness_decodes],
        key=lambda item: (item["window_start"], item["window_end"]),
    )
    fresh_ordinal = 1
    previous_full: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    first_publication_samples = [
        float(item["published_at"]) - float(item["end"])
        for item in provisional
        if item.get("published_at") is not None
    ]

    for witness_index, witness in enumerate(witnesses):
        absolute = _absolute_witness_segments(witness)
        mapped, mapping_state, fresh_ordinal = _map_speakers(
            absolute,
            previous_full,
            provisional,
            fresh_ordinal,
        )
        previous_full = mapped
        # A MOSS segment may cross the ownership boundary.  Whole-segment midpoint
        # selection duplicates words when adjacent views timestamp that turn
        # differently.  Approximate word times uniformly inside the reported segment,
        # then use the same truth-blind crop for the witness and provisional tape.
        owned = _select_token_pieces(
            mapped,
            witness["ownership_start"],
            witness["ownership_end"],
            owned=True,
        )
        removed = _select_token_pieces(
            current,
            witness["ownership_start"],
            witness["ownership_end"],
            owned=True,
        )
        usable = bool(owned) and witness.get("usable", True)
        before_signature = _semantic_signature(removed)
        after_signature = _semantic_signature(owned)
        changed = usable and before_signature != after_signature

        if usable:
            current = sorted(
                _select_token_pieces(
                    current,
                    witness["ownership_start"],
                    witness["ownership_end"],
                    owned=False,
                )
                + owned,
                key=_segment_key,
            )

        available_at = witness.get("available_at")
        published_times = [float(item["published_at"]) for item in removed if item.get("published_at") is not None]
        correction_after_last_publication = (
            max(0.0, float(available_at) - max(published_times))
            if changed and available_at is not None and published_times
            else None
        )
        canonical_after_audio = (
            float(available_at) - float(witness["ownership_end"])
            if usable and available_at is not None
            else None
        )
        decisions.append(
            {
                "witness_index": witness_index,
                "window": {
                    key: witness[key]
                    for key in (
                        "window_start",
                        "window_end",
                        "seam",
                        "ownership_start",
                        "ownership_end",
                        "available_at",
                        "decode_elapsed_sec",
                    )
                },
                "speaker_mapping": mapping_state,
                "absolute_witness_segments": [_public_segment(item) for item in absolute],
                "owned_witness_segments": [_public_segment(item) for item in owned],
                "removed_segments": [_public_segment(item) for item in removed],
                "action": "replace" if usable else "preserve_provisional_empty_crop",
                "visible_change": changed,
                "correction_after_last_provisional_publication_sec": correction_after_last_publication,
                "canonical_available_after_owned_audio_sec": canonical_after_audio,
                "state_after": [_public_segment(item) for item in current],
            }
        )

    changed_decisions = [item for item in decisions if item["visible_change"]]
    correction_samples = [
        float(item["correction_after_last_provisional_publication_sec"])
        for item in changed_decisions
        if item["correction_after_last_provisional_publication_sec"] is not None
    ]
    canonical_samples = [
        float(item["canonical_available_after_owned_audio_sec"])
        for item in decisions
        if item["canonical_available_after_owned_audio_sec"] is not None
    ]
    duration = duration_sec if duration_sec is not None else _inferred_duration(provisional, witnesses)
    return {
        "arm": "seam5",
        "provisional_cap_sec": provisional_cap_sec,
        "final_segments": [_public_segment(item) for item in current],
        "decisions": decisions,
        "latency_definitions": {
            "first_publication": "provisional published_at minus provisional segment end",
            "correction": "changed witness available_at minus last replaced provisional published_at",
            "canonical_after_audio": "witness available_at minus ownership interval end",
        },
        "latency_sec": {
            "first_publication": _distribution(first_publication_samples),
            "visible_correction": _distribution(correction_samples),
            "canonical_after_owned_audio": _distribution(canonical_samples),
        },
        "gpu": {
            "seam5_component": measure_decode_work(duration, witnesses),
        },
        "counts": {
            "provisional_segments": len(provisional),
            "witness_requests": len(witnesses),
            "witness_replacements": sum(item["action"] == "replace" for item in decisions),
            "visible_corrections": len(changed_decisions),
            "final_segments": len(current),
        },
    }


def score_lane(
    reference_segments: Sequence[Mapping[str, Any] | Any],
    hypothesis_segments: Sequence[Mapping[str, Any] | Any],
) -> dict[str, float | dict[str, str]]:
    """Evaluate only after reconciliation; reference never enters merge logic."""

    reference = tuple(_evaluation_segment(item) for item in reference_segments)
    hypothesis = tuple(_evaluation_segment(item) for item in hypothesis_segments)
    tbsa = calculate_tbsa(reference, hypothesis)
    diarization = calculate_diarization(reference, hypothesis)
    return {
        "tbsa": float(tbsa["composite"]),
        "wer": float(tbsa["wer"]),
        "coverage": float(tbsa["text_coverage"]),
        "text_speaker_accuracy": float(tbsa["text_speaker_accuracy"]),
        "der": float(diarization["der"]),
        "miss": float(diarization["miss"]),
        "false_alarm": float(diarization["false_alarm"]),
        "speaker_confusion": float(diarization["speaker_confusion"]),
        "speaker_mapping": dict(tbsa["speaker_mapping"]),
    }


def run_lane(
    *,
    duration_sec: float,
    reference_segments: Sequence[Mapping[str, Any] | Any],
    provisional_segments: Sequence[Mapping[str, Any] | Any],
    witness_decodes: Sequence[Mapping[str, Any] | Any],
    provisional_cap_sec: float,
    provisional_decodes: Sequence[Mapping[str, Any] | Any] = (),
) -> dict[str, Any]:
    """Callable driver for the root benchmark."""

    result = reconcile_seam5(
        provisional_segments,
        witness_decodes,
        provisional_cap_sec=provisional_cap_sec,
        duration_sec=duration_sec,
    )
    result["quality"] = score_lane(reference_segments, result["final_segments"])
    if provisional_decodes:
        all_decodes = list(provisional_decodes) + list(witness_decodes)
        result["gpu"]["provisional_component"] = measure_decode_work(duration_sec, provisional_decodes)
        result["gpu"]["provisional_plus_seam5"] = measure_decode_work(duration_sec, all_decodes)
    else:
        result["gpu"]["provisional_component"] = "unmeasured"
        result["gpu"]["provisional_plus_seam5"] = "unmeasured"
    return result


def measure_decode_work(
    duration_sec: float,
    decodes: Sequence[Mapping[str, Any] | Any],
) -> dict[str, float | int | str]:
    """Report decoder RTF and meeting-load RTF without extrapolating gaps."""

    rows = [_decode_record(item) for item in decodes]
    decoded_audio_sec = sum(float(item["window_end"]) - float(item["window_start"]) for item in rows)
    elapsed = [item.get("decode_elapsed_sec") for item in rows]
    complete_timing = all(value is not None for value in elapsed)
    gpu_elapsed_sec = sum(float(value) for value in elapsed) if complete_timing else "unmeasured"
    return {
        "request_count": len(rows),
        "decoded_audio_sec": round(decoded_audio_sec, 6),
        "audio_work_multiplier": round(decoded_audio_sec / duration_sec, 6) if duration_sec else "unmeasured",
        "gpu_elapsed_sec": round(gpu_elapsed_sec, 6) if isinstance(gpu_elapsed_sec, float) else gpu_elapsed_sec,
        "decoder_rtf": (
            round(gpu_elapsed_sec / decoded_audio_sec, 6)
            if isinstance(gpu_elapsed_sec, float) and decoded_audio_sec
            else "unmeasured"
        ),
        "gpu_load_rtf": (
            round(gpu_elapsed_sec / duration_sec, 6)
            if isinstance(gpu_elapsed_sec, float) and duration_sec
            else "unmeasured"
        ),
    }


def _witness_record(
    value: Mapping[str, Any] | Any,
    provisional_cap_sec: float,
    duration_sec: float | None,
) -> dict[str, Any]:
    row = _decode_record(value)
    seam = float(_optional(value, "seam", (row["window_start"] + row["window_end"]) / 2.0))
    row.update(
        {
            "seam": seam,
            "ownership_start": max(
                float(row["window_start"]),
                float(_optional(value, "ownership_start", seam - provisional_cap_sec / 2.0)),
            ),
            "ownership_end": min(
                float(row["window_end"]),
                float(_optional(value, "ownership_end", seam + provisional_cap_sec / 2.0)),
                duration_sec if duration_sec is not None else float(row["window_end"]),
            ),
            "available_at": _optional(value, "available_at", None),
            "timestamps": _optional(value, "timestamps", "absolute"),
            "segments": list(_required(value, "segments")),
            "usable": bool(_optional(value, "usable", True)),
        }
    )
    return row


def _decode_record(value: Mapping[str, Any] | Any) -> dict[str, Any]:
    return {
        "window_start": float(_required(value, "window_start")),
        "window_end": float(_required(value, "window_end")),
        "decode_elapsed_sec": _optional(value, "decode_elapsed_sec", None),
    }


def _absolute_witness_segments(witness: Mapping[str, Any]) -> list[dict[str, Any]]:
    offset = float(witness["window_start"]) if witness["timestamps"] == "relative" else 0.0
    output: list[dict[str, Any]] = []
    for item in witness["segments"]:
        segment = _segment_record(item, origin="witness")
        segment["start"] += offset
        segment["end"] += offset
        output.append(segment)
    return sorted(output, key=_segment_key)


def _map_speakers(
    candidate: Sequence[dict[str, Any]],
    previous_witness: Sequence[dict[str, Any]],
    provisional: Sequence[dict[str, Any]],
    fresh_ordinal: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    local_labels = sorted({str(item["speaker"]) for item in candidate})
    mapping: dict[str, str] = {}
    stages: list[dict[str, Any]] = []

    for stage_name, anchors in (("previous_witness", previous_witness), ("provisional", provisional)):
        remaining = [label for label in local_labels if label not in mapping]
        blocked = set(mapping.values())
        canonical_labels = sorted({str(item["speaker"]) for item in anchors} - blocked)
        weights = {
            (local, canonical): _speaker_overlap(candidate, local, anchors, canonical)
            for local in remaining
            for canonical in canonical_labels
        }
        assignment = _maximum_positive_assignment(remaining, canonical_labels, weights)
        mapping.update(assignment)
        stages.append(
            {
                "stage": stage_name,
                "weights": {f"{left}->{right}": round(score, 6) for (left, right), score in weights.items()},
                "accepted": assignment,
            }
        )

    for local in local_labels:
        if local not in mapping:
            mapping[local] = f"SEAM_NEW_{fresh_ordinal:03d}"
            fresh_ordinal += 1
    mapped = [dict(item, speaker=mapping[str(item["speaker"])]) for item in candidate]
    return mapped, {"final": mapping, "stages": stages}, fresh_ordinal


def _maximum_positive_assignment(
    rows: Sequence[str],
    columns: Sequence[str],
    weights: Mapping[tuple[str, str], float],
) -> dict[str, str]:
    @lru_cache(maxsize=None)
    def solve(row_index: int, used: int) -> tuple[float, tuple[int | None, ...]]:
        if row_index == len(rows):
            return 0.0, ()
        best_score, best_tail = solve(row_index + 1, used)
        best = (best_score, (None,) + best_tail)
        for column_index, column in enumerate(columns):
            score = float(weights.get((rows[row_index], column), 0.0))
            if score <= 0.0 or used & (1 << column_index):
                continue
            tail_score, tail = solve(row_index + 1, used | (1 << column_index))
            candidate_score = score + tail_score
            if candidate_score > best[0] + 1e-12:
                best = (candidate_score, (column_index,) + tail)
        return best

    choices = solve(0, 0)[1]
    return {
        rows[index]: columns[column]
        for index, column in enumerate(choices)
        if column is not None
    }


def _speaker_overlap(
    left_segments: Sequence[dict[str, Any]],
    left_speaker: str,
    right_segments: Sequence[dict[str, Any]],
    right_speaker: str,
) -> float:
    return sum(
        max(0.0, min(float(left["end"]), float(right["end"])) - max(float(left["start"]), float(right["start"])))
        for left in left_segments
        if left["speaker"] == left_speaker
        for right in right_segments
        if right["speaker"] == right_speaker
    )


def _select_token_pieces(
    segments: Sequence[Mapping[str, Any]],
    start: float,
    end: float,
    *,
    owned: bool,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for segment in segments:
        tokens = str(segment["text"]).split()
        duration = float(segment["end"]) - float(segment["start"])
        if not tokens or duration <= 0.0:
            continue
        step = duration / len(tokens)
        selected: list[tuple[str, float, float]] = []
        for index, token in enumerate(tokens):
            token_start = float(segment["start"]) + index * step
            token_end = float(segment["start"]) + (index + 1) * step
            midpoint = (token_start + token_end) / 2.0
            is_owned = start <= midpoint < end
            if is_owned == owned:
                selected.append((token, token_start, token_end))
            elif selected:
                output.append(_token_piece(segment, selected))
                selected = []
        if selected:
            output.append(_token_piece(segment, selected))
    return output


def _token_piece(
    source: Mapping[str, Any],
    tokens: Sequence[tuple[str, float, float]],
) -> dict[str, Any]:
    piece = dict(source)
    piece.update(
        {
            "start": tokens[0][1],
            "end": tokens[-1][2],
            "text": " ".join(item[0] for item in tokens),
        }
    )
    return piece


def _segment_record(value: Mapping[str, Any] | Any, *, origin: str) -> dict[str, Any]:
    row = {
        "start": float(_required(value, "start")),
        "end": float(_required(value, "end")),
        "speaker": str(_required(value, "speaker")),
        "text": str(_required(value, "text")),
        "origin": origin,
    }
    published_at = _optional(value, "published_at", None)
    if published_at is not None:
        row["published_at"] = float(published_at)
    return row


def _evaluation_segment(value: Mapping[str, Any] | Any) -> EvaluationSegment:
    return EvaluationSegment(
        float(_required(value, "start")),
        float(_required(value, "end")),
        str(_required(value, "speaker")),
        str(_required(value, "text")),
    )


def _public_segment(item: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item[key] for key in ("start", "end", "speaker", "text")}


def _semantic_signature(items: Sequence[Mapping[str, Any]]) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            round(float(item["start"]), 3),
            round(float(item["end"]), 3),
            str(item["speaker"]),
            " ".join(str(item["text"]).split()).casefold(),
        )
        for item in sorted(items, key=_segment_key)
    )


def _segment_key(item: Mapping[str, Any]) -> tuple[float, float, str, str]:
    return float(item["start"]), float(item["end"]), str(item["speaker"]), str(item["text"])


def _distribution(values: Iterable[float]) -> dict[str, float | int | str]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {"count": 0, "mean": "unmeasured", "p50": "unmeasured", "p95": "unmeasured", "max": "unmeasured"}
    return {
        "count": len(ordered),
        "mean": round(mean(ordered), 6),
        "p50": round(_percentile(ordered, 0.50), 6),
        "p95": round(_percentile(ordered, 0.95), 6),
        "max": round(ordered[-1], 6),
    }


def _percentile(ordered: Sequence[float], quantile: float) -> float:
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _inferred_duration(
    provisional: Sequence[Mapping[str, Any]],
    witnesses: Sequence[Mapping[str, Any]],
) -> float:
    ends = [float(item["end"]) for item in provisional] + [float(item["window_end"]) for item in witnesses]
    return max(ends, default=0.0)


def _required(value: Mapping[str, Any] | Any, name: str) -> Any:
    return value[name] if isinstance(value, Mapping) else getattr(value, name)


def _optional(value: Mapping[str, Any] | Any, name: str, default: Any) -> Any:
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)


def _demo() -> dict[str, Any]:
    reference = [
        {"start": 0.0, "end": 3.8, "speaker": "Alice", "text": "we should open the New York office"},
        {"start": 3.8, "end": 6.2, "speaker": "Bob", "text": "yes last Friday"},
        {"start": 6.2, "end": 8.0, "speaker": "Alice", "text": "done"},
    ]
    provisional = [
        {"start": 0.0, "end": 1.2, "speaker": "S00", "text": "we should", "published_at": 1.4},
        {"start": 1.2, "end": 2.5, "speaker": "S00", "text": "open the new", "published_at": 2.8},
        {"start": 2.5, "end": 3.8, "speaker": "S00", "text": "york office", "published_at": 4.1},
        {"start": 3.8, "end": 5.0, "speaker": "S00", "text": "yes", "published_at": 5.3},
        {"start": 5.0, "end": 6.2, "speaker": "S01", "text": "last friday", "published_at": 6.5},
        {"start": 6.2, "end": 8.0, "speaker": "S00", "text": "done", "published_at": 8.3},
    ]
    witnesses = [
        {
            "window_start": 0.0,
            "window_end": 5.0,
            "seam": 2.5,
            "ownership_start": 1.25,
            "ownership_end": 3.75,
            "available_at": 5.6,
            "decode_elapsed_sec": 0.6,
            "segments": [
                {"start": 1.2, "end": 3.7, "speaker": "local-A", "text": "open the New York office"},
            ],
        },
        {
            "window_start": 2.5,
            "window_end": 7.5,
            "seam": 5.0,
            "ownership_start": 3.75,
            "ownership_end": 6.25,
            "available_at": 8.1,
            "decode_elapsed_sec": 0.6,
            "segments": [
                {"start": 3.8, "end": 4.9, "speaker": "renamed-X", "text": "yes"},
                {"start": 4.9, "end": 6.2, "speaker": "renamed-Y", "text": "last Friday"},
            ],
        },
    ]
    measurement = run_lane(
        duration_sec=8.0,
        reference_segments=reference,
        provisional_segments=provisional,
        witness_decodes=witnesses,
        provisional_cap_sec=2.5,
    )
    return {
        "prototype_question": "Can seam5 truth-blind replacement repair short provisional chunks?",
        "assumption": "logic prototype; the integrated runner supplies real MOSS decodes",
        "schedule_60s": {
            "cap_2.5": build_seam5_windows(60.0, 2.5),
            "cap_1.0": build_seam5_windows(60.0, 1.0),
        },
        "measurement": measurement,
        "verdict": "synthetic wiring passes; real quality, latency, and GPU verdict remain unmeasured",
    }


if __name__ == "__main__":
    print(json.dumps(_demo(), indent=2, sort_keys=True))
