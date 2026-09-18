"""THROWAWAY candidate: serial source-lane producers on the real coordinator."""
from dataclasses import replace
from types import SimpleNamespace
import time
from moss_transcribe_diarize.transcript_parser import TranscriptSegment
from .live_span_bounds import span_segments, render_segments
from .live_session import LiveIdentityPreparation, LiveIdentitySnapshot, FrozenSpan
from .live_adapters import InferenceTranscript, LiveProviderError
from .live_identity import unattributed_transcript

LANES = ('system', 'microphone')
def order(s):
    return s.start_sample, LANES.index(s.source_lane), s.end_sample

def prepare_lanes(c, work, on_decoded):
    from .live_coordinator import CoordinatorPreparedWork
    span = work.span
    base = work.base_snapshot
    speakers = base.canonical_speakers
    assignments = []
    placed = []
    elapsed = 0.0
    # Namespaced local labels are internal addresses, never public speaker IDs.
    for index, lane in enumerate(LANES):
        pcm = dict(work.lane_pcm).get(lane, b'')
        if not any(pcm):
            continue
        try:
            inferred = c._decode(span, pcm)
        except LiveProviderError:
            continue
        elapsed += inferred.elapsed_sec or 0.0
        parsed = span_segments(inferred.transcript, sample_count=span.sample_count)
        if not parsed:
            continue
        parsed = tuple(replace(s, speaker=f'S{index+1}{s.speaker[1:]}') for s in parsed)
        text = render_segments(parsed, lambda s: s.speaker)
        if lane not in c._lane_preparers:
            c._lane_preparers[lane] = c.identity_preparer.lane_factory()
        preparer = c._lane_preparers[lane]
        own = c._lane_speakers.setdefault(lane, set())
        current = replace(base, canonical_speakers=speakers)
        prep = preparer.prepare(span=span, pcm=pcm, transcript=text, base_snapshot=current,
                                allowed_speakers=tuple(s for s in speakers if s in own))
        if prep.status == 'prepared':
            new = set(prep.proposed_snapshot.canonical_speakers) - set(speakers)
            own.update(new)
            speakers = prep.proposed_snapshot.canonical_speakers
            diag = dict(prep.proposed_snapshot.diagnostics)
            assignments.extend(filter(None, diag.get('assignments','').split(',')))
            out = prep.relabeled_transcript
        else:
            out = unattributed_transcript(text, sample_count=span.sample_count)
        for local, published in zip(parsed, span_segments(out, sample_count=span.sample_count)):
            placed.append((published.start, index, published.end, published, local))
    placed.sort(key=lambda x: x[:3])
    if not placed:
        return CoordinatorPreparedWork(span=span, transcript='', preparation=None,
                                       empty_reason='no_transcript', decode_elapsed_sec=elapsed)
    transcript = render_segments((x[4] for x in placed), lambda s:s.speaker)
    relabeled = render_segments((x[3] for x in placed), lambda s:s.speaker)
    diagnostics = (('status','prepared'),('span_id',str(span.id)),('assignments',','.join(assignments)))
    snapshot = LiveIdentitySnapshot(version=base.version+1, canonical_speakers=speakers, diagnostics=diagnostics)
    prep = LiveIdentityPreparation(span_id=span.id, epoch=span.epoch, start_sample=span.start_sample,
        end_sample=span.end_sample, base_snapshot_version=base.version, proposed_snapshot=snapshot,
        relabeled_transcript=relabeled)
    if on_decoded:
        on_decoded(span, transcript)
    return CoordinatorPreparedWork(span=span, transcript=transcript, preparation=prep,
        decode_elapsed_sec=elapsed, source_lanes=tuple(LANES[x[1]] for x in placed))

def revision_segments(c, lane, span, pcm, text, authority):
    from .live_provider_bundle import WeSpeakerLiveEvidenceProvider
    from .live_identity import BoundedCausalIdentityPreparer
    from .live_transcript_convergence import resolve_segment_overlaps
    from .live_session import EffectiveTranscriptSegment
    owner = c._lane_preparers.get(lane)
    base = c.session.snapshot().identity_snapshot
    if owner is None:
        # Identity may abstain; it must never erase a late producer's words.
        relabeled = unattributed_transcript(text, sample_count=span.sample_count)
    else:
        evidence = owner.evidence_provider
        reader = WeSpeakerLiveEvidenceProvider(encoder=evidence.encoder,
            canonical_embedding=evidence._canonical_vector,
            min_segment_samples=evidence.min_segment_samples,
            birth_min_seconds=evidence.birth_min_seconds)
        preparer = BoundedCausalIdentityPreparer(config=owner.config,evidence_provider=reader)
        prep = preparer.prepare(span=span,pcm=pcm,transcript=text,base_snapshot=base,
            allowed_speakers=tuple(c._lane_speakers.get(lane,())))
        relabeled = prep.relabeled_transcript if prep.status=='prepared' else unattributed_transcript(text,sample_count=span.sample_count)
    parsed = span_segments(relabeled, sample_count=span.sample_count)
    normalized = resolve_segment_overlaps([(p.speaker,span.start_sample+round(p.start*16000),span.start_sample+round(p.end*16000),p.text) for p in parsed])
    segments=[]
    for label,start,end,text in normalized.segments:
        number=int(label[1:])-1
        speaker=base.canonical_speakers[number] if 0<=number<len(base.canonical_speakers) else None
        segments.append(EffectiveTranscriptSegment(start_sample=start,end_sample=end,text=text,canonical_speaker=speaker,authority=authority,source_lane=lane))
    return tuple(segments)

def decode_refinement(c, request):
    from .live_coordinator import RefinementDecode
    span = FrozenSpan(id=request.id, epoch=request.epoch, start_sample=request.start_sample,
                      end_sample=request.end_sample, reason='rolling_window')
    placed = []
    elapsed = 0.0
    revised_lanes = []
    for lane, tape in c.lane_tapes.items():
        if lane in c._stopped_refinement_lanes:
            continue
        try:
            pcm = tape.read(start_sample=request.start_sample, end_sample=request.end_sample)
            if not any(pcm):
                revised_lanes.append(lane)
                continue
            outcome = c.rolling_decoder.transcribe_pcm(span=span, pcm=pcm)
            segments = revision_segments(c,lane,span,pcm,outcome.transcript,'rolling')
            if not segments:
                c._stopped_refinement_lanes.add(lane)
                continue
            placed.extend(segments)
            revised_lanes.append(lane)
            elapsed += outcome.elapsed_sec or 0
        except Exception:
            c._stopped_refinement_lanes.add(lane)
    return SimpleNamespace(request=request, outcome=InferenceTranscript(transcript='', elapsed_sec=elapsed),
                           failure=None, lane_segments=tuple(sorted(placed,key=order)), revision_lanes=tuple(revised_lanes))

def finalize_lanes(c, finalizer, **kwargs):
    from .live_transcript_convergence import TerminalOutcome, resolve_segment_overlaps
    from .live_session import EffectiveTranscriptSegment
    results = []
    placed = []
    base = kwargs['base_surface']
    for lane, tape in c.lane_tapes.items():
        lane_base = tuple(s for s in base if s.source_lane == lane)
        pcm = tape.read(end_sample=kwargs['plan'].end_sample)
        if not any(pcm):
            continue
        captured = []
        class CaptureRunner:
            def transcribe(self, *args, **options):
                result = finalizer.runner.transcribe(*args, **options)
                captured.append(result)
                return result
        listener = type(finalizer)(runner=CaptureRunner(), transcribe_kwargs=finalizer.transcribe_kwargs, scratch_dir=finalizer.scratch_dir)
        result = listener.finalize(**{**kwargs, 'tape':tape, 'base_surface':(),
                'canonical_speakers':tuple(s for s in kwargs['canonical_speakers'] if s in c._lane_speakers.get(lane,set()))})
        results.append(result)
        if result.proposal is None:
            placed.extend(lane_base)
        else:
            # Terminal identity is voice evidence, never timestamp overlap.
            raw = str(captured[0].text)
            base_snapshot = c.session.snapshot().identity_snapshot
            span = FrozenSpan(id=int(dict(base_snapshot.diagnostics).get('span_id','0'))+1,
                epoch=kwargs['plan'].epoch, start_sample=0, end_sample=kwargs['plan'].end_sample, reason='terminal')
            placed.extend(revision_segments(c,lane,span,pcm,raw,'terminal'))
    if not results:
        return finalizer._refused(kwargs['plan'], TerminalOutcome.NO_TRANSCRIPT, 'all_lanes_zero')
    template = next((r for r in results if r.proposal is not None), results[0])
    if template.proposal is None:
        return template
    return replace(template, proposal=replace(template.proposal, segments=tuple(sorted(placed,key=order))),
        accounting=replace(template.accounting, segments=len(placed),
            decode_elapsed_sec=sum(r.accounting.decode_elapsed_sec or 0 for r in results)))
