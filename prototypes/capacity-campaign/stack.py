"""PROTOTYPE ONLY: local recipe, decoder accounting and two-request ceiling."""
import importlib.util
import io
import math
import os
import dataclasses
import wave
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from moss_transcribe_diarize.app.vllm_runner import VllmRunner
from moss_transcribe_diarize.app.live_coordinator import LiveCoordinator
from moss_transcribe_diarize.app.inference_scheduler import InferenceDispatchScheduler

state = Path(sys.argv[sys.argv.index('--state') + 1])
state.mkdir(parents=True, exist_ok=True)
original = VllmRunner._post_multipart
stub_latency = os.environ.get('WP30_STUB_LATENCY')
if os.environ.get('WP30_TELEMETRY'):
    from telemetry import install
    install(state)
slots = threading.BoundedSemaphore(2)
lock = threading.Lock()
active = 0
sent = 0
completed = 0
max_calls = int(os.environ.get('MOSS_MAX_OWN_DECODER_CALLS', '0')) or None
stage_lock = threading.Lock()
schedulers = []


# Prototype-only in-process observation. Production scheduling is unchanged.
original_scheduler_init = InferenceDispatchScheduler.__init__
original_scheduler_run = InferenceDispatchScheduler._run


def captured_scheduler_init(self, *args, **kwargs):
    original_scheduler_init(self, *args, **kwargs)
    schedulers.append(self)


def captured_scheduler_run(self, *args, **kwargs):
    try:
        return original_scheduler_run(self, *args, **kwargs)
    finally:
        with stage_lock:
            rows = [
                dataclasses.asdict(timing)
                for scheduler in schedulers
                for timing in scheduler.dispatch_timings()
            ]
            temporary = state / 'dispatch-timings.tmp'
            temporary.write_text(json.dumps(rows, indent=2) + '\n')
            temporary.replace(state / 'dispatch-timings.json')


InferenceDispatchScheduler.__init__ = captured_scheduler_init
InferenceDispatchScheduler._run = captured_scheduler_run


def record(kind, **extra):
    with (state / 'decoder.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(kind=kind, time=time.monotonic(), active=active,
                                     sent=sent, completed=completed, **extra)) + '\n')


def counted(self, *args, **kwargs):
    global active, sent, completed
    # External campaign control; no production queue/decoder policy is modified.
    while (state / 'PAUSE').exists():
        time.sleep(.25)
    with slots:
        while (state / 'PAUSE').exists():
            time.sleep(.25)
        with lock:
            if max_calls is not None and sent >= max_calls:
                record('ceiling_refusal', ceiling=max_calls)
                raise RuntimeError('campaign_decoder_call_ceiling_reached')
            active += 1
            sent += 1
            ordinal = sent
            try:
                with wave.open(io.BytesIO(kwargs['file_bytes'])) as wav:
                    audio_seconds = wav.getnframes() / wav.getframerate()
            except Exception:
                audio_seconds = None
            record(
                'start',
                ordinal=ordinal,
                audio_seconds=audio_seconds,
                thread=threading.current_thread().name,
            )
        started = time.monotonic()
        try:
            if stub_latency is not None:
                time.sleep(float(stub_latency))
                with wave.open(io.BytesIO(kwargs['file_bytes'])) as wav:
                    seconds = wav.getnframes()/wav.getframerate()
                text = ''.join(f'[{start:g}][S01]memory probe words[{min(start+2.5, seconds):g}]'
                    for start in (i*2.5 for i in range(math.ceil(seconds/2.5))))
                return {'text':text, 'usage':{'completion_tokens':10}}
            return original(self, *args, **kwargs)
        finally:
            with lock:
                active -= 1
                completed += 1
                record('finish', ordinal=ordinal, elapsed=time.monotonic()-started)


VllmRunner._post_multipart = counted

# Keep each tape's existing accounting, since the public release event names
# only the mixed tape while per-lane decoding also retains two lane tapes.
original_release = LiveCoordinator.release_tape


def measured_release(self):
    through = self.session.snapshot().accepted_samples
    tapes = dict(self.lane_tapes)
    if self.tape is not None:
        tapes['mixed'] = self.tape
    before = {name: tape.accounting(through_sample=through).to_dict()
              for name, tape in tapes.items()}
    result = original_release(self)
    after = {name: tape.accounting(through_sample=through).to_dict()
             for name, tape in tapes.items()}
    with (state / 'tape-release.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(time=time.monotonic(), before=before, after=after)) + '\n')
    return result


LiveCoordinator.release_tape = measured_release
spec = importlib.util.spec_from_file_location('wp6_local_stack', ROOT / 'prototypes/streaming-diarization/draft-lane/run_local_stack.py')
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)
# Reuse the local recipe with only its tunnel endpoint replaced in this process.
from moss_transcribe_diarize.app import phase2_web_cli
cli_main = phase2_web_cli.main


def local_main(argv):
    if '--vllm-base-url' not in sys.argv:
        argv[argv.index('--vllm-base-url') + 1] = 'http://127.0.0.1:18106/v1'
    return cli_main(argv)


phase2_web_cli.main = local_main
recipe.main()
