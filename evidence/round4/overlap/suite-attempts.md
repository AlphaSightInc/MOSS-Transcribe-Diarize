# Suite attempts

## Invalid interpreter attempt

Command used the dev-tree virtualenv instead of the brief-prescribed detached-worktree virtualenv:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python -m pytest -q -p no:cacheprovider tests
```

Result: 2,078 passed, 38 failed, 5 skipped, 2 xfailed, 37 subtests. This is not a valid gate result. Representative isolated failures persisted because tests spawning `sys.executable -I` bypassed `PYTHONPATH` and imported the dev virtualenv's editable install. Action: retain this failed attempt, switch to the exact interpreter required by `COMMON.md`, confirm import custody, and rerun all gates.

## Valid full gates

- Backend with the prescribed interpreter: 2,116 passed, 5 skipped, 2 xfailed, 37 subtests in 195.90 s.
- Frontend: 311/311 passed.
- TypeScript typecheck: passed.
- Vite production build: passed, 34 modules transformed.
