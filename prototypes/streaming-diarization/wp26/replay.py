"""WP26 LOGIC prototype absorbed as a causal acoustic replay bench; no decoder.

Question: do cropped probes recover the two terminal Lex turns without policy changes?
Falsifier: either crop fails to match speaker-0004, or requires cross-lane evidence.
Run: bash prototypes/streaming-diarization/wp26/replay.sh
State after each album observation and probe is printed without transcript words.
"""
import json
import os
import re
import time
import wave
import sys
from collections import Counter
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder
from moss_transcribe_diarize.app.live_identity_album import FingerprintAlbum
from moss_transcribe_diarize.app.live_provider_bundle import WeSpeakerLiveEvidenceProvider
from moss_transcribe_diarize.app.live_identity import BoundedCausalIdentityPreparer, LiveIdentityConfig
from moss_transcribe_diarize.app.live_session import FrozenSpan, LiveIdentitySnapshot
from moss_transcribe_diarize.app.live_span_bounds import span_segments

ROOT = Path.cwd()
OLD = ROOT.parent / 'MOSS-Transcribe-Diarize-wt-wp12-stop-latency-identity/.wp12'
OUT = ROOT / os.environ.get('WP26_EVIDENCE_DIR', 'evidence/mvpfix/wp26')
SCRATCH = ROOT / 'runs/wp26'
RATE = 16000


def emit(**state):
    print(json.dumps(state), flush=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    run = json.loads((ROOT/'evidence/mvpfix/wp12/overlap-fixed-parity-180.json').read_text())
    rows = [json.loads(s) for s in (ROOT/'evidence/mvpfix/wp12/trace.jsonl').read_text().splitlines()]
    rows = [r for r in rows if r['arm'] == run['arm'] and run['start'] <= r['time'] <= run['stop']+run['stop_to_final']]
    identities = [r for r in rows if r['kind'] == 'identity' and 'speaker-0001' in r['diagnostics'].get('assignments', '')]
    provider_id = identities[0]['provider']
    causal = [r for r in rows if r['kind'] == 'identity' and r['provider'] == provider_id and r['status'] == 'prepared']
    manifest_root = Path.home()/'.local/share/moss-transcribe-diarize/live'
    manifest = json.loads((manifest_root/'live-provider-manifest.json').read_text())
    encoder = _OnnxWeSpeakerEmbedder(manifest_root/manifest['assets'][0]['path'], device='cpu')
    album = FingerprintAlbum()
    source = ROOT.parent/'MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/interview_bill_ackman_60s/audio.wav'
    with wave.open(str(source)) as f:
        assert f.getframerate() == RATE and f.getnchannels() == 1 and f.getsampwidth() == 2
        pcm = f.readframes(60*RATE)*3
    base = []
    started = time.monotonic()
    for row in causal:
        score = next(r for r in rows if r['kind'] == 'scores' and r['provider'] == provider_id and r['span'] == row['span'])
        embeddings = [r for r in rows if r['kind'] == 'embedding' and r.get('provider') == provider_id and r['span'] == row['span']]
        # Provider embeds labels in insertion order; score.pending preserves it.
        assert len(embeddings) == len(score['pending'])
        assigned = dict(a.split('->') for a in row['diagnostics']['assignments'].split(',') if '->' in a)
        with wave.open(str(SCRATCH/'span.wav'), 'wb') as f:
            f.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
            f.writeframes(pcm[score['start_sample']*2:score['end_sample']*2])
        for local, emb in zip(score['pending'], embeddings, strict=True):
            if local not in assigned:
                continue
            vector = encoder.embed(SCRATCH/'span.wav', emb['intervals'])
            decision = album.observe(canonical_speaker=assigned[local], vector=vector,
                                     duration_sec=emb['audio_seconds'], span_id=row['span'])
            for a, b in emb['intervals']:
                base.append(dict(start=score['start_sample']+round(a*RATE), end=score['start_sample']+round(b*RATE), speaker=assigned[local]))
            emit(step='album', span=row['span'], local=local, speaker=assigned[local],
                 intervals=emb['intervals'], decision=decision,
                 album={s:len(album.reference_support(s)) for s in album.speakers()})
    provider = WeSpeakerLiveEvidenceProvider(encoder=encoder, album=album,
        min_segment_samples=manifest['identity_provider']['min_segment_samples'])
    preparer = BoundedCausalIdentityPreparer(config=LiveIdentityConfig(**manifest['identity_config']), evidence_provider=provider)
    snapshot = LiveIdentitySnapshot(canonical_speakers=('speaker-0001','speaker-0002','speaker-0003','speaker-0004'))
    surface = json.loads((OLD/'overlap-fixed-parity-180-surface.json').read_text())
    missing = [s for s in surface if s['source_lane']=='system' and s['canonical_speaker'] is None]
    probes = []
    for index, s in enumerate(missing):
        span = FrozenSpan(1000+index, 0, s['start_sample'], s['end_sample'], 'terminal_unassigned')
        crop = pcm[span.start_sample*2:span.end_sample*2]
        text = f'[0][S01]probe[{span.sample_count/RATE}]'
        reader = provider.revision_reader()
        evidence = reader.score(span=span, pcm=crop, segments=span_segments(text, sample_count=span.sample_count), base_snapshot=snapshot)
        prep = preparer.prepare_revision(span=span, pcm=crop, transcript=text, base_snapshot=snapshot, allowed_speakers=('speaker-0001','speaker-0004'))
        overlap = Counter()
        for b in base:
            overlap[b['speaker']] += max(0, min(b['end'],span.end_sample)-max(b['start'],span.start_sample))/RATE
        nearest = min(base, key=lambda b:max(0,b['start']-span.end_sample,span.start_sample-b['end']))
        assigned = dict(prep.proposed_snapshot.diagnostics).get('assignments')
        state = dict(step='probe', start=span.start_sample/RATE, end=span.end_sample/RATE,
                     words=len(re.findall(r'[a-z0-9]+',s['text'].lower())), causal_overlap_seconds=dict(overlap),
                     nearest_causal=nearest, scores={e.canonical_speaker:e.score for e in evidence},
                     diagnostics=dict(prep.proposed_snapshot.diagnostics), assigned=assigned,
                     reference_speaker='speaker-0004', correct=assigned=='S01->speaker-0004')
        probes.append(state)
        emit(**state)
    report = dict(verdict='PASS' if len(probes)==2 and all(s['correct'] for s in probes) else 'FALSIFIED',
                  seconds=time.monotonic()-started, probes=probes, causal_preparations=len(causal),
                  album_support={s:[dict(span=e.span_id, seconds=e.duration_sec) for e in album.reference_support(s)] for s in album.speakers()},
                  provenance='Re-embedded retained causal intervals and accepted assignments against original repeated PCM. Reconstructed album, not retained runtime vectors. No raw terminal local labels or pre-terminal surface retained.', decoder_calls=0)
    (OUT/'prototype.json').write_text(json.dumps(report, indent=2)+'\n')
    emit(**report)
    if '--production' in sys.argv:
        import moss_transcribe_diarize.app.live_lane_decode as lanes
        from moss_transcribe_diarize.app.live_session import EffectiveTranscriptSegment, TextRevisionProposal
        from moss_transcribe_diarize.app.live_transcript_convergence import (
            TerminalFinalization, TerminalFinalizationAccounting, TerminalOutcome,
            TerminalDecodePlan, RollingStatus,
        )
        from moss_transcribe_diarize.app.live_tape import CompleteMixedTape
        segments = tuple(EffectiveTranscriptSegment(**s) for s in surface if s['source_lane']=='system')
        captured = next(r['accounting'] for r in rows if r['kind']=='terminal_end' and r['accounting']['segments']==56)
        accounting = TerminalFinalizationAccounting(**{
            f.name:TerminalOutcome(captured[f.name]) if f.name=='outcome' else captured[f.name]
            for f in fields(TerminalFinalizationAccounting)})
        retained = TerminalFinalization(TextRevisionProposal(0,0,'terminal',0,180*RATE,segments),accounting)
        tape = CompleteMixedTape(epoch=0, capacity_bytes=len(pcm))
        assert tape.append(start_sample=0, pcm=pcm).written
        # Replay the captured POST-MAPPING proposal, not a claim of raw decode replay.
        # Existing labelled terminal rows cover themselves; missing rows use actual
        # causal interval evidence. Thus only the faulty decision is exercised.
        causal_base = tuple(replace(s, authority='causal') for s in segments if s.canonical_speaker)
        causal_base += tuple(EffectiveTranscriptSegment(b['start'],b['end'],'causal',b['speaker'],'causal','system') for b in base)
        c = SimpleNamespace(lane_tapes={'system':tape}, _lane_speakers={'system':{'speaker-0001','speaker-0004'}},
            _lane_preparers={'system':preparer}, session=SimpleNamespace(snapshot=lambda:SimpleNamespace(identity_snapshot=snapshot)))
        calls = []
        revision = lanes.revision_segments
        def measured(c, lane, span, crop, text, authority):
            start = time.monotonic()
            result = revision(c,lane,span,crop,text,authority)
            calls.append(dict(lane=lane,start=span.start_sample/RATE,end=span.end_sample/RATE,
                              bytes=len(crop),reason=span.reason,seconds=time.monotonic()-start))
            return result
        with patch.object(lanes,'revision_segments',measured):
            result = lanes.finalize_lanes(c, SimpleNamespace(finalize=lambda **kwargs:retained),
                plan=TerminalDecodePlan(0,180*RATE,0,RollingStatus.STOPPED,0,0), tape=tape,
                base_text_revision_version=0,base_surface=causal_base,canonical_speakers=snapshot.canonical_speakers)
        diffs = [dict(index=i,start=a.start_sample/RATE,end=a.end_sample/RATE,before=a.canonical_speaker,after=b.canonical_speaker)
                 for i,(a,b) in enumerate(zip(segments,result.proposal.segments,strict=True)) if a!=b]
        unchanged = all(replace(a,canonical_speaker=b.canonical_speaker)==b for a,b in zip(segments,result.proposal.segments,strict=True))
        passed = len(calls)==2 and len(diffs)==2 and all(d['before'] is None and d['after']=='speaker-0004' for d in diffs) and unchanged
        production = dict(verdict='PASS' if passed else 'FAIL',segments=len(segments),differences=diffs,
                          unchanged_words_times_lanes=unchanged,unassigned=result.accounting.unattributed_segments,probes=calls,
                          provenance='Production finalize_lanes, captured post-mapping terminal proposal, reconstructed album and causal coverage. No new decoder/API/Stop run.')
        (OUT/'production-replay.json').write_text(json.dumps(production,indent=2)+'\n')
        emit(**production)
        assert passed


if __name__ == '__main__':
    main()
