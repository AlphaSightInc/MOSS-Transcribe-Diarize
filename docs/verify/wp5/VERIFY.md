# WP5 — execute in a NEW context, in MOSS:3.2

First cd `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp5-browser-stress`.
Read this file, `prototypes/browser-stress/NOTES.md` and `README.md`. Modify nothing outside this worktree.
The user requires actual `/new` in this pane before these steps; do not substitute a same-context reread.
No push/merge/deploy/GitHub/shared-service changes. Read-only shared Python/node_modules/corpus reuse is authorized.

## What to run, literally

1. `git status --short; git branch --show-current; git rev-parse HEAD`
   Expected branch `mvpfix/wp5-browser-stress`, clean at handoff. Check no owned old processes still listen on 17865/18105 before running.
2. `bash prototypes/browser-stress/verify.sh`
   Runs frontend, typecheck, build, exact existing locator sentinel tests, then real headless browser subset with own stack/tunnel. All runtime writes use ignored `runs/wp5`. The bench keeps a cumulative <=200 decoder request budget, already 113 used; do not reset it. Trap stops the tunnel; case14 stops its replacement server.
3. Read `evidence/mvpfix/wp5/fresh/{frontend.txt,typecheck.txt,build.txt,sentinels.txt,verification.json}` and `fresh/browser/campaign-results.json`.
   Expected frontend **206/206**, locator **3/3**, typecheck/build success. Browser **6 PASS / 2 known FAIL out of 8** (cases 1,10,11,12,13,14 PASS; 8/9 FAIL solely because N1 lacks causes). Compare exact counts to logs, not the script's summary labels.
4. Confirm no processes started by verification remain. Inspect `git diff --stat`; build should not change tracked assets. Confirm no audio, database, credentials or private transcripts are staged.
5. Write `VERIFY-RESULT.md` with actual pass/fail, exact denominators, command, commit verified, decoder count, remaining N1 and hidden-tab limitations, and **actual fresh-context status**. If any expectation fails, retain it and report; do not self-retry to erase failure.
6. Commit only this worktree's verification evidence and VERIFY-RESULT.md locally (no pushes). Report <=60 lines in this pane: branch + final SHA, question/verdict, changed files, exact tests, measurements, limits/deviations. Final baseline is `evidence/mvpfix/wp5/verdict.json`: **11 PASS / 2 FAIL / 1 BLOCKED of 14**. New 8-case verification does not replace that population.

## Falsifiers

Any different browser status population; generic N1 failure called explained; hidden=false called hidden evidence; incomplete download accepted as complete; cookie values/transcripts lost; 60 rows/two-Refresh/400px invariant fails; frontend/sentinel/typecheck/build fails; real decoder cap exceeded; other-tree mutation.

## Scope and outcome

No production changes were justified. All apparent additional failures were corrected measurement errors; originals remain under `base`, `base-02`, `base-corrected`. N1 belongs to WP4, so this branch adds a standing bench and reports its reproduction. Case3 is BLOCKED: real headless Chrome stayed visible, including a separate CDP minimization probe. It needs a browser configuration that genuinely enters hidden state; never spoof visibility. No microphone fidelity, quality, deployment, or paid-provider claim.

Read `NOTES.md` for caveats: synthetic microphone readiness signal, system-tab corpus speech, scratch history fixtures, shipped UI 5-second Stop, expected abort/retired-session-404 errors. The protected production policies and exact two-Refresh sentinel remain untouched.
