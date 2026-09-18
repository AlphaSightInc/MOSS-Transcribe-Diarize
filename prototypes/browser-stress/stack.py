"""WP5 private stack; bounded real decoder, no shared-service mutations."""
import sys
import threading
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from moss_transcribe_diarize.app.vllm_runner import VllmRunner
original = VllmRunner._post_multipart
lock = threading.Lock()
slots = threading.Semaphore(2)
count = 0

def bounded(self, *args, **kwargs):
    global count
    with lock:
        counter = ROOT / 'runs/wp5/request-count'
        count = int(counter.read_text()) if counter.exists() else 0
        if count >= 200:
            raise RuntimeError('WP5 decoder request budget exhausted')
        count += 1
        counter.write_text(str(count))
    with slots:
        return original(self, *args, **kwargs)

VllmRunner._post_multipart = bounded
recipe = ROOT / 'prototypes/streaming-diarization/draft-lane/run_local_stack.py'
code = recipe.read_text().replace('127.0.0.1:18000/v1', '127.0.0.1:18105/v1')
exec(compile(code, str(recipe), 'exec'), {'__name__': '__main__', '__file__': str(recipe)})
