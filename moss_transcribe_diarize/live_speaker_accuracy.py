"""Evidence-only live speaker scoring for the formal F-certification harness."""

from __future__ import annotations

import hashlib
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from typing import Any, NamedTuple

LIVE_SAMPLE_RATE = 16000
TRANSCRIPT_SEGMENT = re.compile(
    r"\[([0-9]+(?:\.[0-9]+)?)\]\[(S[0-9]+)\](.*?)\[([0-9]+(?:\.[0-9]+)?)\]"
    r"(?=\s*(?:\[|$))",
    re.DOTALL,
)


class Segment(NamedTuple):
    start: float
    end: float
    speaker: str
    text: str

    @property
    def duration(self) -> float:
        return self.end - self.start

CORPUS_ENV = "corpus.env"
REFERENCE_JSONL = "speaker-reference.jsonl"
FINAL_SNAPSHOT_JSON = "speaker-final.json"


def load_reference_jsonl(path: str | Path) -> tuple[Segment, ...]:
    source = Path(path)
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"reference is unreadable: {source}") from exc
    segments = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"reference record {line_number} is not valid JSONL") from exc
        segments.append(_reference_segment(record, line_number))
    if not segments:
        raise ValueError("reference must contain at least one segment")
    return tuple(segments)


def hypothesis_from_live_snapshot(
    payload: Any,
    *,
    corpus_start_sample: int,
    corpus_duration_sec: float,
) -> tuple[Segment, ...]:
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("snapshot"), dict)
        or not isinstance(payload["snapshot"].get("session"), dict)
    ):
        raise ValueError("live snapshot must contain snapshot.session")
    committed = payload["snapshot"]["session"].get("committed")
    if not isinstance(committed, list):
        raise ValueError("live snapshot session committed must be a list")
    if isinstance(corpus_start_sample, bool) or not isinstance(corpus_start_sample, int):
        raise ValueError("corpus_start_sample must be an integer")
    if not isinstance(corpus_duration_sec, (int, float)) or not math.isfinite(corpus_duration_sec):
        raise ValueError("corpus_duration_sec must be finite")
    if corpus_duration_sec <= 0:
        raise ValueError("corpus_duration_sec must be positive")

    hypothesis = []
    for index, item in enumerate(committed):
        if not isinstance(item, dict):
            raise ValueError(f"committed item {index} must be an object")
        start_sample = _required_sample(item, "start_sample", index)
        end_sample = _required_sample(item, "end_sample", index)
        if end_sample <= start_sample:
            raise ValueError(f"committed item {index} has an invalid sample interval")
        transcript = (
            item.get("revised_transcript")
            if item.get("revised_transcript") is not None
            else item.get("transcript")
        )
        if not isinstance(transcript, str):
            raise ValueError(f"committed item {index} transcript must be a string")
        if not transcript:
            continue
        base = (start_sample - corpus_start_sample) / float(LIVE_SAMPLE_RATE)
        for parsed in _span_segments(transcript, sample_count=end_sample - start_sample):
            start = max(0.0, base + parsed.start)
            end = min(float(corpus_duration_sec), base + parsed.end)
            if end > start:
                hypothesis.append(
                    Segment(start=start, end=end, speaker=parsed.speaker, text=parsed.text)
                )
    return tuple(hypothesis)


def score_live_speaker_accuracy(
    reference: tuple[Segment, ...] | list[Segment],
    hypothesis: tuple[Segment, ...] | list[Segment],
) -> dict[str, Any]:
    if not reference:
        raise ValueError("reference must contain at least one segment")
    ref_speakers = sorted({segment.speaker for segment in reference})
    hyp_speakers = sorted({segment.speaker for segment in hypothesis})
    weights = {(ref, hyp): 0.0 for ref in ref_speakers for hyp in hyp_speakers}
    for ref in reference:
        for hyp in hypothesis:
            overlap = _overlap_seconds(ref, hyp)
            if overlap > 0.0:
                weights[(ref.speaker, hyp.speaker)] += overlap
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


def evaluate_live_speaker_evidence(evidence_dir: str | Path) -> dict[str, Any]:
    directory = Path(evidence_dir)
    metadata = _read_env(directory / CORPUS_ENV)
    required = (
        "CORPUS_AUDIO_SHA256",
        "CORPUS_EXPECTED_AUDIO_SHA256",
        "CORPUS_START_SAMPLE",
        "CORPUS_DURATION_SEC",
        "CORPUS_REFERENCE_SHA256",
        "CORPUS_REFERENCE_SEGMENTS",
    )
    missing = [key for key in required if not metadata.get(key)]
    if missing:
        raise ValueError(f"corpus.env missing required fields: {', '.join(missing)}")
    actual_audio_hash = metadata["CORPUS_AUDIO_SHA256"]
    expected_audio_hash = metadata["CORPUS_EXPECTED_AUDIO_SHA256"]
    if actual_audio_hash != expected_audio_hash:
        raise ValueError(
            f"corpus audio sha256 mismatch: actual {actual_audio_hash}, expected {expected_audio_hash}"
        )

    reference_path = directory / REFERENCE_JSONL
    snapshot_path = directory / FINAL_SNAPSHOT_JSON
    reference_hash = _sha256(reference_path, "reference")
    if reference_hash != metadata["CORPUS_REFERENCE_SHA256"]:
        raise ValueError(
            "corpus reference sha256 mismatch: "
            f"actual {reference_hash}, expected {metadata['CORPUS_REFERENCE_SHA256']}"
        )
    reference = load_reference_jsonl(reference_path)
    expected_segments = _positive_int(metadata["CORPUS_REFERENCE_SEGMENTS"], "reference segments")
    if len(reference) != expected_segments:
        raise ValueError(
            f"corpus reference segment count mismatch: actual {len(reference)}, "
            f"expected {expected_segments}"
        )
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"final live snapshot is unreadable: {snapshot_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("final live snapshot is not valid JSON") from exc
    start_sample = _non_negative_int(metadata["CORPUS_START_SAMPLE"], "corpus start sample")
    duration = _positive_float(metadata["CORPUS_DURATION_SEC"], "corpus duration")
    hypothesis = hypothesis_from_live_snapshot(
        snapshot,
        corpus_start_sample=start_sample,
        corpus_duration_sec=duration,
    )
    result = score_live_speaker_accuracy(reference, hypothesis)
    return {
        **result,
        "audio_sha256": actual_audio_hash,
        "reference_sha256": reference_hash,
        "reference_segments": len(reference),
        "hypothesis_segments": len(hypothesis),
        "corpus_start_sample": start_sample,
        "corpus_duration_sec": duration,
    }


def _reference_segment(record: Any, line_number: int) -> Segment:
    if not isinstance(record, dict):
        raise ValueError(f"reference record {line_number} must be an object")
    start = _required_number(record, "start", line_number)
    end = _required_number(record, "end", line_number)
    if end <= start:
        raise ValueError(f"reference record {line_number} end must be greater than start")
    speaker = _required_text(record, "speaker", line_number)
    text = _required_text(record, "text", line_number)
    return Segment(start=start, end=end, speaker=speaker, text=text)


def _span_segments(transcript: str, *, sample_count: int):
    duration = sample_count / float(LIVE_SAMPLE_RATE)
    for match in TRANSCRIPT_SEGMENT.finditer(transcript):
        start = min(max(float(match.group(1)), 0.0), duration)
        end = max(min(max(float(match.group(4)), 0.0), duration), start)
        yield Segment(start=start, end=end, speaker=match.group(2), text=match.group(3).strip())


def _maximum_weight_assignment(row_labels, column_labels, weights):
    rows = list(row_labels)
    columns = list(column_labels)
    if len(columns) < len(rows):
        columns.extend(
            f"<HYP_PAD_{index:03d}>" for index in range(1, len(rows) - len(columns) + 1)
        )
    rank = {column: index for index, column in enumerate(columns)}

    @lru_cache(maxsize=None)
    def solve(row_index, used_mask):
        if row_index == len(rows):
            return 0.0, ()
        best_score = -math.inf
        best_assignment = None
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


def _overlap_seconds(left, right):
    return max(0.0, min(left.end, right.end) - max(left.start, right.start))


def _reference_overlap_seconds(reference, hypothesis):
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


def _ratio(numerator, denominator):
    return numerator / denominator if denominator > 0.0 else 0.0


def _round_metric(value):
    value = max(value, 0.0)
    if math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-12):
        return 0.0
    if math.isclose(value, 1.0, rel_tol=0.0, abs_tol=1e-12):
        return 1.0
    return round(value, 6)


def _round_seconds(value):
    return round(max(value, 0.0), 6)


def _required_number(record: dict[str, Any], key: str, line_number: int) -> float:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"reference record {line_number} field {key} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"reference record {line_number} field {key} must be finite")
    return number


def _required_text(record: dict[str, Any], key: str, line_number: int) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"reference record {line_number} field {key} must be non-empty")
    return value


def _required_sample(record: dict[str, Any], key: str, index: int) -> int:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"committed item {index} {key} must be a non-negative integer")
    return value


def _read_env(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"corpus.env is unreadable: {path}") from exc
    values = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if separator and key:
            values[key] = value
    return values


def _sha256(path: Path, label: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(f"{label} is unreadable: {path}") from exc


def _non_negative_int(value: str, label: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if number < 0:
        raise ValueError(f"{label} must be non-negative")
    return number


def _positive_int(value: str, label: str) -> int:
    number = _non_negative_int(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be positive")
    return number


def _positive_float(value: str, label: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return number


__all__ = [
    "evaluate_live_speaker_evidence",
    "hypothesis_from_live_snapshot",
    "load_reference_jsonl",
    "score_live_speaker_accuracy",
]
