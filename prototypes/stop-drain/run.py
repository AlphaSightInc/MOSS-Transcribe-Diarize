"""PROTOTYPE (throwaway): WP35 Stop-time drain on the per-lane build. See NOTES.md.

One command:
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> prototypes/stop-drain/run.py \
      --sessions 4 --seconds 600 --output evidence/mvpfix/wp35/stub-4x600-before.json

No network, no GPU. Production runtime/coordinator/arbiter/converger/terminal finalizer,
production process-scoped canonical pump and per-meeting terminal threads, production
identity policy stack, real corpus audio on the system lane and digital zeros on the mic
lane (the WP25 capacity_4x600 shape). The ASR is a stub whose only job is per-request
latency and a request log tagged canonical/rolling/terminal, gated by the same 2-slot
decoder ceiling the campaign harness imposes (prototypes/capacity-campaign/stack.py).
The WeSpeaker forward pass is replaced by a deterministic stand-in (--real-voiceprints
keeps it) because on this laptop one embedding costs more than the stub decode it is
meant to compete with; every identity *policy* value is the manifest's.

Question: at Stop, which queued work must still run for correctness versus which is
superseded by terminal, and what is Stop->final for 1 and 4 concurrent 600 s sessions?

State is printed after every step. Nothing is persisted outside --output.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from moss_transcribe_diarize.app import live_provider_bundle as bundle
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceRuntime,
    LiveServiceDescriptor,
    LiveServiceConfigHashes,
    hash_config,
)
from moss_transcribe_diarize.app.live_transcript_convergence import TerminalTranscriptFinalizer
from moss_transcribe_diarize.app.live_mixer import LiveCompatibilityMixer
from moss_transcribe_diarize.app.live_v2_session import LiveV2Session
from moss_transcribe_diarize.app.live_lane_contract import LiveLane, LiveV2Frame

CORPUS = Path(
    '/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize'
    '/evidence/live-policy-sweep-20260825/corpus'
)
MANIFEST = Path.home() / '.local/share/moss-transcribe-diarize/live/live-provider-manifest.json'
SAMPLE_RATE = 16000

# Per-request stub latency, inside the brief's 0.15-0.6 s/request band and calibrated from
# WP25's own capacity_4x600: 1107 requests, of which 64 were post-Stop, so ~1043 requests
# were served during a 600 s capture by one serial pump worker -- a mean of ~0.575 s per
# request with the worker effectively saturated. A flat decode RTF of 0.22 puts a 2.5 s
# canonical span at 0.55 s and clamps a 10 s rolling window to the 0.6 s ceiling, which
# reproduces that saturation (and therefore the rolling lag) without a GPU.
LATENCY_FLOOR = 0.15
LATENCY_CEILING = 0.60
DECODE_RTF = 0.22
# A terminal pass is charged one ceiling-priced request per 120 s stride window, so a 600 s
# lane tape costs 5 x 0.6 = 3.0 s. That is deliberately far cheaper than a real terminal
# decode: what this bench measures is the *pre-terminal* drain.
TERMINAL_STRIDE_SECONDS = 120.0


class Ledger:
    """Every stub decoder request, tagged, under the campaign's 2-slot ceiling."""

    def __init__(self):
        self.slots = threading.BoundedSemaphore(2)
        self.lock = threading.Lock()
        self.rows: list[dict] = []
        self.active = 0
        self.peak = 0

    def record(self, kind: str, seconds: float, latency: float) -> None:
        with self.slots:
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
                started = time.monotonic()
            try:
                time.sleep(latency)
            finally:
                with self.lock:
                    self.active -= 1
                    self.rows.append(dict(
                        kind=kind, audio_seconds=round(seconds, 3),
                        started=started, finished=time.monotonic(),
                        thread=threading.current_thread().name,
                    ))


class StubRunner:
    """One stub ASR per role, so the request log can name what the request was for."""

    window_seconds = 150
    stride_seconds = 120

    def __init__(self, ledger: Ledger, kind: str, rtf: float = DECODE_RTF):
        self.ledger = ledger
        self.kind = kind
        self.rtf = rtf

    def transcribe(self, audio_path, **kwargs):
        with wave.open(str(audio_path), 'rb') as source:
            seconds = source.getnframes() / source.getframerate()
        if self.kind == 'terminal':
            latency = LATENCY_CEILING * max(1, math.ceil(seconds / TERMINAL_STRIDE_SECONDS))
            windows = max(1, math.ceil(seconds / TERMINAL_STRIDE_SECONDS))
        else:
            latency = min(LATENCY_CEILING, max(LATENCY_FLOOR, self.rtf * seconds))
            windows = 1
        self.ledger.record(self.kind, seconds, latency)
        # Same full-span word shape for every arm; real speech still drives VAD/identity.
        text = ''.join(
            f'[{start:g}][S01]stop drain probe words[{min(start + 2.5, seconds):g}]'
            for start in (index * 2.5 for index in range(max(1, math.ceil(seconds / 2.5))))
        )
        return SimpleNamespace(
            text=text, prompt_len=0, generated_tokens=10, window_count=windows,
            completed_windows=windows, possibly_truncated=False,
        )


def _cheap_voiceprints(encoder, dimension: int):
    """Replace ONLY the ONNX forward pass, keeping the whole identity policy stack.

    This bench is about *scheduling*, and on this laptop one WeSpeaker embedding costs more
    wall time than the whole stub decode it is supposed to be competing with, which would
    make the measured drain a statement about the Mac rather than about the runtime. The
    album, the matcher, the sweeper, the birth rule and every policy value stay exactly as
    the manifest configures them; only the vector's provenance changes, to a deterministic
    two-speaker function of the requested intervals.
    """

    import hashlib

    def embed(wav_path, intervals):
        digest = hashlib.blake2b(
            repr([(round(start, 3), round(end, 3)) for start, end in intervals]).encode(),
            digest_size=8,
        ).digest()
        speaker = digest[0] % 2
        vector = [0.0] * dimension
        vector[speaker] = 1.0
        vector[2 + (digest[1] % 8)] = 0.02  # a stable, tiny per-span jitter
        return vector

    encoder.embed = embed
    return encoder


def build_runtime(ledger: Ledger, tape_bytes: int, rtf: float, *, cheap_identity: bool):
    from dataclasses import replace

    config = bundle.LiveProviderBundleConfig.from_manifest(MANIFEST)
    # Instrumentation-only bound, exactly WP22's: policies otherwise unchanged.
    config = replace(config, bounds_config={**config.bounds_config, 'max_tape_bytes': tape_bytes})
    inference = getattr(bundle, 'bounded_live_inference', bundle.RunnerBoundedWavInference)
    encoder = bundle._identity_encoder(config)
    if cheap_identity:
        encoder = _cheap_voiceprints(encoder, config.runtime.embedding_dimension)
    descriptor = LiveServiceDescriptor(
        source_revision='a' * 40,
        provider_name='wp35-stub-asr',
        provider_revision='prototype',
        provider_manifest_hash=hash_config({}),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config=config.endpoint_config,
            identity_config=config.identity_config,
            decoder_config=config.decoder_config,
        ),
        bounds=bundle._bounds(config.bounds_config),
        frame_samples=config.bounds_config['frame_samples'],
    )
    runtime = LiveServiceRuntime(
        descriptor=descriptor,
        endpoint_policy_factory=lambda: bundle.EndpointPolicy(
            bundle._endpoint_config(config.endpoint_config)
        ),
        speech_provider_factory=lambda: bundle._speech_provider(config),
        decoder_factory=lambda: inference(
            StubRunner(ledger, 'canonical', rtf), max_samples=config.decoder_config['max_samples'],
        ),
        rolling_decoder_factory=lambda: inference(
            StubRunner(ledger, 'rolling', rtf),
            max_samples=bundle.DEFAULT_ROLLING_GEOMETRY.window_samples,
        ),
        identity_preparer_factory=lambda: bundle._identity_preparer(config, encoder=encoder),
        terminal_finalizer=TerminalTranscriptFinalizer(runner=StubRunner(ledger, 'terminal', rtf)),
    )
    return runtime, descriptor


def clips():
    loaded = []
    for name in ('interview_bill_ackman_60s', 'interview_keyu_jin_60s'):
        with wave.open(str(CORPUS / name / 'audio.wav'), 'rb') as source:
            assert (source.getframerate(), source.getnchannels(), source.getsampwidth()) == (16000, 1, 2)
            loaded.append(source.readframes(source.getnframes()))
    return loaded


def words_of(snapshot) -> int:
    return sum(len(segment.text.split()) for segment in snapshot.session.effective_transcript)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions', type=int, default=4)
    parser.add_argument('--seconds', type=int, default=600)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tape-bytes', type=int, default=57_600_000)
    parser.add_argument('--decode-rtf', type=float, default=DECODE_RTF)
    parser.add_argument('--real-voiceprints', action='store_true',
                        help='use the real ONNX identity encoder instead of the cheap stand-in')
    parser.add_argument('--finalization-cap', type=float, default=600.0,
                        help='stop polling for a terminal status after this many seconds')
    args = parser.parse_args()

    scratch = ROOT / '.wp35-tmp'
    scratch.mkdir(exist_ok=True)
    tempfile.tempdir = str(scratch)
    os.environ.setdefault('TMPDIR', str(scratch))

    ledger = Ledger()
    runtime, descriptor = build_runtime(ledger, args.tape_bytes, args.decode_rtf,
                                        cheap_identity=not args.real_voiceprints)
    system_pcm, mic_pcm = clips()
    frame_samples = descriptor.frame_samples
    cadence = frame_samples / SAMPLE_RATE
    assert cadence == .5, 'charter requires 0.5-second frames'
    total_frames = args.seconds * SAMPLE_RATE // frame_samples

    sessions = []
    for _ in range(args.sessions):
        session_id = runtime.create().session_id
        sessions.append(dict(
            session_id=session_id,
            source=LiveV2Session(max_retained_samples=descriptor.bounds.max_retained_samples),
            mixer=LiveCompatibilityMixer(max_output_samples=descriptor.bounds.max_frame_samples),
        ))
    print(json.dumps(dict(step='created', sessions=[s['session_id'] for s in sessions],
                          frames_per_session=total_frames, cadence=cadence)), flush=True)

    barrier = threading.Barrier(args.sessions)
    rows: list[dict] = []
    rows_lock = threading.Lock()

    def drive(index: int):
        entry = sessions[index]
        session_id, source, mixer = entry['session_id'], entry['source'], entry['mixer']
        row = dict(ordinal=index + 1, session_id=session_id, backpressure_retries=0)
        epoch = 1
        barrier.wait(timeout=60)
        started = time.monotonic()
        for seq in range(total_frames):
            offset = seq * frame_samples * 2 % len(system_pcm)
            lane_pcm = {
                LiveLane.SYSTEM: (system_pcm * 2)[offset:offset + frame_samples * 2],
                LiveLane.MICROPHONE: bytes(frame_samples * 2),
            }
            for lane in LiveLane:
                pcm = lane_pcm[lane]
                source.accept(LiveV2Frame(
                    lane=lane, sequence=seq,
                    capture_timestamp_ns=1_000_000_000 + seq * frame_samples * 62500,
                    device_epoch=epoch, silent=pcm == bytes(len(pcm)), discontinuity=False,
                    sample_rate=SAMPLE_RATE, sample_count=frame_samples, pcm=pcm,
                ))
            deadline = time.monotonic() + 30
            while True:
                try:
                    while mixer.admit_available(session_id, source, runtime) is not None:
                        pass
                    break
                except Exception as exc:  # retryable canonical backpressure
                    if getattr(exc, 'retryable', False) is not True or time.monotonic() > deadline:
                        raise
                    row['backpressure_retries'] += 1
                    time.sleep(cadence)
            time.sleep(max(0, started + (seq + 1) * cadence - time.monotonic()))
        while mixer.admit_available(session_id, source, runtime, final=True) is not None:
            pass

        pre = runtime.snapshot(session_id)
        row['words_at_stop_request'] = words_of(pre)
        row['committed_samples_at_stop'] = pre.session.committed_samples
        row['accepted_samples_at_stop'] = pre.session.accepted_samples
        row['events_at_stop'] = len(runtime.events(session_id))
        row['requests_at_stop'] = len(ledger.rows)
        stopped = time.monotonic()
        row['stop_requested_monotonic'] = stopped

        async def stop():
            try:
                await runtime.stop(session_id, 30)
            except Exception as exc:
                row['stop_error'] = type(exc).__name__
            await source.stop(30)

        asyncio.run(stop())
        row['stop_returned_seconds'] = time.monotonic() - stopped
        while True:
            snapshot = runtime.snapshot(session_id)
            status = snapshot.session.finalization_status
            if status in ('final', 'failed', 'unavailable') or (
                snapshot.session.status == 'closed' and status == 'not_started'
            ):
                break
            if time.monotonic() - stopped > args.finalization_cap:
                row['finalization_cap_exceeded'] = True
                break
            time.sleep(.05)
        ended = time.monotonic()
        snapshot = runtime.snapshot(session_id)
        row.update(
            status=snapshot.session.status,
            finalization_status=snapshot.session.finalization_status,
            stop_to_outcome_seconds=ended - stopped,
            stop_to_final_seconds=(
                ended - stopped if snapshot.session.finalization_status == 'final' else None
            ),
            accepted_samples=snapshot.session.accepted_samples,
            accounted_samples=snapshot.session.accounted_samples,
            words_at_final=words_of(snapshot),
            within_90s=(ended - stopped) <= 90,
        )
        events = runtime.events(session_id)
        stop_seq = next((e.seq for e in events if e.kind == 'stop_requested'), None)
        row['stop_event_seq'] = stop_seq
        after = [e for e in events if stop_seq is not None and e.seq > stop_seq]
        row['rolling_admitted_after_stop'] = sum(
            1 for e in after
            if e.kind == 'rolling_decode_queued' and e.payload.get('admitted') is True
        )
        row['rolling_completed_after_stop'] = sum(
            1 for e in after if e.kind == 'rolling_decode_completed'
        )
        outcomes: dict[str, int] = {}
        for event in after:
            if event.kind == 'rolling_decode_completed':
                key = str(event.payload.get('outcome'))
                outcomes[key] = outcomes.get(key, 0) + 1
        row['rolling_outcomes_after_stop'] = outcomes
        row['rolling_revisions_after_stop'] = sum(
            1 for e in after
            if e.kind == 'text_revision_applied' and e.payload.get('source') != 'terminal'
        )
        row['terminal_started'] = any(e.kind == 'terminal_finalization_started' for e in after)
        row['canonical_processed_after_stop'] = sum(
            1 for e in after if e.kind == 'canonical_processed'
        )
        with rows_lock:
            rows.append(row)
        print(json.dumps({k: v for k, v in row.items()}), flush=True)

    threads = [threading.Thread(target=drive, args=(index,), name=f'wp35-session-{index + 1}')
               for index in range(args.sessions)]
    capture_started = time.monotonic()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    rows.sort(key=lambda row: row['ordinal'])
    earliest_stop = min(row['stop_requested_monotonic'] for row in rows)
    by_kind_after_stop: dict[str, int] = {}
    for request in ledger.rows:
        if request['started'] >= earliest_stop:
            by_kind_after_stop[request['kind']] = by_kind_after_stop.get(request['kind'], 0) + 1
    result = dict(
        prototype='wp35-stop-drain',
        cheap_voiceprints=not args.real_voiceprints,
        sessions=args.sessions,
        seconds=args.seconds,
        wall_seconds=time.monotonic() - capture_started,
        stub_latency=dict(floor=LATENCY_FLOOR, ceiling=LATENCY_CEILING, decode_rtf=args.decode_rtf,
                          terminal_stride_seconds=TERMINAL_STRIDE_SECONDS),
        decoder_requests=len(ledger.rows),
        decoder_requests_by_kind={
            kind: sum(1 for r in ledger.rows if r['kind'] == kind)
            for kind in ('canonical', 'rolling', 'terminal')
        },
        decoder_requests_after_first_stop=by_kind_after_stop,
        peak_in_flight=ledger.peak,
        all_final=all(row.get('finalization_status') == 'final' for row in rows),
        all_within_90s=all(row.get('within_90s') for row in rows),
        max_stop_to_outcome_seconds=max(row['stop_to_outcome_seconds'] for row in rows),
        sessions_detail=rows,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'sessions_detail'}, indent=2),
          flush=True)


if __name__ == '__main__':
    os.chdir(ROOT)
    main()
