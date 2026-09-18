# WP1 partial real-runtime evidence

Verdict and limitations: `prototypes/lane-decode-proto/NOTES.md`.
No production fix. Base remains 37979e539f04d4ea740a1a94d021cd3bb894a0e2.

- `scores.json`: nine case summaries, ordered edit counts and explicit reference
  boundary bias, derived saved-lane attribution, latency/queue/count summaries.
- Per-case JSON: capture-frame state and pre/final counts, Stop timing.
- `requests.jsonl`: all 196 completed decoder requests, timing/thread only.
- `spans.jsonl`: v4 adapter elapsed time, span sample count and reason.
- `base-regression.txt`: 70 existing tests, production imports, unchanged source.

Scoring command (raw public-corpus outputs stay ignored in prototype scratch):
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/lane-decode-proto/score.py`

Control command:
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_live_coordinator.py tests/test_live_mixer.py tests/test_live_identity.py tests/test_live_transcript_convergence.py`

The controls detect accidental import-overlay leakage/regression in normal runtime.
They do NOT test or qualify the prototype. No real decoder tests may run until
budget authorization changes: 196 of COMMON.md's 200 requests already consumed.
