# Round-3 pane 3.4 full-suite gate

- Candidate: `af7cf97b1f0dd1abc308308ec214d6cef9c08137`
- Backend command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests`
- Backend: **2,055 passed / 0 failed / 5 skipped / 37 subtests** in 186.75 s; wall 187.98 s.
- Frontend command: `npm --prefix frontend test -- --run`
- Frontend: **310 passed / 310** across 28 files in 2.49 s; wall 2.92 s.
- TypeScript: `npm --prefix frontend run typecheck` clean.
- Build: `npm --prefix frontend run build` clean; 34 modules, 62 ms; committed assets regenerated.
- Invariants: base-to-candidate source diff contains no changed `QUALITY_BOUNDS`, ADR-0014 exception, identity-policy constants, live protocol, Refresh sentinel, readiness threshold, poll-delay, or `LIVE_MEETING_LIMIT` line.
- Decoder: **0/0** remote requests; no tunnel opened.

## Invalid first attempt

- An initial backend run accidentally used `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python` (Python 3.10), not the brief's mandated auto-MVP venv (Python 3.12).
- Invalid result: 1,940 passed / 39 failed / 76 errors / 5 skipped / 37 subtests in 201.07 s.
- The errors revealed two pane-owned suite compatibility defects, both fixed before the valid gate: extensionless runtime TypeScript imports and an unnecessary database snapshot in terminal settlement.
- Every file named by that invalid failure summary then passed under the mandated venv: **295 tests + 19 subtests**.
