"""Absorbed into the bench as a frozen acoustic-versus-overlap comparison.

Run: WP12_ARM=overlap-shadow bash prototypes/streaming-diarization/wp12-stop-identity/experiment.sh 24 parity
No extra decoder calls. Acoustic production output remains the published control.
Production uses the existing finalizer for the same overlap algorithm; this
counterfactual bench loads the frozen 60b3b584 acoustic source archive.
"""
from dataclasses import replace

from moss_transcribe_diarize.app.live_session import EffectiveTranscriptSegment
from moss_transcribe_diarize.app.live_span_bounds import span_segments
from moss_transcribe_diarize.app.live_transcript_convergence import (
    resolve_segment_overlaps, terminal_speaker_mapping,
)


def overlap_segments(c, lane, span, pcm, text, acoustic):
    snapshot = c.session.snapshot()
    base = tuple(s for s in snapshot.effective_transcript
                 if s.source_lane == lane)
    own = tuple(s for s in snapshot.identity_snapshot.canonical_speakers
                if s in c._lane_speakers.get(lane, ()))
    placed = resolve_segment_overlaps([
        (s.speaker, round(s.start * 16000), round(s.end * 16000), s.text)
        for s in span_segments(text, sample_count=span.sample_count)
        if s.text.strip()
    ]).segments
    mapping = terminal_speaker_mapping(placed, base_surface=base, canonical_speakers=own)
    output = []
    fallback_samples = 0
    for index, (local, start, end, words) in enumerate(placed):
        covered = any(s.canonical_speaker in own and
                      min(end, s.end_sample) > max(start, s.start_sample)
                      for s in base)
        speaker = mapping.get(local)
        if not covered:
            # Preserve the original evidence floor/thresholds, but expose only this
            # uncovered segment's audio to the acoustic provider.
            tail = replace(span, id=span.id + index, start_sample=start, end_sample=end,
                           reason='terminal_uncovered')
            probe = acoustic(c, lane, tail, pcm[start*2:end*2],
                             f'[0][{local}]{words}[{(end-start)/16000}]', 'terminal')
            speaker = probe[0].canonical_speaker if probe else None
            fallback_samples += end - start
        output.append(EffectiveTranscriptSegment(start, end, words, speaker, 'terminal', lane))
    return tuple(output), fallback_samples


def install(emit):
    import moss_transcribe_diarize.app.live_lane_decode as lanes
    original = lanes.revision_segments

    def shadow(c, lane, span, pcm, text, authority):
        control = original(c, lane, span, pcm, text, authority)
        if authority != 'terminal':
            return control
        candidate, fallback = overlap_segments(c, lane, span, pcm, text, original)
        differences = []
        for i in range(max(len(control), len(candidate))):
            a = control[i] if i < len(control) else None
            b = candidate[i] if i < len(candidate) else None
            if a != b:
                differences.append(dict(index=i,
                    acoustic=None if a is None else dict(start=a.start_sample, end=a.end_sample, speaker=a.canonical_speaker),
                    overlap=None if b is None else dict(start=b.start_sample, end=b.end_sample, speaker=b.canonical_speaker),
                    words_equal=a is not None and b is not None and a.text==b.text))
        own = c._lane_speakers.get(lane, ())
        emit('overlap_comparison', lane=lane, samples=span.end_sample,
             acoustic_segments=len(control), overlap_segments=len(candidate),
             differences=differences, fallback_audio_seconds=fallback/16000,
             cross_lane_assignments=sum(s.canonical_speaker is not None and s.canonical_speaker not in own for s in candidate))
        return control

    lanes.revision_segments = shadow
