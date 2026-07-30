from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from scipy.optimize import linear_sum_assignment

from moss_transcribe_diarize.transcript_parser import TranscriptSegment

from .live_session import (
    FrozenSpan,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    PCM16_BYTES_PER_SAMPLE,
    UNATTRIBUTED_SPEAKER,
    display_speaker_label,
)
from .live_span_bounds import render_segments, span_segments

if TYPE_CHECKING:  # pragma: no cover - typing only, and importing it for real would cycle
    from .live_identity_sweep import SweepRevision


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

        # Segments are clamped into the span, not refused for leaving it -- see
        # `live_span_bounds`. Everything downstream (evidence scoring, the relabeled
        # transcript this preparation publishes) therefore sees timestamps the span holds.
        segments = span_segments(transcript, sample_count=span.sample_count)
        if not segments:
            return self._failed(span, transcript, base_snapshot, "unparseable_transcript")

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
        candidates = tuple(local for local in local_speakers if local not in assigned)
        try:
            deferred = self._deferred_births(span=span, candidates=candidates)
        except Exception as exc:
            return self._failed(span, transcript, base_snapshot, f"birth_evidence_failed:{exc.__class__.__name__}")
        births = [local for local in candidates if local not in deferred]
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
            deferred_births=deferred,
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

    def take_identity_revision(self) -> "SweepRevision | None":
        """Any retrospective correction the evidence provider has ready, or `None`.

        The capability is optional at every layer for one reason: an identity stack with no
        album has no sweeper, has retained nothing, and therefore has nothing to say about a
        span it has already answered. `NoLiveSpeakerEvidence` is that stack, and so is every
        test double -- so this asks rather than requires, exactly as the album and the sweeper
        are collaborators the provider may not have.
        """

        take = getattr(self.evidence_provider, "take_identity_revision", None)
        return None if take is None else take()

    def finalize_identity(self, *, base_snapshot: LiveIdentitySnapshot) -> None:
        """Tell the evidence provider the meeting has ended, if it has anything to settle.

        Relayed rather than implemented for the same reason `take_identity_revision` is: the
        preparer is pure and holds no evidence, so what a session end means is entirely the
        provider's business. Asked for by name, because the stacks that predate ADR-0002
        step 3 -- `NoLiveSpeakerEvidence` and every hand-built double -- have nothing to
        settle and must not have to say so.
        """

        finalize = getattr(self.evidence_provider, "finalize_identity", None)
        if finalize is not None:
            finalize(base_snapshot=base_snapshot)

    def _deferred_births(
        self,
        *,
        span: FrozenSpan,
        candidates: tuple[str, ...],
    ) -> dict[str, float]:
        """Candidate births the evidence layer will not enrol, each with the seconds behind it.

        Candidate 55: **a birth must not be minted from audio the system refused to embed.**
        14 of one certification run's 16 canonical speakers, and 13 of another's, were born
        from spans where no segment cleared the evidence floor -- so the encoder was never
        asked for a vector, the album has nothing to enrol, and the new speaker exists only as
        a capacity slot that no later span can match against. Sixteen canonical speakers for
        two voices is what that costs, reached inside the first minute.

        The floor is asked of the provider rather than held here because the evidence duration
        lives there. Phase N deliberately separates its 1.0 s birth floor from the album's
        2.0 s enrollment floor: 9-clip real replay showed that coupling both at 2.0 s collapses
        a cold-start clip. What this class keeps is what a deferral *means*, which is the half
        that belongs to birth.

        Asked by name, exactly as `take_identity_revision` and `finalize_identity` are: a
        stack with no album -- `NoLiveSpeakerEvidence`, the pre-ADR-0002 overwrite policy,
        every test double -- has no admission gate, has refused nothing, and must keep
        birthing as it always did rather than lose every label to a floor nothing enforces.
        """

        if not candidates:
            return {}
        deferrals = getattr(self.evidence_provider, "birth_deferrals", None)
        if deferrals is None:
            return {}
        return dict(deferrals(span_id=span.id, candidates=candidates))

    def _assign(
        self,
        local_speakers: tuple[str, ...],
        canonical_speakers: tuple[str, ...],
        evidence: tuple[LiveSpeakerEvidence, ...],
    ) -> tuple[tuple[str, str], ...]:
        return assign_speakers(
            local_speakers=local_speakers,
            canonical_speakers=canonical_speakers,
            evidence=evidence,
            config=self.config,
        )

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


def assign_speakers(
    *,
    local_speakers: tuple[str, ...],
    canonical_speakers: tuple[str, ...],
    evidence: tuple[LiveSpeakerEvidence, ...],
    config: LiveIdentityConfig,
) -> tuple[tuple[str, str], ...]:
    """One span's local speakers matched one-to-one onto canonical ones, or an ambiguity.

    This is the matcher, and it is deliberately a free function rather than a method: a
    retrospective sweep re-matches historical spans against a better album, and it has to reach
    the *same* verdicts the live path reached or a "correction" is just a second opinion from a
    second implementation. `tests/live_identity_accuracy.py` exists because ADR-0002's own
    prototype numbers came from a re-implemented matcher; nothing else in this repository may
    repeat that.

    Raises `LiveIdentityError` naming the ambiguity. The live path turns that into an abstain
    for the whole span; a sweep turns it into "this span keeps the labels it has". Both are the
    same ruling -- an ambiguous span is not relabelled -- taken at different times.
    """

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
        if score < config.min_match_score:
            continue
        rejection_reason = _match_rejection_reason(
            row_index,
            column_index,
            local_speakers,
            canonical_speakers,
            score_by_pair,
            config,
        )
        if rejection_reason is not None:
            raise LiveIdentityError(rejection_reason)
        assigned_rows.add(row_index)
        mapping.append((local, canonical))

    for row_index, local in enumerate(local_speakers):
        if row_index in assigned_rows:
            continue
        if max((score_by_pair.get((local, canonical), 0.0) for canonical in canonical_speakers), default=0.0) >= (
            config.min_match_score
        ):
            raise LiveIdentityError("same_span_cannot_link_conflict")
    return tuple(mapping)


def _match_rejection_reason(
    row_index: int,
    column_index: int,
    local_speakers: tuple[str, ...],
    canonical_speakers: tuple[str, ...],
    score_by_pair: dict[tuple[str, str], float],
    config: LiveIdentityConfig,
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
    if score - column_runner < config.min_match_margin:
        return "same_span_cannot_link_conflict"
    if score - row_runner < config.min_match_margin:
        return "ambiguous_identity"
    return None


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


def unattributed_transcript(transcript: str, *, sample_count: int) -> str:
    """Render a span's words with no speaker attributed to any of them.

    This is what a span publishes when identity did not resolve -- an abstention, or a
    preparer that could not obtain evidence. The words are kept because they are the
    meeting; the labels are dropped because the decoder's `S01` is local to one span and
    means nothing across spans, so publishing it as canonical would assert a link the
    session declined to make. Timestamps go through the same span bound as every other
    published segment, so an unattributed span is no less honest about what it holds.

    Returns `""` for a transcript that parses to nothing; the caller decides what a span
    with no words publishes, exactly as `span_segments` leaves that question open.
    """

    return render_segments(
        span_segments(transcript, sample_count=sample_count),
        lambda segment: UNATTRIBUTED_SPEAKER,
    )


def _render_transcript(
    segments: tuple[TranscriptSegment, ...],
    assignments: dict[str, str],
    canonical_speakers: tuple[str, ...],
) -> str:
    """The span's words under the canonical labels it established, and `S00` for the rest.

    A local speaker with no assignment is a *deferred birth*: too little embedded speech to
    become a canonical speaker, and no existing one it matched. Its words are published
    exactly as an abstention publishes them -- kept, attributed to nobody -- because identity
    answers *who*, never *whether* (J2). Deferring per speaker rather than abstaining for the
    whole span is what keeps a two-voice span's confident match when the other voice is one
    fragment: an abstain would drop a label the session had every reason to write.
    """

    return render_segments(
        segments,
        lambda segment: (
            display_speaker_label(assignments[segment.speaker], canonical_speakers)
            if segment.speaker in assignments
            else UNATTRIBUTED_SPEAKER
        ),
    )


def _diagnostics(
    *,
    status: str,
    reason: str,
    span: FrozenSpan,
    local_speakers: tuple[str, ...],
    assignments: dict[str, str],
    canonical_speakers: tuple[str, ...],
    deferred_births: dict[str, float] | None = None,
) -> tuple[tuple[str, str], ...]:
    assignment_text = ",".join(f"{local}->{assignments[local]}" for local in sorted(assignments))
    # Named with the seconds that earned the refusal, because a deferral that recorded only
    # "deferred" would leave a reader unable to tell a voice the evidence floor skipped
    # entirely (0.000) from one that missed admission by a tenth of a second.
    deferred_text = ",".join(
        f"{local}={deferred_births[local]:.3f}" for local in sorted(deferred_births or {})
    )
    return (
        ("schema_version", "1"),
        ("status", status),
        ("reason", reason),
        ("span_id", str(span.id)),
        ("span_samples", f"{span.start_sample}:{span.end_sample}"),
        ("local_speakers", ",".join(local_speakers)),
        ("assignments", assignment_text),
        ("deferred_births", deferred_text),
        ("canonical_speakers", ",".join(canonical_speakers)),
    )


__all__ = [
    "BoundedCausalIdentityPreparer",
    "LiveIdentityConfig",
    "LiveIdentityError",
    "LiveSpeakerEvidence",
    "LiveSpeakerEvidenceProvider",
    "NoLiveSpeakerEvidence",
    "assign_speakers",
    "unattributed_transcript",
]
