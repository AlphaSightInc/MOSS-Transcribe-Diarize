# WP32 actual fresh-context ten-row verification

This file is the complete new-session assignment. Drafting is finished and full
suites passed before this file was written. Work **only** in:
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp32-final-crossreview`.
Branch `mvpfix/wp32-final-crossreview`; reviewed base `37979e53`, source HEAD `d8fa767f`.
No push/merge/rebase/deploy/GitHub, GPU, shared-service operations or other-tree writes.

1. First cd there; read external COMMON.md then WP32-final-crossreview.md in
   `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/`.
   Read AGENTS.md, this file, `docs/audits/mvpfix-final-crossreview-20260918.md`,
   and `evidence/mvpfix/wp32/NOTES.md`. Read the audit's Standards and Spec artifacts
   as needed. This is a verification task, not a new whole review or repair.
2. Record branch, HEAD, clean status and **actual CODEX_THREAD_ID**. Compare with
   `evidence/mvpfix/wp32/drafting-thread.txt`; different session required. Read
   `evidence/mvpfix/wp32/new-session-dispatch.txt` if present, but do not treat
   a dispatch log alone as proof of `/new` execution. Current session context and
   identity establish freshness. Never label an in-context rerun fresh.
3. Independently check exactly the ten audit rows below. Open cited production
   files, base Git objects and retained logs; do not merely trust table prose.
   Retain row-by-row PASS/FAIL with specific evidence in
   `evidence/mvpfix/wp32/fresh-spot-check.md`. Here PASS means the audit statement
   is accurate, including its negative/qualified claims; it does not accept bugs.

| Row | Literal spot-check task and falsifier |
|---|---|
| V1 | Compare base/current QUALITY_BOUNDS, album constants, provider override readers, ControlPanel readiness, SILENCE_RMS and CSS root tokens using `git diff 37979e53..d8fa767f -- <cited files>` plus `git blame`. Fails if any protected value changed or claim omits a change. |
| V2 | Open queue/tape/frame/sentinel/Stop cited lines. Confirm nine keys, two Refresh, per-tape cap and three tapes; compare base Stop drain infinity. Fails if aggregate memory is claimed unchanged or cap/protocol/sentinel changed. |
| V3 | Independently inspect all five frontend unit assertion replacements (`ControlPanel.test.tsx`, `TranscriptPane.test.tsx`) and WP10/12/17/27 cited fixture/evidence. Confirm old assertions retained where stated. Spot-check deletion inventory against actual two-dot diff. Fails if a weakened assertion is mislabeled correction. |
| V4 | Open workspace missing-model SKIP and exit predicate, WP28 skip branch, and WP12 mutation-log failures. Confirm SKIP can exit0 and two terminal controls have invalid TypeError mechanism. Fails if presented as summary acceptance or 5/5 valid mutation kills. |
| V5 | Trace new admission/saved rename owner checks and outcome fields; inspect fixed URL/notice/guard producers and redirect/User-Agent delta. Fresh focused tests cover foreign rename404 and secret-bearing synthetic errors. Fails on unqualified privacy/owner claim or actual leak. |
| V6 | Read TLS subprocess argv/config parsing and bundle metadata. Check WP24 build-identity local path and live-browser public-corpus source collection. Fails if evidence is called universally path/content-free or credential/private transcript leak overlooked. |
| V7 | Read terminal pool join, separate lane preparers, embedding ordered-map/reduction and finally tape release. Compare Stop server deadline at base. Fails if shared mutable lane state, early publication or new unbounded authority is missed. Native-hang proof remains unmeasured. |
| V8 | Inspect legacy selector and terminal isolation test; no-lane persistence test. Execute export probe below; expect 4/5 byte identical, JSON497→523. Fails if real-ASR/all-input byte parity is claimed or probe differs. |
| V9 | Search production frontend for unsafe HTML sinks, inspect reason/notice rendering and Reset condition. Execute ended-track probe below; expect configuring, Reset false,1 witness passed/23 filtered. Fails if audit labels gap new or says all recovery works. |
| V10 | Execute actual native finalizer/compositor/publication probe below. Expect flags false,true,false for none/system/microphone truncation;2/3 correct;all3 applied/final. Fails if reproduction absent or a pre-publication running state is mislabeled final. |

4. Run literally `sh evidence/mvpfix/wp32/fresh-probes.sh`. It keeps outputs/cache/temp
   in this worktree; shared node_modules only read, Vite runner loader. Expected
   focused Python **108 passed,2 skipped**, frontend witness **1 passed,23 filtered**,
   legacy/truncation results above. Do not rerun full suites without a changed source
   or new failure: WP32 fresh contract is ten rows. Independently open prior full logs:
   `python.txt`:1941 passed,4 skipped,21warnings,37subtests,182.76s;
   `frontend.txt`:265passed/28files,2.95s; typecheck exit0. Skips in `skips.txt`.
5. If a source claim is wrong, correct audit and record discrepancy. Nontrivial
   product defects remain findings for Fable; only trivial unambiguous fixes allowed.
   Write `docs/verify/wp32/VERIFY-RESULT.md`: actual fresh thread, source and audit SHA,
   10-row numerator/denominator, command counts, unresolved F1–F5 and limits.
   Amend audit's last paragraph to link the completed result (do not claim acceptance).
6. Remove only own `.wp32` generated scratch and any temporary WP32prototype source
   after commands finish. Ensure no test/process roots remain. Check no production
   diff versus d8fa767f, no audio/DB/secrets in new evidence; `git diff --check` for
   source/docs (raw logs can contain native trailing whitespace). Commit audit/result/
   fresh evidence locally, confirm clean status and final SHA.
7. Final report **<=60 lines in this pane**: branch/final SHA; review base/source;
   F1 new truncation, F2 pre-existing Reset, F3 JSON divergence; F4 SKIP and F5 mutation
   qualifications; protected invariants; prototype verdict; full/fresh exact counts;
   files changed; limits/deviations. No claim of product/deployment acceptance.

Drafting used code-review and prototype skills. Automated probes replace interactive
TUI; no source rebuild because no production changes. Fresh task must actually
finish the ten rows; queued `/new` alone is not completion.
