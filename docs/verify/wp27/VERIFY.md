# WP27 fresh-context verification

Run after `/new` in MOSS:3.4. Work ONLY in:
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp27-early-share`
Branch: `mvpfix/wp27-early-share`; base `d3ca29dcfb79da24d05da9a4599fd0b50e7e25df`.
No push/merge/rebase/deploy/GitHub, no shared services/ports 7861 or 7862, no GPU.

1. `cd` to the worktree. Read AGENTS.md, then the external briefs in order:
   `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/COMMON.md`
   and `WP27-early-share.md` in that directory. Read this file fully.
2. Record `git branch --show-current`, `git rev-parse HEAD`, and `git status --short`.
   Expect the WP27 branch and a clean committed worktree. Inspect
   `git diff d3ca29dc -- frontend/src/components/ControlPanel.tsx frontend/src/components/ControlPanel.captureFailure.test.tsx`
   and read `evidence/mvpfix/wp27/NOTES.md` plus `docs/design-capture-setup.md`.
   Confirm tests use real CaptureClient; devices/HTTP alone are simulated.
3. Run literally: `sh evidence/mvpfix/wp27/verify.sh`.
   It writes all output inside the worktree and runs the entire Python/frontend suites,
   typecheck, build, and an asset equality check. Expected: Python 1917 passed,
   2 skipped, 37 subtests passed; frontend 264 passed across 28 files; typecheck/build
   exit 0; no asset diff. No Python source/test change is expected.
4. Falsifiers: early Share explanation disappears after microphone completion;
   both failures are not named; Reset is unavailable on setup error; old setup
   completion changes a reset/new panel; nonzero stale meters; tracks/handlers survive
   Reset; readiness changes; full-suite regression; rebuilt assets differ.
   Review the retained event traces in fresh-frontend-full.txt against these conditions.
   Fourteen WP27 cases are appended to the existing nine capture-failure cases.
5. Record actual fresh session identity (`CODEX_THREAD_ID`, if available), verified
   source SHA, pass/fail, exact counts/timings and observations in `docs/verify/wp27/VERIFY-RESULT.md`.
   Do not label an in-context rerun fresh. If any check fails, diagnose within scope;
   retain failed attempts, fix, rerun affected and required full gates before reporting.
6. Commit docs/verify/wp27/VERIFY-RESULT.md and fresh evidence locally after success. Confirm clean
   status and final SHA, then deliver <=60-line report in THIS pane: branch/SHA,
   prototype question/verdict, files changed, exact tests/measurements, remaining
   limits and deviations. Physical devices unmeasured. Report the separately observed
   pre-existing pre-session track-ended recovery gap without expanding this fix.

Implementation baseline already passed both full-suite gates before this file was written.
