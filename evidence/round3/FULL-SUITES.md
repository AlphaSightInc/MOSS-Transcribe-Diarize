# Round 3 pane 3.3 full-suite gate

Run from `/private/tmp/moss-round3-20260919/runner` at
`b4f8abd11f588633b8d6c6c59d5fda54d096348e`.

- Backend: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <venv>/bin/python -m pytest -q
  -p no:cacheprovider tests` → **2,052 passed, 5 skipped, 37 subtests**, 0 failed,
  179.24 s.
- Frontend tests: `npm --prefix frontend test -- --run` → **28 files, 288 tests
  passed**, 0 failed, 2.54 s.
- `npm --prefix frontend run typecheck` → clean.
- `npm --prefix frontend run build` → clean, 34 modules transformed.

No new failure required qualification. `git status --short` remained empty after build.
