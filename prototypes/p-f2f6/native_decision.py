"""Prototype native terminal decision returning immutable diagnostics with its result."""

from __future__ import annotations

import json
from collections import defaultdict

from moss_transcribe_diarize.app.live_identity import (
    BoundedCausalIdentityPreparer,
    LiveIdentityConfig,
    LiveSpeakerEvidence,
)
from moss_transcribe_diarize.app.live_session import FrozenSpan, LiveIdentitySnapshot
from moss_transcribe_diarize.app.live_span_bounds import render_segments, span_segments
from moss_transcribe_diarize.app.live_transcript_convergence import resolve_segment_overlaps
from moss_transcribe_diarize.transcript_parser import TranscriptSegment

from records import (
    NativeDecisionResult,
    NormalizedPartitionRecord,
    RawTerminalSpan,
    RawToNormalized,
    SCHEMA_VERSION,
    TerminalDecisionDiagnostics,
)


RATE = 16_000
ELIGIBILITY_FLOOR_SAMPLES = 8_000
ADAM = "speaker-0001"
MEETING_OWNER = "account-7/meeting-19"
RUN_OWNER = "s17/identity-gap"
CONTAINED_TRANSCRIPT = "[0][S01]outer evidence[2][0.5][S02]contained brief span[0.77]"


class DeterministicEvidence:
    """Production preparer protocol with explicit, retained score evidence."""

    min_segment_samples = ELIGIBILITY_FLOOR_SAMPLES

    def __init__(self, score: float = 0.909091):
        self.score_value = score
        self.last_scores: tuple[LiveSpeakerEvidence, ...] = ()

    def revision_reader(self):
        return self

    def score(self, *, span, pcm, segments, base_snapshot):
        del pcm, base_snapshot
        if span.sample_count < self.min_segment_samples:
            self.last_scores = ()
            return ()
        self.last_scores = tuple(
            LiveSpeakerEvidence(segment.speaker, ADAM, self.score_value)
            for segment in segments
        )
        return self.last_scores


def _raw_spans(transcript: str, end_sample: int):
    parsed = tuple(span_segments(transcript, sample_count=end_sample))
    records = tuple(
        RawTerminalSpan(
            raw_index=index,
            terminal_local_label=segment.speaker,
            start=round(segment.start * RATE),
            end=round(segment.end * RATE),
            samples=round((segment.end - segment.start) * RATE),
        )
        for index, segment in enumerate(parsed)
    )
    placed = tuple(
        (record.terminal_local_label, record.start, record.end, parsed[index].text)
        for index, record in enumerate(records)
    )
    return records, placed


def _mapping(raw_spans, normalized_segments):
    rows = []
    for raw in raw_spans:
        matches = [
            segment
            for segment in normalized_segments
            if segment[0] == raw.terminal_local_label
            and min(raw.end, segment[2]) > max(raw.start, segment[1])
        ]
        if not matches:
            rows.append(RawToNormalized(raw.raw_index, None, "dropped_by_normalization"))
            continue
        exact = any((raw.start, raw.end) == (segment[1], segment[2]) for segment in matches)
        disposition = "survived" if exact else "merged_or_displaced"
        rows.append(
            RawToNormalized(
                raw.raw_index,
                f"system:{raw.terminal_local_label}",
                disposition,
            )
        )
    return tuple(rows)


def decide(
    transcript: str = CONTAINED_TRANSCRIPT,
    *,
    meeting_owner: str = MEETING_OWNER,
    run_owner: str = RUN_OWNER,
) -> NativeDecisionResult:
    """Run the real resolver and preparer, returning publication plus diagnostics."""

    end_sample = round(2.5 * RATE)
    raw_spans, placed = _raw_spans(transcript, end_sample)
    resolution = resolve_segment_overlaps(placed)
    mapping = _mapping(raw_spans, resolution.segments)
    mapped_raw_by_label: dict[str, list[int]] = defaultdict(list)
    for raw, mapped in zip(raw_spans, mapping, strict=True):
        if mapped.normalized_partition_id is not None:
            mapped_raw_by_label[raw.terminal_local_label].append(raw.raw_index)

    normalized_records = []
    published = []
    for partition_index, label in enumerate(
        dict.fromkeys(segment[0] for segment in resolution.segments)
    ):
        members = tuple(segment for segment in resolution.segments if segment[0] == label)
        start = min(segment[1] for segment in members)
        end = max(segment[2] for segment in members)
        span = FrozenSpan(
            id=100 + partition_index,
            epoch=0,
            start_sample=start,
            end_sample=end,
            reason="terminal_partition_probe",
        )
        relative = render_segments(
            (
                TranscriptSegment(
                    start=(segment_start - start) / RATE,
                    end=(segment_end - start) / RATE,
                    speaker=label,
                    text=text,
                )
                for _, segment_start, segment_end, text in members
            ),
            lambda segment: segment.speaker,
        )
        provider = DeterministicEvidence()
        preparer = BoundedCausalIdentityPreparer(
            config=LiveIdentityConfig(16, 0.35, 0.1),
            evidence_provider=provider,
        )
        preparation = preparer.prepare_revision(
            span=span,
            pcm=bytes([1]) * span.sample_count * 2,
            transcript=relative,
            base_snapshot=LiveIdentitySnapshot(canonical_speakers=(ADAM,)),
            allowed_speakers=(ADAM,),
        )
        assignments = dict(preparation.proposed_snapshot.diagnostics).get(
            "assignments", ""
        )
        published_identity = ADAM if f"{label}->{ADAM}" in assignments else None
        score_by_canonical = tuple(
            sorted(
                {
                    evidence.canonical_speaker: float(evidence.score)
                    for evidence in provider.last_scores
                }.items()
            )
        )
        ranked = sorted((score for _, score in score_by_canonical), reverse=True)
        margin = None if not ranked else ranked[0] - (ranked[1] if len(ranked) > 1 else 0.0)
        partition_id = f"system:{label}"
        normalized_records.append(
            NormalizedPartitionRecord(
                schema_version=SCHEMA_VERSION,
                meeting_owner=meeting_owner,
                run_owner=run_owner,
                partition_id=partition_id,
                terminal_local_label=label,
                member_raw_indexes=tuple(mapped_raw_by_label[label]),
                start=start,
                end=end,
                samples=end - start,
                eligibility_floor_samples=ELIGIBILITY_FLOOR_SAMPLES,
                eligible=(end - start) >= ELIGIBILITY_FLOOR_SAMPLES,
                score_by_canonical=score_by_canonical,
                margin=margin,
                decision=(
                    "matched_existing"
                    if published_identity is not None
                    else "identity_abstained"
                ),
                published_identity=published_identity,
            )
        )
        published.extend(
            {
                "start": segment_start,
                "end": segment_end,
                "text": text,
                "canonical_speaker": published_identity,
            }
            for _, segment_start, segment_end, text in members
        )

    proposal_bytes = json.dumps(
        published, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return NativeDecisionResult(
        published_proposal_bytes=proposal_bytes,
        diagnostics=TerminalDecisionDiagnostics(
            raw_spans=raw_spans,
            raw_to_normalized=mapping,
            normalized_partitions=tuple(normalized_records),
        ),
    )
