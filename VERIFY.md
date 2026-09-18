# WP31 fresh-context verification

Run literally after `/new`, in:
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp31-data-durability`
Modify nothing outside this worktree. No decoder/network calls, push, merge, deployment,
GitHub or shared-service actions. Do not read earlier conversation. Read this file first.
The code branch is `mvpfix/wp31-data-durability`; parent integrated SHA `ea89af0c`.
Private `.wp31` stores are COPIES. Never open older originals read-write.

## Purpose and falsifiers

Verify retained claims, then independently reopen every extended copied store. Any
lost old transcript, missing new meeting, unavailable referenced audio, refusal mutation,
or mismatch with explicit rollback/hot-copy limitations fails this verification.
No product-source fix was necessary; changes are tests, measurement bench and operator
contracts. The base reader intentionally fails lane fidelity; do not relabel that PASS.

## Commands (in order)

```sh
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp31-data-durability
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/.wp31/tmp"
WP31_PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
git status --short --branch
git rev-parse HEAD
"$WP31_PY" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
"$WP31_PY" prototypes/data-durability/verify_retained.py > evidence/mvpfix/wp31/fresh-retained.txt 2> .wp31/fresh-retained-errors.txt
"$WP31_PY" -m pytest -q -p no:cacheprovider --basetemp=.wp31/pytest-fresh tests > .wp31/python-fresh.txt 2>&1
npm --prefix frontend test -- --run > .wp31/frontend-fresh.txt 2>&1
git diff --check
lsof -nP -iTCP:18131 -iTCP:18132 -iTCP:18133 -sTCP:LISTEN
```

Expected: package resolves in this tree; retained verifier PASS, 13 stores / 60 meetings /
47 preserved old transcripts / 13 new meetings / 60 referenced audio files. Full Python
1945 passed, 4 skipped, 37 subtests; frontend 264 passed / 28 files. `lsof` should return
no listeners (exit 1 is expected). Full-suite preflight already passed on the final tests:
1945 passed / 4 skipped / 37 subtests; frontend 264/264. Local exact SQLite runtime-pin
bypass is confined to the supplied harness/test fixture, documented in NOTES.

If a command fails, inspect its private log, retain failure and identify product vs
instrument cause. Do not overwrite/re-run a failed decoder measurement. A missing
`.wp31` input means BLOCKED for real-data verification, never synthetic PASS.
`verify_retained.py` uses `.wp31/verify-extended` once; preserve failed output before any
instrument repair. No additional live decoder runs are needed or authorized here.

## Record / report

Write `VERIFY-RESULT.md`: tested SHA, commands, PASS/FAIL and exact counts, known limits.
Retain only content-free numeric test summaries under `evidence/mvpfix/wp31/` (raw logs
remain `.wp31/`). Commit verification results locally on this branch; no amend needed.
Then report here in <=60 lines: branch + final SHA; prototype question/verdict; changed
files; test counts; 13/47/235/13 upgrade numbers; 2/2 TERM segments and partial MP3,
same-document new capture; 107/200 decoder requests; explicit rollback/hot-copy limits.
Nonempty real voiceprints, host reboot/cold model cache and base writes to per-lane
meetings remain UNMEASURED. Browser device input was simulated public speech;
HTTP/ASR/storage were real. Both failed recovery-instrument attempts are retained.
All processes started by the implementation session were stopped before `/new`.

Read `evidence/mvpfix/wp31/NOTES.md` only after running the checks, for final report
context. Do not turn a local journey into deployed production qualification.
