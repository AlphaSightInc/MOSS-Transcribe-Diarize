from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from scipy.optimize import linear_sum_assignment

from moss_transcribe_diarize.transcript_parser import TranscriptSegment, parse_transcript

from .live_session import (
    FrozenSpan,
    LIVE_SAMPLE_RATE,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    PCM16_BYTES_PER_SAMPLE,
)


class LiveIdentityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LiveIdentityConfig:
    max_speakers: int
    min_match_score: float
    min_match_margin: float

    def __post_init__(self) -> None:
        if self.max_speakers <= 0:
            raise ValueError("max_speakers must be positive.")
        if not 0.0 <= self.min_match_score <= 1.0:
            raise ValueError("min_match_score must be between 0 and 1.")
        if self.min_match_margin < 0.0:
            raise ValueError("min_match_margin must be non-negative.")


@dataclass(frozen=True, slots=True)
class LiveSpeakerEvidence:
    local_speaker: str
    canonical_speaker: str
    score: float
    evidence_id: str = ""


class LiveSpeakerEvidenceProvider(Protocol):
    def score(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        segments: tuple[TranscriptSegment, ...],
        base_snapshot: LiveIdentitySnapshot,
    ) -> tuple[LiveSpeakerEvidence, ...]:
        ...


class NoLiveSpeakerEvidence:
    def score(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        segments: tuple[TranscriptSegment, ...],
        base_snapshot: LiveIdentitySnapshot,
    ) -> tuple[LiveSpeakerEvidence, ...]:
        del span, pcm, segments, base_snapshot
        return ()


class BoundedCausalIdentityPreparer:
    """Pure live identity preparer; it proposes state but never mutates a session."""

    def __init__(
        self,
        *,
        config: LiveIdentityConfig,
        evidence_provider: LiveSpeakerEvidenceProvider | None = None,
    ):
        self.config = config
        self.evidence_provider = evidence_provider or NoLiveSpeakerEvidence()

    def prepare(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        transcript: str,
        base_snapshot: LiveIdentitySnapshot,
    ) -> LiveIdentityPreparation:
        expected_pcm_bytes = span.sample_count * PCM16_BYTES_PER_SAMPLE
        if len(pcm) != expected_pcm_bytes:
            return self._failed(span, transcript, base_snapshot, "pcm_span_mismatch")

        segments = tuple(parse_transcript(transcript))
        if not segments:
            return self._failed(span, transcript, base_snapshot, "unparseable_transcript")

        duration = span.sample_count / float(LIVE_SAMPLE_RATE)
        if any(segment.start < 0 or segment.end > duration for segment in segments):
            return self._failed(span, transcript, base_snapshot, "timestamp_outside_span")

        local_speakers = _local_speakers(segments)
        if len(local_speakers) > self.config.max_speakers:
            return self._abstain(span, transcript, base_snapshot, "speaker_capacity_exceeded", local_speakers)

        try:
            evidence = self.evidence_provider.score(
                span=span,
                pcm=pcm,
                segments=segments,
                base_snapshot=base_snapshot,
            )
        except Exception as exc:
            return self._failed(span, transcript, base_snapshot, f"evidence_provider_failed:{exc.__class__.__name__}")

        try:
            mapping = self._assign(local_speakers, base_snapshot.canonical_speakers, evidence)
        except LiveIdentityError as exc:
            return self._abstain(span, transcript, base_snapshot, str(exc), local_speakers)

        assigned = dict(mapping)
        existing_count = len(base_snapshot.canonical_speakers)
        births = [local for local in local_speakers if local not in assigned]
        if existing_count + len(births) > self.config.max_speakers:
            return self._abstain(span, transcript, base_snapshot, "speaker_capacity_exceeded", local_speakers)

        new_speakers = _next_speaker_ids(base_snapshot.canonical_speakers, len(births))
        for local, canonical in zip(births, new_speakers, strict=True):
            assigned[local] = canonical

        canonical_speakers = base_snapshot.canonical_speakers + new_speakers
        relabeled = _render_transcript(segments, assigned, canonical_speakers)
        diagnostics = _diagnostics(
            status="prepared",
            reason="ok",
            span=span,
            local_speakers=local_speakers,
            assignments=assigned,
            canonical_speakers=canonical_speakers,
        )
        snapshot = LiveIdentitySnapshot(
            version=base_snapshot.version + 1,
            canonical_speakers=canonical_speakers,
            diagnostics=diagnostics,
        )
        return LiveIdentityPreparation(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            base_snapshot_version=base_snapshot.version,
            proposed_snapshot=snapshot,
            relabeled_transcript=relabeled,
        )

    def _assign(
        self,
        local_speakers: tuple[str, ...],
        canonical_speakers: tuple[str, ...],
        evidence: tuple[LiveSpeakerEvidence, ...],
    ) -> tuple[tuple[str, str], ...]:
        if not local_speakers or not canonical_speakers:
            return ()

        score_by_pair = _score_by_pair(local_speakers, canonical_speakers, evidence)
        matrix = [
            [-score_by_pair.get((local, canonical), 0.0) for canonical in canonical_speakers]
            for local in local_speakers
        ]
        row_indexes, column_indexes = linear_sum_assignment(matrix)
        assigned_rows: set[int] = set()
        mapping: list[tuple[str, str]] = []
        for row_index, column_index in sorted(zip(row_indexes, column_indexes, strict=True)):
            local = local_speakers[row_index]
            canonical = canonical_speakers[column_index]
            score = score_by_pair.get((local, canonical), 0.0)
            if score < self.config.min_match_score:
                continue
            rejection_reason = self._match_rejection_reason(
                row_index,
                column_index,
                local_speakers,
                canonical_speakers,
                score_by_pair,
            )
            if rejection_reason is not None:
                raise LiveIdentityError(rejection_reason)
            assigned_rows.add(row_index)
            mapping.append((local, canonical))

        for row_index, local in enumerate(local_speakers):
            if row_index in assigned_rows:
                continue
            if max((score_by_pair.get((local, canonical), 0.0) for canonical in canonical_speakers), default=0.0) >= (
                self.config.min_match_score
            ):
                raise LiveIdentityError("same_span_cannot_link_conflict")
        return tuple(mapping)

    def _match_rejection_reason(
        self,
        row_index: int,
        column_index: int,
        local_speakers: tuple[str, ...],
        canonical_speakers: tuple[str, ...],
        score_by_pair: dict[tuple[str, str], float],
    ) -> str | None:
        local = local_speakers[row_index]
        canonical = canonical_speakers[column_index]
        score = score_by_pair.get((local, canonical), 0.0)
        row_runner = max(
            (
                score_by_pair.get((local, other), 0.0)
                for col, other in enumerate(canonical_speakers)
                if col != column_index
            ),
            default=0.0,
        )
        column_runner = max(
            (
                score_by_pair.get((other, canonical), 0.0)
                for row, other in enumerate(local_speakers)
                if row != row_index
            ),
            default=0.0,
        )
        if score - column_runner < self.config.min_match_margin:
            return "same_span_cannot_link_conflict"
        if score - row_runner < self.config.min_match_margin:
            return "ambiguous_identity"
        return None

    def _failed(
        self,
        span: FrozenSpan,
        transcript: str,
        base_snapshot: LiveIdentitySnapshot,
        reason: str,
    ) -> LiveIdentityPreparation:
        return _non_prepared(span, transcript, base_snapshot, status="failed", reason=reason)

    def _abstain(
        self,
        span: FrozenSpan,
        transcript: str,
        base_snapshot: LiveIdentitySnapshot,
        reason: str,
        local_speakers: tuple[str, ...],
    ) -> LiveIdentityPreparation:
        diagnostics = _diagnostics(
            status="abstain",
            reason=reason,
            span=span,
            local_speakers=local_speakers,
            assignments={},
            canonical_speakers=base_snapshot.canonical_speakers,
        )
        return _non_prepared(span, transcript, base_snapshot, status="abstain", reason=reason, diagnostics=diagnostics)


def _non_prepared(
    span: FrozenSpan,
    transcript: str,
    base_snapshot: LiveIdentitySnapshot,
    *,
    status: str,
    reason: str,
    diagnostics: tuple[tuple[str, str], ...] | None = None,
) -> LiveIdentityPreparation:
    snapshot = LiveIdentitySnapshot(
        version=base_snapshot.version,
        canonical_speakers=base_snapshot.canonical_speakers,
        diagnostics=diagnostics or (("status", status), ("reason", reason), ("span_id", str(span.id))),
    )
    return LiveIdentityPreparation(
        span_id=span.id,
        epoch=span.epoch,
        start_sample=span.start_sample,
        end_sample=span.end_sample,
        base_snapshot_version=base_snapshot.version,
        proposed_snapshot=snapshot,
        relabeled_transcript=transcript,
        status=status,
        reason=reason,
    )


def _score_by_pair(
    local_speakers: tuple[str, ...],
    canonical_speakers: tuple[str, ...],
    evidence: tuple[LiveSpeakerEvidence, ...],
) -> dict[tuple[str, str], float]:
    local_set = set(local_speakers)
    canonical_set = set(canonical_speakers)
    scores: dict[tuple[str, str], float] = {}
    for item in evidence:
        if item.local_speaker not in local_set or item.canonical_speaker not in canonical_set:
            continue
        if not math.isfinite(item.score) or item.score < 0.0 or item.score > 1.0:
            raise LiveIdentityError("invalid_identity_evidence")
        key = (item.local_speaker, item.canonical_speaker)
        scores[key] = max(scores.get(key, 0.0), item.score)
    return scores


def _local_speakers(segments: tuple[TranscriptSegment, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    speakers: list[str] = []
    for segment in segments:
        if segment.speaker not in seen:
            seen.add(segment.speaker)
            speakers.append(segment.speaker)
    return tuple(speakers)


def _next_speaker_ids(existing: tuple[str, ...], count: int) -> tuple[str, ...]:
    ids: list[str] = []
    next_index = 1
    while len(ids) < count:
        candidate = f"speaker-{next_index:04d}"
        next_index += 1
        if candidate in existing or candidate in ids:
            continue
        ids.append(candidate)
    return tuple(ids)


def _display_label(canonical: str, canonical_speakers: tuple[str, ...]) -> str:
    return f"S{canonical_speakers.index(canonical) + 1:02d}"


def _render_transcript(
    segments: tuple[TranscriptSegment, ...],
    assignments: dict[str, str],
    canonical_speakers: tuple[str, ...],
) -> str:
    parts: list[str] = []
    for segment in segments:
        canonical = assignments[segment.speaker]
        speaker = _display_label(canonical, canonical_speakers)
        parts.append(f"[{_fmt_time(segment.start)}][{speaker}]{segment.text}[{_fmt_time(segment.end)}]")
    return "".join(parts)


def _fmt_time(value: float) -> str:
    return f"{value:g}"


def _diagnostics(
    *,
    status: str,
    reason: str,
    span: FrozenSpan,
    local_speakers: tuple[str, ...],
    assignments: dict[str, str],
    canonical_speakers: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    assignment_text = ",".join(f"{local}->{assignments[local]}" for local in sorted(assignments))
    return (
        ("schema_version", "1"),
        ("status", status),
        ("reason", reason),
        ("span_id", str(span.id)),
        ("span_samples", f"{span.start_sample}:{span.end_sample}"),
        ("local_speakers", ",".join(local_speakers)),
        ("assignments", assignment_text),
        ("canonical_speakers", ",".join(canonical_speakers)),
    )


__all__ = [
    "BoundedCausalIdentityPreparer",
    "LiveIdentityConfig",
    "LiveIdentityError",
    "LiveSpeakerEvidence",
    "LiveSpeakerEvidenceProvider",
    "NoLiveSpeakerEvidence",
]
