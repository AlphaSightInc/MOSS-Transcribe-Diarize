"""PROTOTYPE ONLY: local recipe, decoder accounting and two-request ceiling."""
import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from moss_transcribe_diarize.app.vllm_runner import VllmRunner

state = Path(sys.argv[sys.argv.index('--state') + 1])
state.mkdir(parents=True, exist_ok=True)
original = VllmRunner._post_multipart
slots = threading.BoundedSemaphore(2)
lock = threading.Lock()
active = 0
sent = 0
completed = 0


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
            active += 1
            sent += 1
            ordinal = sent
            record('start', ordinal=ordinal)
        started = time.monotonic()
        try:
            return original(self, *args, **kwargs)
        finally:
            with lock:
                active -= 1
                completed += 1
                record('finish', ordinal=ordinal, elapsed=time.monotonic()-started)


VllmRunner._post_multipart = counted
spec = importlib.util.spec_from_file_location('wp6_local_stack', ROOT / 'prototypes/streaming-diarization/draft-lane/run_local_stack.py')
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)
# Reuse the local recipe with only its tunnel endpoint replaced in this process.
from moss_transcribe_diarize.app import phase2_web_cli
cli_main = phase2_web_cli.main


def local_main(argv):
    argv[argv.index('--vllm-base-url') + 1] = 'http://127.0.0.1:18106/v1'
    return cli_main(argv)


phase2_web_cli.main = local_main
recipe.main()
