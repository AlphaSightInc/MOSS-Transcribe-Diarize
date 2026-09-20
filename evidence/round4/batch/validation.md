# R4-5 validation evidence

Base: `89f833acd4c654dd702664a17ed19783a2999c95`

## Prototype

Command:

```sh
prototypes/batch-startup/run.sh all
```

Result: `SUPPORTED`; 10/10 deterministic cases. Full state:
`prototype-all.json` and `prototypes/batch-startup/results.json`.

## Focused controls

Command: pytest over the existing workspace-startup, File-cleanup, Live-restart, and
new R4-5 strict-xfail controls.

Result: `9 passed, 2 xfailed, 1 warning in 3.45s`.

New control alone: `2 xfailed in 2.33s`. Both fail on base because startup interrupts
the valid retained File/URL Meeting and makes zero remaining delegate calls.

## Local-HF smoke

Command:

```sh
prototypes/batch-startup/run-real-smoke.sh
```

Environment forced `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`. Snapshot followed size:
1.7 GiB. Result: `SUPPORTED`; real FastAPI lifespan; 10-second human-speech File;
`completed`; 3 transcript segments / 120 text characters; 10.207 seconds; zero remote
decoder requests. Full state: `real-runner-smoke.json`.

## Full gate

Backend:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests
```

Result: `2116 passed, 5 skipped, 2 xfailed, 21 warnings, 37 subtests passed in
196.49s`. The two xfails are the intentional R4-5 violating controls; passing count
matches the `89f833ac` baseline.

Frontend:

```sh
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Result: `311 passed (311)`; TypeScript clean; Vite build clean. Generated assets had
no Git diff.

## Resource receipt

- Remote decoder requests: `0 / 0`.
- GPU lease: not acquired.
- Tunnel: not opened.
- Network: not used.
- SQLite: host Python 3.50.4 substituted for required 3.53.4 only inside the prototype,
  matching the explicitly permitted P2 semantic-store allowance.
