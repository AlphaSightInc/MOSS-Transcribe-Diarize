"""Source-lane decoding; concurrent terminal jobs reuse lane-scoped voice evidence."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from moss_transcribe_diarize.transcript_parser import TranscriptSegment
from .live_span_bounds import span_segments, render_segments
from .live_session import LiveIdentityPreparation, LiveIdentitySnapshot, FrozenSpan
from .live_adapters import (
    InferenceTranscript,
    LiveProviderError,
    LiveProviderTransientError,
)
from .live_identity import unattributed_transcript

LANES = ("system", "microphone")


def order(s):
    return s.start_sample, LANES.index(s.source_lane), s.end_sample


def prepare_lanes(c, work, on_decoded):
    from .live_coordinator import CoordinatorPreparedWork

    span = work.span
    base = work.base_snapshot
    speakers = base.canonical_speakers
    assignments = []
    new_speaker_lanes = []
    failures = []
    answered = False
    placed = []
    elapsed = 0.0
    decoded = []
    # Namespaced local labels are internal addresses, never public speaker IDs.
    for index, lane in enumerate(LANES):
        pcm = dict(work.lane_pcm).get(lane, b"")
        if not any(pcm):
            continue
        try:
            inferred = c._decode(span, pcm)
        except LiveProviderError as exc:
            failures.append((lane, exc))
            continue
        answered = True
        elapsed += inferred.elapsed_sec or 0.0
        parsed = span_segments(inferred.transcript, sample_count=span.sample_count)
        if not parsed:
            continue
        parsed = tuple(replace(s, speaker=f"S{index+1}{s.speaker[1:]}") for s in parsed)
        text = render_segments(parsed, lambda s: s.speaker)
        decoded.append((index, lane, pcm, parsed, text))
    if on_decoded and decoded:
        preview = sorted(
            (
                (part.start, index, part.end, part)
                for index, _, _, parsed, _ in decoded
                for part in parsed
            ),
            key=lambda row: row[:3],
        )
        on_decoded(
            span,
            render_segments((row[3] for row in preview), lambda part: part.speaker),
        )
    for index, lane, pcm, parsed, text in decoded:
        if lane not in c._lane_preparers:
            c._lane_preparers[lane] = c.identity_preparer.fork_lane()
        preparer = c._lane_preparers[lane]
        own = c._lane_speakers.get(lane, set())
        current = replace(base, canonical_speakers=speakers)
        prep = preparer.prepare(
            span=span,
            pcm=pcm,
            transcript=text,
            base_snapshot=current,
            allowed_speakers=tuple(s for s in speakers if s in own),
        )
        if prep.status == "prepared":
            new = set(prep.proposed_snapshot.canonical_speakers) - set(speakers)
            new_speaker_lanes.extend((speaker, lane) for speaker in sorted(new))
            speakers = prep.proposed_snapshot.canonical_speakers
            diag = dict(prep.proposed_snapshot.diagnostics)
            assignments.extend(filter(None, diag.get("assignments", "").split(",")))
            out = prep.relabeled_transcript
        else:
            out = unattributed_transcript(text, sample_count=span.sample_count)
        for local, published in zip(
            parsed, span_segments(out, sample_count=span.sample_count)
        ):
            placed.append((published.start, index, published.end, published, local))
    if failures and not answered:
        first = failures[0][1]
        if all(isinstance(exc, LiveProviderTransientError) for _, exc in failures):
            return c._unanswered_span(span, first)
        raise first
    c._consecutive_unanswered_spans = 0
    placed.sort(key=lambda x: x[:3])
    if not placed:
        return CoordinatorPreparedWork(
            span=span,
            transcript="",
            preparation=None,
            empty_reason="decoder_returned_no_transcript",
            decode_elapsed_sec=elapsed,
        )
    transcript = render_segments((x[4] for x in placed), lambda s: s.speaker)
    relabeled = render_segments((x[3] for x in placed), lambda s: s.speaker)
    diagnostics = (
        ("status", "prepared"),
        ("span_id", str(span.id)),
        ("assignments", ",".join(assignments)),
    )
    snapshot = LiveIdentitySnapshot(
        version=base.version + 1, canonical_speakers=speakers, diagnostics=diagnostics
    )
    prep = LiveIdentityPreparation(
        span_id=span.id,
        epoch=span.epoch,
        start_sample=span.start_sample,
        end_sample=span.end_sample,
        base_snapshot_version=base.version,
        proposed_snapshot=snapshot,
        relabeled_transcript=relabeled,
    )
    return CoordinatorPreparedWork(
        span=span,
        transcript=transcript,
        preparation=prep,
        decode_elapsed_sec=elapsed,
        source_lanes=tuple(LANES[x[1]] for x in placed),
        new_speaker_lanes=tuple(new_speaker_lanes),
        lane_failures=tuple((lane, type(exc).__name__) for lane, exc in failures),
    )


def revision_segments(
    c, lane, span, pcm, text, authority, *, terminal_capture=None, partition_id=None
):
    from .live_transcript_convergence import resolve_segment_overlaps
    from .live_session import EffectiveTranscriptSegment

    owner = c._lane_preparers.get(lane)
    base = c.session.snapshot().identity_snapshot
    if owner is None:
        # Identity may abstain; it must never erase a late producer's words.
        relabeled = unattributed_transcript(text, sample_count=span.sample_count)
    else:
        preparation_kwargs = dict(
            span=span,
            pcm=pcm,
            transcript=text,
            base_snapshot=base,
            allowed_speakers=tuple(c._lane_speakers.get(lane, ())),
        )
        if terminal_capture is None:
            prep = owner.prepare_revision(**preparation_kwargs)
        else:
            try:
                prep = terminal_capture.prepare_revision(
                    owner=owner,
                    partition_id=partition_id,
                    **preparation_kwargs,
                )
            except Exception:
                # Observation may never convert a normal terminal decision into refusal.
                prep = owner.prepare_revision(**preparation_kwargs)
        relabeled = (
            prep.relabeled_transcript
            if prep.status == "prepared"
            else unattributed_transcript(text, sample_count=span.sample_count)
        )
    parsed = span_segments(relabeled, sample_count=span.sample_count)
    normalized = resolve_segment_overlaps(
        [
            (
                p.speaker,
                span.start_sample + round(p.start * 16000),
                span.start_sample + round(p.end * 16000),
                p.text,
            )
            for p in parsed
        ]
    )
    segments = []
    for label, start, end, text in normalized.segments:
        number = int(label[1:]) - 1
        speaker = (
            base.canonical_speakers[number]
            if 0 <= number < len(base.canonical_speakers)
            else None
        )
        segments.append(
            EffectiveTranscriptSegment(
                start_sample=start,
                end_sample=end,
                text=text,
                canonical_speaker=speaker,
                authority=authority,
                source_lane=lane,
            )
        )
    return tuple(segments)


def decode_refinement(c, request):
    from .live_coordinator import RefinementDecode

    span = FrozenSpan(
        id=request.id,
        epoch=request.epoch,
        start_sample=request.start_sample,
        end_sample=request.end_sample,
        reason="rolling_window",
    )
    placed = []
    elapsed = 0.0
    revised_lanes = []
    for lane, tape in c.lane_tapes.items():
        if lane in c._stopped_refinement_lanes:
            continue
        try:
            pcm = tape.read(
                start_sample=request.start_sample, end_sample=request.end_sample
            )
            if not any(pcm):
                revised_lanes.append(lane)
                continue
            outcome = c.rolling_decoder.transcribe_pcm(span=span, pcm=pcm)
            segments = revision_segments(
                c, lane, span, pcm, outcome.transcript, "rolling"
            )
            if not segments:
                c._stopped_refinement_lanes.add(lane)
                continue
            placed.extend(segments)
            revised_lanes.append(lane)
            elapsed += outcome.elapsed_sec or 0
        except Exception:
            c._stopped_refinement_lanes.add(lane)
    return RefinementDecode(
        request=request,
        outcome=InferenceTranscript(transcript="", elapsed_sec=elapsed),
        failure="lane_refinement_failed" if c._stopped_refinement_lanes else None,
        lane_segments=tuple(sorted(placed, key=order)),
        revision_lanes=tuple(revised_lanes),
        failed_lanes=tuple(sorted(c._stopped_refinement_lanes)),
    )


def finalize_lanes(c, finalizer, **kwargs):
    """Finalize lanes, matching each unmapped terminal-local partition once."""
    from .live_transcript_convergence import (
        TerminalOutcome,
        TerminalPartitionDecision,
        TerminalPartitionSpan,
    )
    from .terminal_label_capture import capture_from_environment

    results = []
    lane_results_by_name = {}
    failures = []
    placed = []
    terminal_partitions = []
    base = kwargs["base_surface"]
    terminal_capture = capture_from_environment()

    def finish_lane(item):
        lane, tape = item
        results, failures, placed, terminal_partitions = [], [], [], []
        lane_base = tuple(s for s in base if s.source_lane == lane)
        try:
            pcm = tape.read(end_sample=kwargs["plan"].end_sample)
        except Exception as exc:
            failures.append((lane, type(exc).__name__))
            placed.extend(lane_base)
            return results, failures, placed, terminal_partitions
        if not any(pcm):
            return results, failures, placed, terminal_partitions
        own = c._lane_speakers.get(lane, set())
        # Reuse mono's speaker-level overlap assignment, with both evidence and
        # candidates scoped to this lane. The finalizer preserves its partition.
        result = finalizer.finalize(
            **{
                **kwargs,
                "tape": tape,
                "base_surface": lane_base,
                "canonical_speakers": tuple(
                    s
                    for s in kwargs["canonical_speakers"]
                    if s in own
                ),
            }
        )
        results.append(result)
        if result.proposal is None:
            failures.append((lane, result.accounting.outcome.value))
            placed.extend(lane_base)
        else:
            terminal_local_speakers = result.proposal.terminal_local_speakers
            partition_speakers = {}
            probe_indexes = set()
            partitions = {}
            if len(terminal_local_speakers) == len(result.proposal.segments):
                base_snapshot = c.session.snapshot().identity_snapshot
                for index, (segment, local_speaker) in enumerate(zip(
                    result.proposal.segments, terminal_local_speakers, strict=True
                )):
                    covered = any(
                        base_segment.canonical_speaker in own
                        and min(segment.end_sample, base_segment.end_sample)
                        > max(segment.start_sample, base_segment.start_sample)
                        for base_segment in lane_base
                    )
                    if covered and segment.canonical_speaker is not None:
                        continue
                    probe_indexes.add(index)
                    partitions.setdefault(local_speaker, []).append(segment)
                for index, (local_speaker, segments) in enumerate(partitions.items()):
                    partition_id = f"{lane}:{local_speaker}"
                    start_sample = min(segment.start_sample for segment in segments)
                    end_sample = max(segment.end_sample for segment in segments)
                    span = FrozenSpan(
                        id=int(dict(base_snapshot.diagnostics).get("span_id", "0")) + 1 + index,
                        epoch=kwargs["plan"].epoch,
                        start_sample=start_sample,
                        end_sample=end_sample,
                        reason="terminal_partition_probe",
                    )
                    transcript = render_segments(
                        (
                            TranscriptSegment(
                                start=(segment.start_sample - start_sample) / 16000,
                                end=(segment.end_sample - start_sample) / 16000,
                                speaker="S01",
                                text=segment.text,
                            )
                            for segment in segments
                        ),
                        lambda segment: segment.speaker,
                    )
                    try:
                        probe_args = (
                            c,
                            lane,
                            span,
                            pcm[span.start_sample * 2:span.end_sample * 2],
                            transcript,
                            "terminal",
                        )
                        probe = (
                            revision_segments(*probe_args)
                            if terminal_capture is None
                            else revision_segments(
                                *probe_args,
                                terminal_capture=terminal_capture,
                                partition_id=partition_id,
                            )
                        )
                        speakers = {segment.canonical_speaker for segment in probe}
                        partition_speakers[local_speaker] = (
                            speakers.pop() if len(speakers) == 1 else None
                        )
                    except Exception as exc:
                        failures.append((lane, type(exc).__name__))
                        partition_speakers[local_speaker] = None
            final_speakers = []
            for index, segment in enumerate(result.proposal.segments):
                speaker = segment.canonical_speaker
                if index in probe_indexes:
                    speaker = partition_speakers.get(terminal_local_speakers[index])
                final_speakers.append(speaker)
                placed.append(replace(segment, source_lane=lane, canonical_speaker=speaker))
            if len(terminal_local_speakers) == len(result.proposal.segments):
                groups = {}
                for index, (segment, local_speaker) in enumerate(zip(
                    result.proposal.segments, terminal_local_speakers, strict=True
                )):
                    groups.setdefault(local_speaker, []).append((index, segment))
                owner = getattr(c, "_lane_preparers", {}).get(lane)
                minimum_samples = getattr(
                    getattr(owner, "evidence_provider", None), "min_segment_samples", None
                )
                for local_speaker, members in groups.items():
                    terminal_partitions.append(
                        TerminalPartitionDecision(
                            lane=lane,
                            partition_id=f"{lane}:{local_speaker}",
                            terminal_local_label=local_speaker,
                            decision=(
                                "terminal_partition_probe"
                                if local_speaker in partitions
                                else "terminal_overlap_mapping"
                            ),
                            minimum_samples=(
                                None if minimum_samples is None else int(minimum_samples)
                            ),
                            spans=tuple(
                                TerminalPartitionSpan(
                                    span_index=index,
                                    source_start=segment.start_sample,
                                    source_end=segment.end_sample,
                                    published_identity=final_speakers[index],
                                )
                                for index, segment in members
                            ),
                        )
                    )
        return results, failures, placed, terminal_partitions

    # Stop has drained causal work. Each lane reads its own tape and settled voice
    # evidence; results are assembled in lane order before the single publication.
    with ThreadPoolExecutor(
        max_workers=len(LANES), thread_name_prefix="moss-lane-terminal"
    ) as pool:
        for lane, (lane_results, lane_failures, lane_segments, lane_partitions) in zip(
            c.lane_tapes, pool.map(finish_lane, c.lane_tapes.items())
        ):
            if lane_results:
                lane_results_by_name[lane] = lane_results[0]
            results.extend(lane_results)
            failures.extend(lane_failures)
            placed.extend(lane_segments)
            terminal_partitions.extend(lane_partitions)
    gaps = tuple(
        gap
        for tape in c.lane_tapes.values()
        for gap in tape.gaps(kwargs["plan"].end_sample)
    )
    tape_samples = sum(tape.sample_count for tape in c.lane_tapes.values())
    if not results:
        return finalizer._refused(
            kwargs["plan"],
            (
                TerminalOutcome.TAPE_UNAVAILABLE
                if failures
                else TerminalOutcome.NO_TRANSCRIPT
            ),
            "lane_tape_unavailable" if failures else "all_lanes_zero",
            gaps=gaps,
            tape_samples=tape_samples,
        )
    template = next((r for r in results if r.proposal is not None), results[0])

    def aggregate_elapsed(name: str) -> float | None:
        reached = tuple(
            value
            for result in results
            if (value := getattr(result.accounting, name)) is not None
        )
        return sum(reached) if reached else None

    # These are meeting totals, including lanes that refused publication. Plan and
    # runner geometry are shared; outcome still describes the assembled proposal.
    accounting = replace(
        template.accounting,
        tape_gaps=len(gaps),
        tape_samples=tape_samples,
        possibly_truncated=any(r.accounting.possibly_truncated for r in results),
        **{name: sum(getattr(r.accounting, name) for r in results) for name in (
            "window_count", "completed_windows", "decoded_audio_samples",
            "generated_tokens", "prompt_tokens", "local_speakers",
            "seam_merged_segments", "seam_dropped_segments", "seam_displaced_samples",
        )},
        decode_elapsed_sec=sum(r.accounting.decode_elapsed_sec or 0 for r in results),
        preparation_elapsed_sec=aggregate_elapsed("preparation_elapsed_sec"),
        other_finalize_elapsed_sec=aggregate_elapsed("other_finalize_elapsed_sec"),
        total_elapsed_sec=aggregate_elapsed("total_elapsed_sec"),
        window_diagnostics=[
            {**diagnostic, "source_lane": lane}
            for lane, result in lane_results_by_name.items()
            for diagnostic in result.accounting.window_diagnostics or []
        ] or None,
        window_failure={
            lane: result.accounting.window_failure
            for lane, result in lane_results_by_name.items()
            if result.accounting.window_failure is not None
        } or None,
    )
    if template.proposal is None:
        return replace(
            template,
            accounting=accounting,
            terminal_partitions=tuple(terminal_partitions),
        )
    if terminal_capture is not None:
        terminal_capture.record_partitions(tuple(terminal_partitions))
    return replace(
        template,
        proposal=replace(
            template.proposal,
            segments=tuple(sorted(placed, key=order)),
            terminal_local_speakers=(),
        ),
        accounting=replace(
            accounting,
            segments=len(placed),
            reason=(
                "lane_terminal_failed:" + ",".join(lane for lane, _ in failures)
                if failures
                else None
            ),
            mapped_speakers=len(
                {s.canonical_speaker for s in placed if s.canonical_speaker is not None}
            ),
            unattributed_segments=sum(s.canonical_speaker is None for s in placed),
        ),
        terminal_partitions=tuple(terminal_partitions),
    )
