"""Offline six-case convergence isolation; never calls a provider or changes policy.

Run from the repo: .venv/bin/python prototypes/streaming-diarization/phase2-quality-surface-audit/probe.py
Frozen provider answers and canonical speaker timelines are inputs, not fresh production evidence.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import sys
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'prototypes/streaming-diarization/live-convergence'), str(ROOT / 'prototypes/live-file-gap-context')]
import proto_context_arms as bench
import verify_production_converger as verifier
from moss_transcribe_diarize.phase2_acceptance_external import _load_surface_harness
from moss_transcribe_diarize.app.live_transcript_convergence import RollingTranscriptConverger
from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.live_service_replay import _snapshot_from_dict, ServiceReplayTransportFailure

HERE = Path(__file__).resolve().parent
CORPUS = ROOT / 'evidence/live-policy-sweep-20260825/corpus'
ARCHIVE = ROOT / 'evidence/live-g4-recovery-20260825/deployed-10-10'
MODEL = 'OpenMOSS-Team/MOSS-Transcribe-Diarize'


def capture_probe(harness, snapshots):
    class Inner:
        def events(self, session_id, since_seq=0):
            return ()
        async def stop(self, session_id, deadline):
            raise ServiceReplayTransportFailure('controlled Stop failure')
        def snapshot(self, session_id):
            return _snapshot_from_dict(snapshots['pre_stop_settled']['snapshot'])
    capture = harness.SurfaceCaptureService(Inner(), settle_timeout=30, poll_seconds=.25)
    failed = False
    try:
        asyncio.run(capture.stop('controlled', deadline=5))
    except ServiceReplayTransportFailure:
        failed = True
    return {'stop_failure_propagated': failed, 'captured_surfaces': list(capture.captures),
            'settled_wait': capture.captures['pre_stop_settled']['wait'],
            'post_stop_final_produced': 'post_stop_final' in capture.captures}


def main():
    harness = _load_surface_harness(ROOT)
    manifest = json.loads((CORPUS / 'corpus-manifest.json').read_text())
    result = {'source_revision': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(), 'scope': 'current converger with frozen provider answers and canonical speaker timelines; not fresh Account replay', 'cases': []}
    with tempfile.TemporaryDirectory(prefix='moss-quality-offline-') as temp:
        for pass_name, cache_name in [('A', 'pass-A.json'), ('B', 'pass-B-recovery.json')]:
            decoder = bench.Decoder(runner=verifier._NoRunner(), model=MODEL,
                cache_path=ROOT / 'evidence/live-policy-sweep-20260825/moss/shadow-cache' / cache_name)
            for item in manifest['cases']:
                case_id = item['case_id']
                case = harness.Case(case_id, CORPUS / case_id, CORPUS / case_id / 'reference.jsonl')
                pcm = bench.read_pcm(case.audio)
                audio_sha = hashlib.sha256(case.audio.read_bytes()).hexdigest()
                assert audio_sha == item['audio']['wav_sha256']
                duration = len(pcm) / 32000
                snapshots = {x['surface']: x for x in map(json.loads,
                    (ARCHIVE / f'pass-{pass_name}' / case_id / 'actual/snapshots.jsonl').read_text().splitlines())}
                captured_scores = {name: harness.score_surface(case, harness.transcript_rows(value['snapshot'], duration))
                    for name, value in snapshots.items()}
                if 'stop_probe' not in result:
                    result['stop_probe'] = capture_probe(harness, snapshots)
                canonical = list(harness.lsa._hypothesis_from_committed(snapshots['pre_stop_settled']['snapshot']['session'],
                    corpus_start_sample=0, corpus_duration_sec=duration))
                timeline = bench.SpeakerTimeline(canonical)
                converger = RollingTranscriptConverger(epoch=0)
                session = verifier._Session()
                cursor = 0
                total = len(pcm) // 2
                while cursor < total:
                    end = min(cursor + 8000, total)
                    requests = converger.accept_pcm(cursor, pcm[cursor * 2:end * 2])
                    cursor = end
                    session.committed_samples = cursor
                    requests += converger.observe_base(session)
                    for request in requests:
                        decoded = decoder.decode(pcm=pcm, audio_sha=audio_sha, start_sample=request.start_sample,
                            end_sample=request.end_sample, token_cap=request.token_cap, scratch=Path(temp))
                        proposal = converger.complete(request.id, InferenceTranscript(transcript=decoded['transcript'],
                            elapsed_sec=float(decoded['elapsed_seconds'])))
                        assert proposal is not None
                        session.apply(proposal)
                converger.observe_base(session)
                converger.stop(total)
                accounting = converger.accounting()
                projected = timeline.relabel(bench.normalise(session.segments, duration))
                rows = [{'start': s.start, 'end': s.end, 'speaker': s.speaker, 'text': s.text} for s in projected]
                # A partial final window remains canonical; the retained snapshot is its input.
                frontier = session.canonical_through_sample / 16000
                tail = harness.transcript_rows(snapshots['pre_stop_settled']['snapshot'], duration)
                assert not any(r['start'] < frontier < r['end'] for r in tail)
                rows.extend(r for r in tail if r['start'] >= frontier)
                entry = {'case_id': case_id, 'pass': pass_name, 'captured_scores_rescored_at_head': captured_scores,
                    'current_converger_frozen_decode_scores': harness.score_surface(case, rows),
                    'windows_completed': accounting.windows_completed, 'windows_failed': accounting.windows_failed,
                    'stale_completions': accounting.stale_completions,
                    'captured_settled_wait': snapshots['pre_stop_settled'].get('wait'),
                    'captured_finalization': snapshots['post_stop_final']['snapshot']['session']['finalization_status']}
                result['cases'].append(entry)
                print(case_id, pass_name, entry['windows_completed'], entry['current_converger_frozen_decode_scores']['wer'], flush=True)
            assert all(call['cached'] for call in decoder.calls)
    result['fresh_provider_requests'] = 0
    result['total_windows_completed'] = sum(r['windows_completed'] for r in result['cases'])
    result['macro_current_converger'] = {key: sum(r['current_converger_frozen_decode_scores'][key] for r in result['cases']) / len(result['cases'])
        for key in ('wer', 'content_recall', 'tbsa', 'der', 'matched_word_speaker_accuracy', 'reference_speech_der')}
    (HERE / 'results.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result['macro_current_converger'], indent=2))

if __name__ == '__main__':
    main()
