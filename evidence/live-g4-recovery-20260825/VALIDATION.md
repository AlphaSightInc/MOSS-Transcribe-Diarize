# A4 validation — reviewed production diff

## Focused live contracts

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q \
  tests/test_live_transcript_convergence.py \
  tests/test_live_text_revision.py \
  tests/test_live_rolling_wiring.py \
  tests/test_live_terminal_finalizer.py
```

Result: **86 passed, 19 subtests passed**.

## Replay

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests/test_live_service_replay.py
```

Result: **29 passed, 9 subtests passed**.

## Repository

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests/
```

Result: **1160 passed, 2 skipped, 411 subtests passed in 86.02 s**. Warnings were existing
FastAPI/audioread deprecations.

## Cached production-class Jamie path

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-policy-sweep-20260825/verify_jamie_rolling_recovery.py \
  --output evidence/live-g4-recovery-20260825/jamie-production-class-probe.json
```

Result: **PASS** — windows 0-4 applied, displacement 2,720, word loss 0/24, merge/drop 0,
window 5 queued.

The production files did not change between these tests and the deployed campaign; their exact
hashes and complete patch are in `restart-post.json` and `production.patch`.
