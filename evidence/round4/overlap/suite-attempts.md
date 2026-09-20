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

## Follow-on full gates

- Backend: **1 failed**, 2,118 passed, 5 skipped, 3 xfailed, 37 subtests passed in 182.62 s.
- Sole failure: `test_verify_layout_current_tree`; the generic repository policy rejects root `VERIFY.md` and `VERIFY-RESULT.md`, which this lane's lead explicitly required at clone root. No product test failed; the mandated files were retained and the conflict was not hidden by changing the policy test.
- Frontend: 311/311 passed.
- TypeScript typecheck: passed.
- Vite production build: passed, 34 modules transformed.
