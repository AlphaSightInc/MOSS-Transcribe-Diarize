from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


MAX_FINE_DURATION_SECONDS = 300.0
SCHEMA_VERSION = 1


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
class Fixture:
    fixture_id: str
    duration_sec: float
    reference_covered_seconds: float
    match_rate: float
    reference_path: Path
    reference: tuple[Segment, ...]


def evaluate_files(
    *,
    manifest_path: str | Path,
    alignment_stats_path: str | Path,
    hypothesis_path: str | Path,
) -> dict[str, Any]:
    fixture = _load_fixture(Path(manifest_path), Path(alignment_stats_path))
    hypothesis = tuple(_load_hypothesis(Path(hypothesis_path)))
    tbsa = calculate_tbsa(fixture.reference, hypothesis)
    diarization = calculate_diarization(fixture.reference, hypothesis)
    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_id": fixture.fixture_id,
        "gate_tier": "fine",
        "reference_path": str(fixture.reference_path.resolve()),
        "match_rate": fixture.match_rate,
        "reference_covered_seconds": fixture.reference_covered_seconds,
        "tbsa": tbsa,
        "diarization": diarization,
    }


def calculate_tbsa(
    reference: tuple[Segment, ...] | list[Segment],
    hypothesis: tuple[Segment, ...] | list[Segment],
) -> dict[str, Any]:
    ref_speakers = _ordered_speakers(reference)
    hyp_speakers = _ordered_speakers(hypothesis)
    weights = _text_speaker_weights(reference, hypothesis, ref_speakers, hyp_speakers)
    mapping, matched_weight = _maximum_weight_assignment(
        ref_speakers,
        hyp_speakers,
        weights,
    )
    total_tokens = sum(_token_count(segment.text) for segment in reference)
    text_speaker_accuracy = _ratio(matched_weight, total_tokens)
    text_coverage = _text_coverage(reference, hypothesis)
    wer = _wer(
        _tokenize(" ".join(segment.text for segment in sorted(reference, key=_segment_order))),
        _tokenize(" ".join(segment.text for segment in sorted(hypothesis, key=_segment_order))),
    )
    composite = (
        0.40 * text_speaker_accuracy
        + 0.35 * text_coverage
        + 0.25 * (1.0 - wer)
    )
    return {
        "composite": _round_metric(composite),
        "text_speaker_accuracy": _round_metric(text_speaker_accuracy),
        "text_coverage": _round_metric(text_coverage),
        "wer": _round_metric(wer),
        "speaker_mapping": mapping,
    }


def calculate_diarization(
    reference: tuple[Segment, ...] | list[Segment],
    hypothesis: tuple[Segment, ...] | list[Segment],
) -> dict[str, Any]:
    ref_speakers = _ordered_speakers(reference)
    hyp_speakers = _ordered_speakers(hypothesis)
    weights = _duration_speaker_weights(reference, hypothesis, ref_speakers, hyp_speakers)
    mapping, _matched_weight = _maximum_weight_assignment(
        ref_speakers,
        hyp_speakers,
        weights,
    )
    reference_duration = sum(segment.duration for segment in reference)
    overlapped_by_reference = 0.0
    confusion_duration = 0.0
    for ref in reference:
        for hyp in hypothesis:
            overlap = _overlap_seconds(ref, hyp)
            if overlap <= 0.0:
                continue
            overlapped_by_reference += overlap
            if mapping.get(ref.speaker) != hyp.speaker:
                confusion_duration += overlap

    hypothesis_reference_overlap = 0.0
    for hyp in hypothesis:
        for ref in reference:
            hypothesis_reference_overlap += _overlap_seconds(ref, hyp)

    hypothesis_duration = sum(segment.duration for segment in hypothesis)
    miss = max(reference_duration - overlapped_by_reference, 0.0)
    false_alarm = max(hypothesis_duration - hypothesis_reference_overlap, 0.0)
    speaker_confusion = min(confusion_duration, reference_duration)
    der = _ratio(miss + false_alarm + speaker_confusion, reference_duration)
    return {
        "der": _round_metric(der),
        "miss": _round_metric(_ratio(miss, reference_duration)),
        "false_alarm": _round_metric(_ratio(false_alarm, reference_duration)),
        "speaker_confusion": _round_metric(_ratio(speaker_confusion, reference_duration)),
        "speaker_mapping": mapping,
    }


def calculate_speaker_accuracy(
    reference: tuple[Segment, ...] | list[Segment],
    hypothesis: tuple[Segment, ...] | list[Segment],
) -> dict[str, Any]:
    """Duration-weighted speaker accuracy under the best label permutation.

    The denominator is all reference speech, so missed or unlabelled speech cannot disappear
    from the score. This is the interval form of the live identity acceptance scorer: canonical
    label names are arbitrary, and the maximum-weight one-to-one mapping gives them credit only
    for reference speech they overlap.
    """

    ref_speakers = _ordered_speakers(reference)
    hyp_speakers = _ordered_speakers(hypothesis)
    weights = _duration_speaker_weights(reference, hypothesis, ref_speakers, hyp_speakers)
    mapping, matched_weight = _maximum_weight_assignment(ref_speakers, hyp_speakers, weights)
    reference_duration = sum(segment.duration for segment in reference)
    covered_duration = sum(_reference_overlap_seconds(segment, hypothesis) for segment in reference)
    return {
        "speaker_accuracy": _round_metric(_ratio(matched_weight, reference_duration)),
        "reference_coverage": _round_metric(_ratio(covered_duration, reference_duration)),
        "matched_speaker_seconds": _round_seconds(matched_weight),
        "covered_reference_seconds": _round_seconds(covered_duration),
        "reference_seconds": _round_seconds(reference_duration),
        "hypothesis_seconds": _round_seconds(sum(segment.duration for segment in hypothesis)),
        "reference_speaker_count": len(ref_speakers),
        "hypothesis_speaker_count": len(hyp_speakers),
        "speaker_mapping": mapping,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score a fine MOSS speaker fixture.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--alignment-stats", required=True)
    parser.add_argument("--hypothesis", required=True)
    args = parser.parse_args(argv)

    try:
        payload = evaluate_files(
            manifest_path=args.manifest,
            alignment_stats_path=args.alignment_stats,
            hypothesis_path=args.hypothesis,
        )
    except ValueError as exc:
        print(f"evaluation error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


def _load_fixture(manifest_path: Path, alignment_stats_path: Path) -> Fixture:
    manifest = _load_json_object(manifest_path, "manifest")
    alignment_stats = _load_json_object(alignment_stats_path, "alignment stats")
    fixture_id = _required_str(manifest, "sample_id", "manifest")
    duration_sec = _required_number(manifest, "duration_sec", "manifest")
    reference_covered_seconds = _required_number(
        manifest,
        "reference_covered_seconds",
        "manifest",
    )
    match_rate = _required_number(alignment_stats, "match_rate", "alignment stats")
    if match_rate != 1.0:
        raise ValueError("fine fixture requires match_rate == 1.0")
    if not math.isclose(reference_covered_seconds, duration_sec, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("fine fixture requires coverage equal to duration_sec")
    if duration_sec > MAX_FINE_DURATION_SECONDS:
        raise ValueError("fine fixture duration must be at most five minutes")

    reference_path = manifest_path.parent / "reference.jsonl"
    reference = tuple(_load_jsonl_segments(reference_path, "reference"))
    if not reference:
        raise ValueError("reference must contain at least one segment")
    covered_seconds = _covered_seconds(reference)
    if not math.isclose(covered_seconds, reference_covered_seconds, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("reference timestamps do not match reference_covered_seconds")

    if "segment_count" in manifest and manifest["segment_count"] != len(reference):
        raise ValueError("manifest segment_count does not match reference")
    if "speakers" in manifest:
        speakers = manifest["speakers"]
        if not isinstance(speakers, list) or sorted(speakers) != _ordered_speakers(reference):
            raise ValueError("manifest speakers do not match reference")

    return Fixture(
        fixture_id=fixture_id,
        duration_sec=duration_sec,
        reference_covered_seconds=reference_covered_seconds,
        match_rate=match_rate,
        reference_path=reference_path,
        reference=reference,
    )


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"{label} is unreadable: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _load_hypothesis(path: Path) -> list[Segment]:
    if path.suffix == ".jsonl":
        segments = _load_jsonl_segments(path, "hypothesis JSONL")
    else:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError(f"hypothesis is unreadable: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"hypothesis is not valid JSON: {path}") from exc
        if isinstance(payload, dict):
            if "segments" not in payload:
                raise ValueError("hypothesis object must contain segments")
            payload = payload["segments"]
        if not isinstance(payload, list):
            raise ValueError("hypothesis must be a JSON segment list")
        segments = [_segment_from_record(record, "hypothesis") for record in payload]
    if not segments:
        raise ValueError("hypothesis must contain at least one segment")
    return segments


def _load_jsonl_segments(path: Path, label: str) -> list[Segment]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"{label} is unreadable: {path}") from exc

    segments: list[Segment] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} record {line_number} is not valid JSONL") from exc
        segments.append(_segment_from_record(record, label))
    return segments


def _segment_from_record(record: Any, label: str) -> Segment:
    if not isinstance(record, dict):
        raise ValueError(f"{label} segment must be an object")
    start = _required_number(record, "start", label)
    end = _required_number(record, "end", label)
    speaker = _required_str(record, "speaker", label)
    text = _required_str(record, "text", label)
    if end <= start:
        raise ValueError(f"{label} segment end must be greater than start")
    return Segment(start=start, end=end, speaker=speaker, text=text)


def _required_number(record: dict[str, Any], key: str, label: str) -> float:
    if key not in record:
        raise ValueError(f"{label} missing required field {key}")
    value = record[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} field {key} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} field {key} must be finite")
    return number


def _required_str(record: dict[str, Any], key: str, label: str) -> str:
    if key not in record:
        raise ValueError(f"{label} missing required field {key}")
    value = record[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} field {key} must be a non-empty string")
    return value


def _maximum_weight_assignment(
    row_labels: list[str],
    column_labels: list[str],
    weights: dict[tuple[str, str], float],
) -> tuple[dict[str, str], float]:
    rows = list(row_labels)
    columns = list(column_labels)
    if len(columns) < len(rows):
        columns.extend(f"<HYP_PAD_{index:03d}>" for index in range(1, len(rows) - len(columns) + 1))

    rank = {column: index for index, column in enumerate(columns)}

    @lru_cache(maxsize=None)
    def solve(row_index: int, used_mask: int) -> tuple[float, tuple[int, ...]]:
        if row_index == len(rows):
            return 0.0, ()
        best_score = -math.inf
        best_assignment: tuple[int, ...] | None = None
        row = rows[row_index]
        for column_index, column in enumerate(columns):
            if used_mask & (1 << column_index):
                continue
            rest_score, rest_assignment = solve(row_index + 1, used_mask | (1 << column_index))
            score = weights.get((row, column), 0.0) + rest_score
            assignment = (rank[column],) + rest_assignment
            if (
                score > best_score + 1e-12
                or (
                    math.isclose(score, best_score, rel_tol=0.0, abs_tol=1e-12)
                    and (best_assignment is None or assignment < best_assignment)
                )
            ):
                best_score = score
                best_assignment = assignment
        if best_assignment is None:
            return 0.0, ()
        return best_score, best_assignment

    matched_weight, assignment_ranks = solve(0, 0)
    inverse_rank = {value: key for key, value in rank.items()}
    mapping = {
        row: inverse_rank[assignment_ranks[index]]
        for index, row in enumerate(rows)
    }
    return mapping, matched_weight


def _text_speaker_weights(
    reference: tuple[Segment, ...] | list[Segment],
    hypothesis: tuple[Segment, ...] | list[Segment],
    ref_speakers: list[str],
    hyp_speakers: list[str],
) -> dict[tuple[str, str], float]:
    weights = {(ref, hyp): 0.0 for ref in ref_speakers for hyp in hyp_speakers}
    for ref in reference:
        ref_tokens = _token_count(ref.text)
        if ref_tokens == 0:
            continue
        for hyp in hypothesis:
            overlap = _overlap_seconds(ref, hyp)
            if overlap <= 0.0:
                continue
            credit = ref_tokens * min(overlap / ref.duration, 1.0)
            weights[(ref.speaker, hyp.speaker)] += credit
    return weights


def _duration_speaker_weights(
    reference: tuple[Segment, ...] | list[Segment],
    hypothesis: tuple[Segment, ...] | list[Segment],
    ref_speakers: list[str],
    hyp_speakers: list[str],
) -> dict[tuple[str, str], float]:
    weights = {(ref, hyp): 0.0 for ref in ref_speakers for hyp in hyp_speakers}
    for ref in reference:
        for hyp in hypothesis:
            overlap = _overlap_seconds(ref, hyp)
            if overlap > 0.0:
                weights[(ref.speaker, hyp.speaker)] += overlap
    return weights


def _overlap_seconds(left: Segment, right: Segment) -> float:
    return max(0.0, min(left.end, right.end) - max(left.start, right.start))


def _reference_overlap_seconds(reference: Segment, hypothesis: tuple[Segment, ...] | list[Segment]) -> float:
    intervals = []
    for segment in hypothesis:
        start = max(reference.start, segment.start)
        end = min(reference.end, segment.end)
        if end > start:
            intervals.append((start, end))
    if not intervals:
        return 0.0
    intervals.sort()
    covered = 0.0
    current_start, current_end = intervals[0]
    for start, end in intervals[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            covered += current_end - current_start
            current_start, current_end = start, end
    return covered + current_end - current_start


def _text_coverage(
    reference: tuple[Segment, ...] | list[Segment],
    hypothesis: tuple[Segment, ...] | list[Segment],
) -> float:
    total = sum(_token_count(segment.text) for segment in reference)
    if total == 0:
        return 0.0
    covered = 0.0
    for ref in reference:
        ref_tokens = _token_count(ref.text)
        for hyp in hypothesis:
            overlap = _overlap_seconds(ref, hyp)
            if overlap > 0.0:
                covered += ref_tokens * min(overlap / ref.duration, 1.0)
    return min(_ratio(covered, total), 1.0)


def _wer(reference_tokens: list[str], hypothesis_tokens: list[str]) -> float:
    if not reference_tokens:
        return 0.0 if not hypothesis_tokens else 1.0
    previous = list(range(len(hypothesis_tokens) + 1))
    for row_index, ref_token in enumerate(reference_tokens, start=1):
        current = [row_index]
        for column_index, hyp_token in enumerate(hypothesis_tokens, start=1):
            substitution = previous[column_index - 1] + (ref_token != hyp_token)
            insertion = current[column_index - 1] + 1
            deletion = previous[column_index] + 1
            current.append(min(substitution, insertion, deletion))
        previous = current
    return _ratio(previous[-1], len(reference_tokens))


def _covered_seconds(segments: tuple[Segment, ...]) -> float:
    intervals = sorted((segment.start, segment.end) for segment in segments)
    total = 0.0
    current_start, current_end = intervals[0]
    for start, end in intervals[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue
        total += current_end - current_start
        current_start, current_end = start, end
    total += current_end - current_start
    return total


def _ordered_speakers(segments: tuple[Segment, ...] | list[Segment]) -> list[str]:
    return sorted({segment.speaker for segment in segments})


def _segment_order(segment: Segment) -> tuple[float, float, str, str]:
    return (segment.start, segment.end, segment.speaker, segment.text)


def _token_count(text: str) -> int:
    return len(_tokenize(text))


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0.0:
        return 0.0
    return numerator / denominator


def _round_metric(value: float) -> float:
    value = max(value, 0.0)
    if math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-12):
        return 0.0
    if math.isclose(value, 1.0, rel_tol=0.0, abs_tol=1e-12):
        return 1.0
    return round(value, 6)


def _round_seconds(value: float) -> float:
    return round(max(value, 0.0), 6)


if __name__ == "__main__":
    raise SystemExit(main())
