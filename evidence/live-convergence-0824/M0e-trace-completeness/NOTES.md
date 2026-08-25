# M0/F3 — the replay trace is complete again

**Defect (found in iteration 4, fixed here).** Every 5-minute replay trace this repo has
ever written — the checked-in `prototypes/live-file-gap-baseline-20260824/keyu-5m/` one
included — was missing its first ~30 seconds, and looked well formed while missing it.

The service holds session events in `deque(maxlen=bounds.max_events)`
(`app/live_service_runtime.py:499`, bound 1000 in the deployed descriptor). The replay
client read that stream **once, with `since_seq=0`, after the session had already ended**
(`live_service_replay.py:446`). A 5-minute session emits 1113 events, so 113 of them were
evicted before anyone asked for them. The live portal never had this defect: it already
polls with a moving cursor. Only the offline measurement path read once at the end.

**Fix.** The replay client now drains the stream once per accepted frame, carrying the
`since_seq` cursor it already had, and appends what it collected to the trace in the same
place and the same order as before. Two consequences, both deliberate:

- Completeness holds for any session length, because the cursor never leaves the retention
  window: what has to fit inside `max_events` is now one *frame period* of events (1–3 in
  production), not the whole session.
- A gap is no longer writable. If the next sequence the client asks for is already gone,
  `ServiceReplayEventLossFailure` ends the run instead of writing a hole into the artifact.

## Gate results (`gates.json`)

Fresh 5-minute pass, 2026-08-25 01:29–01:34 local, deployed service pid 82706, **not
restarted** — the fix is entirely client-side, and the descriptor it validates against is
unchanged.

| | baseline (2026-08-24) | working tree (2026-08-25) |
|---|---|---|
| service events in trace | 1000 | **1113** |
| first event seq / kind | 113 / `span_frozen` | **0 / `session_created`** |
| contiguous from 0 | no | **yes** |
| `frame_accepted` events | 540, first sequence 60 | **600, first sequence 0** |
| `span_frozen` events | 114, spans 13–126 | **127, spans 0–126** |
| first span start_sample | 438560 | **0** |

All five preregistered gates pass. Scores on this pass: live WER .1477 / DER .1100 /
spk .8900, file WER .0506 / DER .0579 — the live numbers reproduce M0d run B exactly and
the file numbers reproduce the baseline, so recording more of the stream changed no metric.

## What the truncation was hiding

`_canonical_decode_rtf_evaluation` reads this stream, so the strict RTF gate was scored on
a censored sample. With the whole stream: p95 .2320 → **.2624**, measurements 115 → 128,
and measurements above the 1.0 bound 1 → **3**. It still passes the 1.0 bound.

Every over-bound measurement is a *short* span — span 0 is 0.08 s of audio decoded in
0.244 s (RTF 3.04). Per-request overhead, not slow decoding: the 2.5 s hard-cap spans sit
at RTF .085–.13. That is the shape M2/M3 need to keep in view when they reason about the
G7 real-time budget, and it was previously invisible on the only case long enough to show
it.

## Reproduce

```bash
# the fix does not change a trace that never overflowed (three runs: HEAD, HEAD, working tree)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/probe_replay_trace_shape_identity.py
# tripwire + completeness regression tests
.venv/bin/python -m pytest tests/test_live_service_replay.py -q
# the measured 5-minute pass in this bundle
.venv/bin/python prototypes/live-file-gap-baseline-20260824/remeasure_5m_case.py /tmp/f3-<stamp>
```

`trace-shape-identity.txt` records the side-effect check: across a scripted 8-frame
session, the only fields that differ between HEAD and the working tree are the four the
runtime stamps from a real clock (`runtime_monotonic_ns`, `queue_wait_ms`,
`queued_to_processed_ms`, `canonical_processing_elapsed_ms`) — exactly the fields that
differ between two HEAD runs of the same script. Nothing else moves.

## Mutation check

- drop the per-frame drain (read once at the end, as before) → completeness test fails
- replace the gap tripwire with a cursor jump → eviction test fails

Both caught; `pytest-replay.txt` is the green run of the whole module (23 tests).
