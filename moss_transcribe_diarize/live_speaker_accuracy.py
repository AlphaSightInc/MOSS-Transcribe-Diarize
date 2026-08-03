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
# `afplay` has no render-start handshake.  The formal driver records the accepted sample
# position before it launches the process, so process startup can move the corpus by seconds
# relative to that declared position.  Keep the correction bounded to the measured startup
# envelope and choose it using speech coverage only -- speaker labels do not participate.
CORPUS_ALIGNMENT_MAX_SEC = 3.0
CORPUS_ALIGNMENT_STEP_SEC = 0.05
TRANSCRIPT_SEGMENT = re.compile(
    r"\[([0-9]+(?:\.[0-9]+)?)\]\[(S[0-9]+)\](.*?)\[([0-9]+(?:\.[0-9]+)?)\]"
    r"(?=\s*(?:\[|$))",
    re.DOTALL,
)


class TranscriptSegment(NamedTuple):
    start: float
    end: float
    speaker: str
    text: str

    @property
    def duration(self) -> float:
        return self.end - self.start


class SpeakerActivityInterval(NamedTuple):
    """A speaker-labelled activity interval, independent of transcript text."""

    start: float
    end: float
    speaker: str

    @property
    def duration(self) -> float:
        return self.end - self.start


# Private compatibility name for the original transcript parser.
Segment = TranscriptSegment

CORPUS_ENV = "corpus.env"
REFERENCE_JSONL = "speaker-reference.jsonl"
FINAL_SNAPSHOT_JSON = "speaker-final.json"


def load_reference_jsonl(path: str | Path) -> tuple[Segment, ...]:
    """Load transcript segments, using independent v2 transcript timing when present."""

    records = _load_reference_records(path)
    return tuple(
        _reference_segment(record, line_number)
        for line_number, record in enumerate(records, start=1)
    )


def load_reference_speaker_activity_jsonl(
    path: str | Path,
) -> tuple[SpeakerActivityInterval, ...]:
    """Load speaker activity without collapsing it to lexical transcript timing."""

    records = _load_reference_records(path)
    return tuple(
        _reference_activity(record, line_number)
        for line_number, record in enumerate(records, start=1)
    )


def _load_reference_records(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"reference is unreadable: {source}") from exc
    records = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"reference record {line_number} is not valid JSONL") from exc
        if not isinstance(record, dict):
            raise ValueError(f"reference record {line_number} must be an object")
        records.append(record)
    if not records:
        raise ValueError("reference must contain at least one segment")
    return records


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


def speaker_activity_from_live_snapshot(
    payload: Any,
    *,
    corpus_start_sample: int,
    corpus_duration_sec: float,
) -> tuple[SpeakerActivityInterval, ...]:
    transcript = hypothesis_from_live_snapshot(
        payload,
        corpus_start_sample=corpus_start_sample,
        corpus_duration_sec=corpus_duration_sec,
    )
    return tuple(
        SpeakerActivityInterval(item.start, item.end, item.speaker) for item in transcript
    )


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
    activity = _speaker_activity_metrics(reference, hypothesis, mapping)
    reference_seconds_by_speaker = {
        speaker: sum(segment.duration for segment in reference if segment.speaker == speaker)
        for speaker in ref_speakers
    }
    matched_seconds_by_speaker = {
        speaker: weights.get((speaker, mapping[speaker]), 0.0)
        for speaker in ref_speakers
    }
    reference_duration = sum(segment.duration for segment in reference)
    covered_duration = sum(_reference_overlap_seconds(segment, hypothesis) for segment in reference)
    mapped_labels = tuple(mapping.values())
    two_sided_mapping = (
        len(mapped_labels) == len(ref_speakers)
        and len(set(mapped_labels)) == len(mapped_labels)
        and all(label in hyp_speakers for label in mapped_labels)
    )
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
        "two_sided_mapping": two_sided_mapping,
        "speaker_correctness": {
            speaker: _round_metric(
                _ratio(matched_seconds_by_speaker[speaker], reference_seconds_by_speaker[speaker])
            )
            for speaker in ref_speakers
        },
        **activity,
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
    reference_transcript = load_reference_jsonl(reference_path)
    reference = load_reference_speaker_activity_jsonl(reference_path)
    expected_segments = _positive_int(metadata["CORPUS_REFERENCE_SEGMENTS"], "reference segments")
    if len(reference_transcript) != expected_segments or len(reference) != expected_segments:
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
    identity_snapshot = snapshot.get("snapshot", {}).get("session", {}).get(
        "identity_snapshot", {}
    )
    canonical_speakers = (
        identity_snapshot.get("canonical_speakers", [])
        if isinstance(identity_snapshot, dict)
        else []
    )
    if not isinstance(canonical_speakers, list):
        canonical_speakers = []
    start_sample = _non_negative_int(metadata["CORPUS_START_SAMPLE"], "corpus start sample")
    duration = _positive_float(metadata["CORPUS_DURATION_SEC"], "corpus duration")
    unaligned_hypothesis = speaker_activity_from_live_snapshot(
        snapshot,
        corpus_start_sample=start_sample,
        corpus_duration_sec=duration,
    )
    unaligned = score_live_speaker_accuracy(reference, unaligned_hypothesis)
    alignment_samples, hypothesis = _coverage_alignment(
        reference,
        snapshot,
        declared_start_sample=start_sample,
        corpus_duration_sec=duration,
    )
    result = score_live_speaker_accuracy(reference, hypothesis)
    return {
        **result,
        "audio_sha256": actual_audio_hash,
        "reference_sha256": reference_hash,
        "reference_segments": len(reference),
        "hypothesis_segments": len(hypothesis),
        "canonical_speaker_count": len(canonical_speakers),
        "corpus_start_sample": start_sample,
        "aligned_corpus_start_sample": start_sample + alignment_samples,
        "corpus_alignment_adjustment_sec": _round_signed_seconds(
            alignment_samples / float(LIVE_SAMPLE_RATE)
        ),
        "corpus_alignment_max_sec": CORPUS_ALIGNMENT_MAX_SEC,
        "corpus_alignment_step_sec": CORPUS_ALIGNMENT_STEP_SEC,
        "unaligned_speaker_accuracy": unaligned["speaker_accuracy"],
        "unaligned_reference_coverage": unaligned["reference_coverage"],
        "corpus_duration_sec": duration,
    }


def _coverage_alignment(
    reference: tuple[Segment, ...],
    snapshot: dict[str, Any],
    *,
    declared_start_sample: int,
    corpus_duration_sec: float,
) -> tuple[int, tuple[Segment, ...]]:
    """Choose one global playback shift without inspecting a speaker label.

    Coverage is the union of hypothesis time under each reference speech interval; the
    hypothesis speaker names and the optimal speaker mapping are deliberately absent.  Ties
    keep the smallest absolute adjustment, then the lower signed adjustment, so a flat
    coverage curve preserves the declared position rather than inventing movement.
    """

    step_samples = int(round(CORPUS_ALIGNMENT_STEP_SEC * LIVE_SAMPLE_RATE))
    max_samples = int(round(CORPUS_ALIGNMENT_MAX_SEC * LIVE_SAMPLE_RATE))
    best_samples = 0
    best_hypothesis = speaker_activity_from_live_snapshot(
        snapshot,
        corpus_start_sample=declared_start_sample,
        corpus_duration_sec=corpus_duration_sec,
    )
    best_coverage = _covered_reference_seconds(reference, best_hypothesis)
    for adjustment in range(-max_samples, max_samples + 1, step_samples):
        if adjustment == 0 or declared_start_sample + adjustment < 0:
            continue
        candidate = speaker_activity_from_live_snapshot(
            snapshot,
            corpus_start_sample=declared_start_sample + adjustment,
            corpus_duration_sec=corpus_duration_sec,
        )
        coverage = _covered_reference_seconds(reference, candidate)
        better_tie = math.isclose(coverage, best_coverage, rel_tol=0.0, abs_tol=1e-12) and (
            (abs(adjustment), adjustment) < (abs(best_samples), best_samples)
        )
        if coverage > best_coverage + 1e-12 or better_tie:
            best_samples = adjustment
            best_hypothesis = candidate
            best_coverage = coverage
    return best_samples, best_hypothesis


def _covered_reference_seconds(reference, hypothesis) -> float:
    return sum(_reference_overlap_seconds(segment, hypothesis) for segment in reference)


def _reference_segment(record: Any, line_number: int) -> Segment:
    if not isinstance(record, dict):
        raise ValueError(f"reference record {line_number} must be an object")
    if record.get("schema") == "moss-speaker-reference.v2":
        activity = record.get("speaker_activity")
        transcript = record.get("transcript")
        if not isinstance(activity, dict) or not isinstance(transcript, dict):
            raise ValueError(
                f"reference record {line_number} v2 activity and transcript must be objects"
            )
        record = {
            "start": transcript.get("start", activity.get("start")),
            "end": transcript.get("end", activity.get("end")),
            "speaker": activity.get("speaker"),
            "text": transcript.get("text"),
        }
    start = _required_number(record, "start", line_number)
    end = _required_number(record, "end", line_number)
    if end <= start:
        raise ValueError(f"reference record {line_number} end must be greater than start")
    speaker = _required_text(record, "speaker", line_number)
    text = _required_text(record, "text", line_number)
    return Segment(start=start, end=end, speaker=speaker, text=text)


def _reference_activity(record: Any, line_number: int) -> SpeakerActivityInterval:
    if not isinstance(record, dict):
        raise ValueError(f"reference record {line_number} must be an object")
    if record.get("schema") == "moss-speaker-reference.v2":
        activity = record.get("speaker_activity")
        if not isinstance(activity, dict):
            raise ValueError(f"reference record {line_number} v2 activity must be an object")
        record = activity
    start = _required_number(record, "start", line_number)
    end = _required_number(record, "end", line_number)
    if end <= start:
        raise ValueError(f"reference record {line_number} end must be greater than start")
    return SpeakerActivityInterval(
        start=start,
        end=end,
        speaker=_required_text(record, "speaker", line_number),
    )


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


def _speaker_activity_metrics(reference, hypothesis, mapping):
    reference_union = _union_intervals(reference)
    hypothesis_union = _union_intervals(hypothesis)
    reference_activity_seconds = sum(end - start for start, end in reference_union)
    hypothesis_activity_seconds = sum(end - start for start, end in hypothesis_union)
    true_positive_activity_seconds = _interval_intersection_seconds(
        reference_union, hypothesis_union
    )
    false_positive_activity_seconds = max(
        0.0, hypothesis_activity_seconds - true_positive_activity_seconds
    )
    missed_activity_seconds = max(
        0.0, reference_activity_seconds - true_positive_activity_seconds
    )

    inverse_mapping = {
        hypothesis_speaker: reference_speaker
        for reference_speaker, hypothesis_speaker in mapping.items()
        if not hypothesis_speaker.startswith("<HYP_PAD_")
    }
    boundaries = sorted(
        {
            point
            for interval in (*reference, *hypothesis)
            for point in (interval.start, interval.end)
        }
    )
    missed_speaker_seconds = 0.0
    false_positive_speaker_seconds = 0.0
    confused_speaker_seconds = 0.0
    reference_speaker_seconds = 0.0
    for start, end in zip(boundaries, boundaries[1:]):
        if end <= start:
            continue
        midpoint = (start + end) / 2.0
        reference_active = {
            interval.speaker
            for interval in reference
            if interval.start <= midpoint < interval.end
        }
        hypothesis_active = {
            interval.speaker
            for interval in hypothesis
            if interval.start <= midpoint < interval.end
        }
        width = end - start
        reference_count = len(reference_active)
        hypothesis_count = len(hypothesis_active)
        mapped_active = {
            inverse_mapping[label] for label in hypothesis_active if label in inverse_mapping
        }
        correct_count = len(reference_active & mapped_active)
        matched_count = min(reference_count, hypothesis_count)
        reference_speaker_seconds += reference_count * width
        missed_speaker_seconds += max(0, reference_count - hypothesis_count) * width
        false_positive_speaker_seconds += max(0, hypothesis_count - reference_count) * width
        confused_speaker_seconds += max(0, matched_count - correct_count) * width
    diarization_errors = (
        missed_speaker_seconds
        + false_positive_speaker_seconds
        + confused_speaker_seconds
    )
    return {
        "speaker_activity_precision": _round_metric(
            _ratio(true_positive_activity_seconds, hypothesis_activity_seconds)
        ),
        "speaker_activity_recall": _round_metric(
            _ratio(true_positive_activity_seconds, reference_activity_seconds)
        ),
        "reference_activity_seconds": _round_seconds(reference_activity_seconds),
        "hypothesis_activity_seconds": _round_seconds(hypothesis_activity_seconds),
        "true_positive_activity_seconds": _round_seconds(true_positive_activity_seconds),
        "false_positive_activity_seconds": _round_seconds(false_positive_activity_seconds),
        "missed_activity_seconds": _round_seconds(missed_activity_seconds),
        "false_positive_speaker_seconds": _round_seconds(false_positive_speaker_seconds),
        "missed_speaker_seconds": _round_seconds(missed_speaker_seconds),
        "confused_speaker_seconds": _round_seconds(confused_speaker_seconds),
        "diarization_error_rate": _round_metric(
            _ratio(diarization_errors, reference_speaker_seconds)
        ),
    }


def _union_intervals(intervals):
    ordered = sorted(
        ((interval.start, interval.end) for interval in intervals if interval.end > interval.start)
    )
    if not ordered:
        return []
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _interval_intersection_seconds(left, right):
    total = 0.0
    left_index = 0
    right_index = 0
    while left_index < len(left) and right_index < len(right):
        left_start, left_end = left[left_index]
        right_start, right_end = right[right_index]
        total += max(0.0, min(left_end, right_end) - max(left_start, right_start))
        if left_end <= right_end:
            left_index += 1
        else:
            right_index += 1
    return total


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


def _round_signed_seconds(value):
    if math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-12):
        return 0.0
    return round(value, 6)


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
    "SpeakerActivityInterval",
    "TranscriptSegment",
    "evaluate_live_speaker_evidence",
    "hypothesis_from_live_snapshot",
    "load_reference_jsonl",
    "score_live_speaker_accuracy",
    "speaker_activity_from_live_snapshot",
]
