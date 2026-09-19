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

## Final candidate pre-verification rerun

After fresh attempt 1 exposed root-document and moving-SHA harness defects, the
canonical document move and deterministic guards were committed as
`5c05c4a400111be8311a4152de0be72a9f746802` and the entire gate was rerun.

- First dirty-index attempt: backend **2,036 passed / 1 failed / 5 skipped / 37
  subtests** in 181.35 s. The sole failure was
  `test_verify_layout_current_tree`: the unstaged index still tracked root
  `VERIFY.md`. Frontend remained 288/288; typecheck/build passed.
- Committed candidate backend: **2,037 passed / 0 failed / 5 skipped / 37
  subtests**; 21 warnings; pytest 182.84 s; wall 183.89 s, user 125.93 s,
  sys 54.17 s.
- Committed candidate frontend: **28 files, 288/288 tests passed**; Vitest
  2.56 s; wall 2.98 s, user 10.90 s, sys 3.94 s.
- Typecheck: **PASS**; wall 1.22 s, user 2.44 s, sys 0.12 s.
- Build: **PASS**, 34 modules, Vite 58 ms; wall 0.38 s, user 0.42 s,
  sys 0.22 s.
- Product/test/frontend diff from `a7a738cf`: empty. Post-build worktree: clean.
