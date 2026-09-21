# Fresh-context verification — P-F2F6

Run from `/private/tmp/moss-round4-20260920/p-f2f6` with the pinned project interpreter.
No decoder endpoint, tunnel, GPU, or network is permitted.

```sh
git rev-parse HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -c 'import moss_transcribe_diarize as m; print(m.__file__)'
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/p-f2f6/run.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/s17-identity-rerun/run.py --plan-only --out evidence/round4/p-f2f6/s17-identity-plan.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
git diff --check
git status --short
```

Expected: HEAD descends from `0de56e1a`; import resolves inside this clone; prototype
reports F2/F6 `SUPPORTED`, 0 decoder/network; S17 prints 184 planned requests and
`REQUIRED-BEFORE-RUN`; backend 2,167 passed / 5 skipped / 4 expected xfailed /
37 subtests / 0 failed; frontend 312/312; typecheck/build/diff clean. Status may list
only `prototypes/p-f2f6/`, the S17 prototype update, F2/F6 tests,
`evidence/round4/p-f2f6/`, and `docs/verify/p-f2f6/`. Any product-code or generated-
asset change falsifies the handoff.
