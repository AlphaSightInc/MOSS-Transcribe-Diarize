# PANE 3.2 full-suite gate

Candidate branch `round3/identity`; tested SHA `4fef0c51ef9f233158cde5fe9a918cbb951c5cc9`.

## Backend

Command:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
-m pytest -q -p no:cacheprovider tests
```

Result: **2,037 passed, 5 skipped, 37 subtests passed, 0 failed**; 21 warnings.
Pytest duration 177.73 s; `/usr/bin/time` wall 178.85 s, user 128.12 s, sys 50.01 s.
A Playwright `TargetClosedError` shutdown warning was printed after 100%; it did not
change the zero exit status or any count.

## Frontend

- `npm --prefix frontend test -- --run`: **28 files, 288/288 tests passed**;
  Vitest 3.05 s; wall 3.62 s, user 11.26 s, sys 4.88 s.
- `npm --prefix frontend run typecheck`: **PASS**; wall 1.37 s, user 2.53 s,
  sys 0.13 s.
- `npm --prefix frontend run build`: **PASS**, 34 modules, Vite 87 ms;
  wall 0.53 s, user 0.44 s, sys 0.28 s.

Post-build `git status --short` was empty. No frontend or generated-asset delta.
