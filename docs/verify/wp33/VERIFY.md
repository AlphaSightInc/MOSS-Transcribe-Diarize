# WP33 fresh-context verification

Only modify `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp33-crossreview-fixes`.
Branch `mvpfix/wp33-crossreview-fixes`; base `0e97c71b503435b76e47c158daa0c7554a85a89f`.
No push/merge/rebase/deploy/GitHub/GPU/shared service. Local commits authorized.

1. First cd to that worktree. Read COMMON then WP33-crossreview-fixes briefs under
   `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/`;
   read AGENTS.md, this file, and evidence/mvpfix/wp33/NOTES.md.
   Verify own branch/status/SHA. Read drafting-thread.txt and current CODEX_THREAD_ID;
   they must differ. Record actual fresh thread ID, never infer freshness from a
   dispatch log. If not fresh, stop and report that accurately.
2. Inspect `git diff 0e97c71b..HEAD` (exclude generated assets/raw logs as needed).
   F1: OR either lane, sum seam/counter totals, retain lane window diagnostics and
   failures, including all-refused path; shared plan/runner geometry unchanged.
   F2: existing callback closes capture, error/Reset, Not connected; WP27 intact.
   F3: no-lane speaker-bearing keys retain legacy bytes; tagged keys retain suffix.
   F4: selected required SKIP remains visible; harness exit2, bundle INCOMPLETE/
   qualified false; shell propagates code2. FAIL precedence; optional long skip allowed.
   F5: historical 3 valid/2 invalid clearly qualified; repaired two controls assert.
   Confirm protected thresholds, frame protocol, sentinel and lifecycle unchanged.
3. Execute literally, once; this detects regression, stale assets, and false PASS:
   `sh evidence/mvpfix/wp33/verify.sh`
   Expected: fresh-status PASS; native finalizer 3/3 flags and 3/3 final; legacy
   5/5 byte parity, JSON497; qualification 13 PASS/1 SKIP -> exit2/INCOMPLETE;
   2/2 repaired assertion controls, no TypeError; bundle helpers 7 passed;
   full Python 1962 passed/4 skipped/21 warnings/37 subtests; frontend271/28 files;
   typecheck/build exit0; rebuilt tracked assets identical; layout PASS.
   A wrong import path, missing warning, absent Reset/stale connection, export
   mismatch, false qualification acceptance, malformed mutation, failing test,
   changed asset bytes, or changed protected contract falsifies completion.
   Preserve any failed attempt; investigate only inside this worktree.
4. Write `docs/verify/wp33/VERIFY-RESULT.md`: actual pass/fail, source SHA, actual
   drafting/fresh thread IDs, exact counts/timings, F1–F5 before/after, limitations
   and deviations. Append fresh results link to NOTES. No claim of physical/GPU
   or deployed acceptance. Clear owned .wp33 scratch and confirm no owned processes
   remain; retain committed evidence only. Commit fresh result/evidence locally.
5. Final report in this pane <=60 lines: branch/final SHA; prototype question/verdict;
   F1–F5 before/after; changed files; tests with counts/timings; remaining limits;
   contract deviations. Do not notify another pane or perform publication.

Draft gates already ran before this file: Python1962/4 skips/37 subtests, 170.76s;
frontend271/28 files, 2.47s; typecheck/build pass. Fresh run must independently repeat.
