"""Bench: CPU cost of production observations on 300 real-speech 8000-sample chunks.
Question: can an explicit opt-in remove correlation from the default hot path?
Falsifier: disabled mode calls correlation or differs in exact-zero decisions.
Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <venv-python> prototypes/streaming-diarization/capture-guards/cost.py
Deterministic batch state output replaces a TUI for this CPU measurement.
"""
import json
import sys
import statistics
import time
from prototype import read
from moss_transcribe_diarize.app.live_capture_guard import observe_capture_span

system = read('interview_bill_ackman_60s')
near = read('interview_keyu_jin_60s')
chunks = [(system[i:i+8000].tolist(), near[i:i+8000].tolist())
          for i in range(0, min(len(system), len(near))-7999, 8000)]
rows = []
for index in range(300):
    s, n = chunks[index % len(chunks)]
    started = time.process_time_ns()
    state = observe_capture_span(s, n, sample_rate=16000, correlation="--correlation" in sys.argv)
    rows.append(dict(chunk=index, cpu_us=(time.process_time_ns()-started)/1000, state=state))
print(json.dumps(dict(correlation="--correlation" in sys.argv, chunks=len(rows), samples_per_chunk=8000, clock='process_time_ns',
                     median_us=statistics.median(r['cpu_us'] for r in rows),
                     max_us=max(r['cpu_us'] for r in rows), rows=rows), indent=2))
