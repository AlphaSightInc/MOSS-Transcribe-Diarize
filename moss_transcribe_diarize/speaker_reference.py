"""Validation primitives for versioned speaker-activity references."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from moss_transcribe_diarize.reference_jsonl import load_reference_records
from moss_transcribe_diarize.transcript_parser import parse_transcript

DEFAULT_MAX_SPEECH_RATE = 8.0
DEFAULT_MIN_ACOUSTIC_EXISTENCE_SCORE = 0.65
DEFAULT_ACOUSTIC_SLACK_SEC = 1.5
V2_SCHEMA = "moss-speaker-reference.v2"
ACOUSTIC_EVIDENCE_SCHEMA = "moss-speaker-reference-acoustic-existence.v1"
_TOKEN = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|[0-9]+[A-Za-z]*")
_SPOKEN_NUMBERS = {
    "2": ("two",),
    "1990s": ("nineteen", "nineties"),
    "2000s": ("two", "thousands"),
    "2004": ("two", "thousand", "four"),
    "2005": ("two", "thousand", "five"),
    "2006": ("two", "thousand", "six"),
    "2025": ("twenty", "twenty", "five"),
}
_SPELLED_ACRONYMS = {"AI", "HBO", "IPO", "JP"}


@dataclass(frozen=True)
class AcousticReferenceValidation:
    """The evidence binding and policy used to validate acoustic existence."""

    evidence_path: str | Path | None = None
    audio_path: str | Path | None = None
    expected_audio_sha256: str | None = None
    required: bool = False
    min_score: float = DEFAULT_MIN_ACOUSTIC_EXISTENCE_SCORE
    slack_sec: float = DEFAULT_ACOUSTIC_SLACK_SEC


@dataclass(frozen=True)
class AcousticMatch:
    score: float
    reference_recall: float
    asr_precision: float
    asr_text: str


def normalize_reference_text(text: str) -> str:
    """Return the exact MMS-FA word sequence used for alignment provenance."""

    source = text.replace("Google+", "Google plus").replace("google+", "google plus")
    normalized: list[str] = []
    for raw in _TOKEN.findall(source):
        compact = raw.replace("’", "'")
        if compact in _SPELLED_ACRONYMS:
            normalized.extend(compact.lower())
        elif compact.lower() == "2x":
            normalized.extend(("two", "x"))
        elif compact in _SPOKEN_NUMBERS:
            normalized.extend(_SPOKEN_NUMBERS[compact])
        else:
            normalized.append(compact.lower())
    return " ".join(normalized)


def validate_speaker_reference(
    path: str | Path,
    *,
    lineage_path: str | Path | None = None,
    max_speech_rate: float = DEFAULT_MAX_SPEECH_RATE,
    acoustic: AcousticReferenceValidation | None = None,
    audit_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate timing, transcript provenance, and optional immutable-v1 lineage."""

    source = Path(path)
    rows = load_reference_records(source)
    lineage = load_reference_records(Path(lineage_path)) if lineage_path is not None else None
    issues: list[dict[str, Any]] = []
    previous_end = -math.inf
    rates: list[float] = []
    acoustic_summary: dict[str, Any] | None = None
    audit_summary: dict[str, Any] | None = None

    for index, row in enumerate(rows, start=1):
        start, end, _speaker, text, _line_index = _reference_fields(row)
        if not _finite_number(start) or not _finite_number(end) or end <= start:
            issues.append({"code": "interval", "record": index})
            continue
        if start < previous_end:
            issues.append(
                {
                    "code": "monotonicity",
                    "record": index,
                    "start": start,
                    "previous_end": previous_end,
                }
            )
        previous_end = end

        if not isinstance(text, str) or not text.strip():
            issues.append({"code": "text", "record": index})
            continue
        transcript_start, transcript_end = _transcript_interval(row, start, end, index, issues)
        normalized = normalize_reference_text(text)
        words = normalized.split()
        rate = len(words) / (transcript_end - transcript_start)
        rates.append(rate)
        if rate > max_speech_rate:
            issues.append(
                {
                    "code": "speech_rate",
                    "record": index,
                    "words_per_sec": round(rate, 6),
                    "limit": max_speech_rate,
                }
            )

        if row.get("schema") == V2_SCHEMA:
            alignment = row.get("alignment")
            expected_hash = hashlib.sha256(normalized.encode()).hexdigest()
            if (
                not isinstance(alignment, dict)
                or alignment.get("normalized_text") != normalized
                or alignment.get("normalized_text_sha256") != expected_hash
                or alignment.get("word_count") != len(words)
            ):
                issues.append({"code": "text_alignment", "record": index})
            _validate_nonlexical_activity(
                row,
                activity_start=float(start),
                activity_end=float(end),
                transcript_start=transcript_start,
                issues=issues,
                record=index,
            )

    if lineage is not None:
        audit, audit_summary = _load_audit(
            Path(audit_path) if audit_path is not None else None,
            lineage_path=Path(lineage_path),
            issues=issues,
        )
        _validate_lineage(rows, lineage, audit=audit, issues=issues)

    if acoustic is not None and acoustic.evidence_path is not None:
        acoustic_summary = _validate_acoustic_existence(
            rows,
            evidence_path=Path(acoustic.evidence_path),
            audio_path=Path(acoustic.audio_path) if acoustic.audio_path is not None else None,
            expected_audio_sha256=acoustic.expected_audio_sha256,
            threshold=acoustic.min_score,
            slack_sec=acoustic.slack_sec,
            issues=issues,
        )
    elif acoustic is not None and acoustic.required:
        issues.append({"code": "acoustic_evidence_missing"})

    result = {
        "verdict": "PASS" if not issues else "FAIL",
        "reference": str(source.resolve()),
        "segment_count": len(rows),
        "max_speech_rate_words_per_sec": round(max(rates, default=0.0), 6),
        "speech_rate_limit_words_per_sec": max_speech_rate,
        "issues": issues,
    }
    if acoustic_summary is not None:
        result["acoustic_existence"] = acoustic_summary
    if audit_summary is not None:
        result["audit"] = audit_summary
    return result


def _load_audit(
    path: Path | None,
    *,
    lineage_path: Path,
    issues: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if path is None:
        return None, None
    try:
        audit = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append({"code": "audit_invalid", "detail": str(exc)})
        return None, {"accepted_edits": 0}
    if (
        not isinstance(audit, dict)
        or audit.get("schema") != "moss-speaker-reference-human-audit.v1"
        or audit.get("status") != "accepted"
        or not isinstance(audit.get("decisions"), list)
    ):
        issues.append({"code": "audit_schema"})
        return None, {"accepted_edits": 0}
    expected_candidate = hashlib.sha256(lineage_path.read_bytes()).hexdigest()
    if audit.get("candidate_reference_sha256") != expected_candidate:
        issues.append(
            {
                "code": "audit_candidate_hash",
                "actual": audit.get("candidate_reference_sha256"),
                "expected": expected_candidate,
            }
        )
    edits = sum(
        1 for decision in audit["decisions"] if decision.get("disposition") == "EDIT"
    )
    return audit, {
        "accepted_edits": edits,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _validate_lineage(
    rows: list[dict[str, Any]],
    lineage: list[dict[str, Any]],
    *,
    audit: dict[str, Any] | None,
    issues: list[dict[str, Any]],
) -> None:
    ancestors = {_reference_fields(row)[4]: row for row in lineage}
    descendants = {_reference_fields(row)[4]: row for row in rows}
    decisions = audit.get("decisions", []) if audit is not None else []
    edit_by_line = {
        line_index: decision
        for decision in decisions
        if decision.get("disposition") == "EDIT"
        for line_index in decision.get("line_indices", [])
    }
    absent_lines = {
        line_index
        for decision in decisions
        if decision.get("disposition") == "ABSENT"
        for line_index in decision.get("line_indices", [])
    }
    for index, row in enumerate(rows, start=1):
        _start, _end, speaker, text, line_index = _reference_fields(row)
        ancestor = ancestors.get(line_index)
        if ancestor is None:
            issues.append({"code": "text_lineage", "record": index})
            continue
        ancestor_fields = _reference_fields(ancestor)
        if speaker != ancestor_fields[2]:
            issues.append({"code": "text_lineage", "record": index})
            continue
        if text == ancestor_fields[3]:
            continue
        decision = edit_by_line.get(line_index)
        if (
            decision is None
            or decision.get("candidate_text") != ancestor_fields[3]
            or decision.get("post_audit_text") != text
        ):
            issues.append({"code": "text_lineage", "record": index})
    unexpected_missing = set(ancestors) - set(descendants) - absent_lines
    if unexpected_missing:
        issues.append(
            {
                "code": "lineage_count",
                "actual": len(rows),
                "expected": len(lineage),
                "missing_line_indices": sorted(unexpected_missing, key=str),
            }
        )


def _transcript_interval(
    row: dict[str, Any],
    activity_start: float,
    activity_end: float,
    record: int,
    issues: list[dict[str, Any]],
) -> tuple[float, float]:
    if row.get("schema") != V2_SCHEMA:
        return float(activity_start), float(activity_end)
    transcript = row.get("transcript")
    if not isinstance(transcript, dict):
        return float(activity_start), float(activity_end)
    has_start = "start" in transcript
    has_end = "end" in transcript
    if not has_start and not has_end:
        return float(activity_start), float(activity_end)
    start = transcript.get("start")
    end = transcript.get("end")
    if (
        not has_start
        or not has_end
        or not _finite_number(start)
        or not _finite_number(end)
        or float(end) <= float(start)
        or float(start) < float(activity_start)
        or float(end) > float(activity_end)
    ):
        issues.append({"code": "transcript_interval", "record": record})
        return float(activity_start), float(activity_end)
    return float(start), float(end)


def _validate_nonlexical_activity(
    row: dict[str, Any],
    *,
    activity_start: float,
    activity_end: float,
    transcript_start: float,
    issues: list[dict[str, Any]],
    record: int,
) -> None:
    nonlexical = row.get("nonlexical_activity")
    if nonlexical is None:
        return
    if (
        not isinstance(nonlexical, dict)
        or not _finite_number(nonlexical.get("start"))
        or not _finite_number(nonlexical.get("end"))
        or float(nonlexical["start"]) < activity_start
        or float(nonlexical["end"]) > activity_end
        or float(nonlexical["end"]) > transcript_start
        or float(nonlexical["end"]) <= float(nonlexical["start"])
        or nonlexical.get("kind") != "uncertain_prelexical_vocalization"
        or nonlexical.get("confirmed_lexical_text") is not None
    ):
        issues.append({"code": "nonlexical_activity", "record": record})


def _validate_acoustic_existence(
    rows: list[dict[str, Any]],
    *,
    evidence_path: Path,
    audio_path: Path | None,
    expected_audio_sha256: str | None,
    threshold: float,
    slack_sec: float,
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append({"code": "acoustic_evidence_invalid", "detail": str(exc)})
        return {"accepted": 0, "rejected": len(rows)}
    if not isinstance(evidence, dict) or evidence.get("schema") != ACOUSTIC_EVIDENCE_SCHEMA:
        issues.append({"code": "acoustic_evidence_schema"})
        return {"accepted": 0, "rejected": len(rows)}
    if evidence.get("blind_to_reference_transcript") is not True:
        issues.append({"code": "acoustic_evidence_not_independent"})

    declared_audio_sha = evidence.get("audio_sha256")
    bound_audio_sha = expected_audio_sha256
    if audio_path is not None:
        try:
            bound_audio_sha = hashlib.sha256(audio_path.read_bytes()).hexdigest()
        except OSError as exc:
            issues.append({"code": "acoustic_audio_unreadable", "detail": str(exc)})
    if bound_audio_sha is None:
        issues.append({"code": "acoustic_audio_unbound"})
    elif declared_audio_sha != bound_audio_sha:
        issues.append(
            {
                "code": "acoustic_audio_hash",
                "actual": declared_audio_sha,
                "expected": bound_audio_sha,
            }
        )

    segments = _acoustic_segments(evidence, issues)
    accepted = 0
    rejected = 0
    records: list[dict[str, Any]] = []
    for record_number, row in enumerate(rows, start=1):
        start, end, _speaker, text, line_index = _reference_fields(row)
        if not _finite_number(start) or not _finite_number(end) or not isinstance(text, str):
            continue
        transcript_start, transcript_end = _transcript_interval(
            row,
            float(start),
            float(end),
            record_number,
            issues,
        )
        evaluation = acoustic_existence_evaluation(
            start=transcript_start,
            end=transcript_end,
            text=text,
            segments=segments,
            slack_sec=slack_sec,
        )
        evaluation.update({"record": record_number, "line_index": line_index})
        records.append(evaluation)
        if evaluation["score"] >= threshold:
            accepted += 1
        else:
            rejected += 1
            issues.append(
                {
                    "code": "acoustic_existence",
                    "record": record_number,
                    "line_index": line_index,
                    "score": evaluation["score"],
                    "threshold": threshold,
                    "asr_text": evaluation["asr_text"],
                }
            )

    return {
        "accepted": accepted,
        "rejected": rejected,
        "threshold": threshold,
        "slack_sec": slack_sec,
        "audio_sha256": declared_audio_sha,
        "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        "records": records,
    }


def acoustic_existence_evaluation(
    *,
    start: float,
    end: float,
    text: str,
    segments: list[dict[str, Any]],
    slack_sec: float = DEFAULT_ACOUSTIC_SLACK_SEC,
) -> dict[str, Any]:
    """Score reference text against a local window from an independent ASR pass.

    The best local token alignment may omit up to four reference tokens, so this
    is deletion-capable and never assumes every proposed transcript token exists.
    """

    reference_tokens = normalize_reference_text(text).split()
    nearby_text = " ".join(
        str(segment["text"])
        for segment in segments
        if float(segment["end"]) >= start - slack_sec
        and float(segment["start"]) <= end + slack_sec
    )
    asr_tokens = normalize_reference_text(nearby_text).split()
    if not reference_tokens or not asr_tokens:
        return {
            "score": 0.0,
            "reference_recall": 0.0,
            "asr_precision": 0.0,
            "asr_text": "",
        }

    best = AcousticMatch(0.0, 0.0, 0.0, "")
    minimum_width = max(1, len(reference_tokens) - 4)
    maximum_width = min(len(asr_tokens), len(reference_tokens) + 4)
    for width in range(minimum_width, maximum_width + 1):
        for first in range(0, len(asr_tokens) - width + 1):
            window = asr_tokens[first : first + width]
            matches = sum(
                block.size
                for block in SequenceMatcher(
                    None, reference_tokens, window, autojunk=False
                ).get_matching_blocks()
            )
            recall = matches / len(reference_tokens)
            precision = matches / len(window)
            score = 0.0 if not matches else 2.0 * recall * precision / (recall + precision)
            if score > best.score:
                best = AcousticMatch(score, recall, precision, " ".join(window))
    return {
        "score": round(best.score, 6),
        "reference_recall": round(best.reference_recall, 6),
        "asr_precision": round(best.asr_precision, 6),
        "asr_text": best.asr_text,
    }


def _acoustic_segments(
    evidence: dict[str, Any], issues: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    raw_segments = evidence.get("segments")
    if raw_segments is None and isinstance(evidence.get("transcript"), str):
        raw_segments = [
            {
                "start": segment.start,
                "end": segment.end,
                "speaker": segment.speaker,
                "text": segment.text,
            }
            for segment in parse_transcript(evidence["transcript"])
        ]
    if not isinstance(raw_segments, list) or not raw_segments:
        issues.append({"code": "acoustic_evidence_segments"})
        return []
    segments: list[dict[str, Any]] = []
    for index, segment in enumerate(raw_segments, start=1):
        if (
            not isinstance(segment, dict)
            or not _finite_number(segment.get("start"))
            or not _finite_number(segment.get("end"))
            or float(segment["end"]) < float(segment["start"])
            or not isinstance(segment.get("text"), str)
        ):
            issues.append({"code": "acoustic_evidence_segment", "record": index})
            continue
        segments.append(segment)
    return segments


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )


def _reference_fields(row: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    if row.get("schema") != V2_SCHEMA:
        return (
            row.get("start"),
            row.get("end"),
            row.get("speaker"),
            row.get("text"),
            row.get("line_index"),
        )
    activity = row.get("speaker_activity")
    transcript = row.get("transcript")
    if not isinstance(activity, dict) or not isinstance(transcript, dict):
        return None, None, None, None, None
    return (
        activity.get("start"),
        activity.get("end"),
        activity.get("speaker"),
        transcript.get("text"),
        transcript.get("line_index"),
    )


__all__ = [
    "ACOUSTIC_EVIDENCE_SCHEMA",
    "AcousticReferenceValidation",
    "DEFAULT_ACOUSTIC_SLACK_SEC",
    "DEFAULT_MIN_ACOUSTIC_EXISTENCE_SCORE",
    "DEFAULT_MAX_SPEECH_RATE",
    "V2_SCHEMA",
    "acoustic_existence_evaluation",
    "normalize_reference_text",
    "validate_speaker_reference",
]
