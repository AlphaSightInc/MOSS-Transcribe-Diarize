# WP9 fresh-context verification

This file is the complete fresh-session assignment. Work only in:
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp9-rename-identity`
Branch `mvpfix/wp9-rename-identity`; base `a92bb4aa88f9581b46cefcafae98c80e911a1d3b`.
No push/merge/deploy/GitHub, no other worktree edits, no shared services.
The preceding session implements WP9; do not treat its claims as fresh verification.
The original user explicitly requires `/new` in MOSS:3.4 before this assignment.

## Contract and falsifiers

Owner can name any opened terminal live/file meeting. Exact speaker ID selects rows;
names persist through GET/history/reload/export/summary input. Existing active naming,
account authority, pending enrollment clearing and thresholds must remain unchanged.
Terminal meetings without retained eligible album evidence report unavailable enrollment;
never fabricate a voiceprint/pending intent. Existing linked profiles remain renameable.
LiveTranscribe cards have no speaker field; leave their layout unchanged.
WP7's zero-filled 25.25–27.75 s birth span must produce no decoder/identity calls.
Falsify on lost/incorrect name, changed other speaker, foreign mutation, a silence birth,
wrong default enrollment state, or any new failure attributable to WP9.

## Execute literally

1. `cd` to the worktree above. Inspect `git status --short`, branch and HEAD. Read
   `prototypes/rename-after-stop/NOTES.md`, then review the production diff against
   `a92bb4aa` for the stated contract. No new architecture or thresholds are authorized.
2. Run `bash prototypes/rename-after-stop/verify.sh`. It keeps scratch in this tree,
   uses the supplied Python with `PYTHONPATH=.`/no bytecode, and verifies the module path.
   Expected: routes 5/5; unchanged exact silence span: 0 nonzero bytes, 0 decoder calls,
   0 identity preparations, 0 extra births; affected Python tests 20/20;
   frontend 239/239 in 27 files; typecheck/build success. Fresh route evidence goes to
   `evidence/mvpfix/wp9/fresh-prototype.json`; frontend also consumes committed real
   route documents for 25 exports and four completed summary inputs.
3. Inspect all output and `git diff --check`. The script deliberately re-runs the
   already-failing integration nodes: expect 2 failures + 22 setup errors. These
   reproduced with original production files, recorded in `suite-failures-baseline.log`.
   Confirm that failure reasons match. Do not repair unrelated integration tests.
4. Full phase2 was already required/run: 805 passed, 2 failed, 22 errors, 829 total,
   109.74 s (`phase2-full.log`). **Do not rerun the full suite uncontained**: it includes
   existing hardcoded /tmp sockets/directories that violate the own-tree constraint.
   It also regenerates WP2 screenshots, which the preceding session restored.
   Fresh verification uses affected suites plus independent reproduction of all 24
   integration failures. No shared-service or production-runtime claim is justified.
5. Write root `VERIFY-RESULT.md`: explicitly state fresh `/new` session, verified SHA,
   pass/fail and exact counts, expected integration failures/limits, any new findings.
   If a WP9 regression appears, fix only WP9, rerun its checks, report honestly whether
   any edited implementation still lacks a separate fresh-session check.
6. Commit ONLY fresh verification evidence, result, and any relevant changes locally;
   no push. Do not commit scratch, audio, credentials or unrelated screenshots.
7. Final response in THIS pane, <=60 lines: branch/final SHA; prototype question/verdict;
   changed files/behavior; exact test counts and measurements; remaining failures;
   deviations. State full suite is not green. No message to another pane is requested.

Known deviations to retain in report: batch trace instead of interactive TUI; semantic
SQLite 3.50.4 override matching existing test fixtures (production requires 3.53.4);
full-suite tests temporarily created/removed hardcoded /tmp sockets despite TMPDIR;
full 60 s acoustic rerun unmeasured (exact original silence birth span measured instead).
No shared decoder calls, tunnels, service restarts or deployments occurred.

Original report sources: COMMON.md and WP9-rename-identity.md under
`/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/` (read-only).
