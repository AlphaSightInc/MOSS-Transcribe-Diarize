# WP28 fresh-context verification — PASS

Verified 2026-09-18 in the actual new chat. The prescribed command completed once, exit 0:
`bash prototypes/streaming-diarization/wp28-file-resolver-perf/verify.sh`.
No fresh failures, retries, waived assertions, or implementation changes.

## F1 — Authority and custody

- Worktree: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp28-file-resolver-perf`.
- Branch: `mvpfix/wp28-file-resolver-perf`.
- Baseline: `d49fc50a99ec71867ddee8642f1e9b1f87e9a87e`; implementation: `418258c6`.
- Verified HEAD: `263c4bc516e85235a0d5302760d72ae042ff63e7` (implementation plus verification instructions).
- Implementation chat: `01a0b37c-6798-7603-9d79-0d77aedd7a55`.
- Fresh verification chat: `01a0b397-c27e-7c03-b126-135cfaeaa796`; own pane `%20`.
- `context-transition.json` records own-pane `/new` submitted at `2026-09-18T08:17:44Z`; `fresh/context.json` independently records the different current thread.
- Required reads completed in order: COMMON, WP28 brief, evidence NOTES, prototype NOTES. Also read the referenced execution plan and prototype skill.
- Initial status: only the expected untracked transition JSON. Import resolved inside this worktree; retained in `fresh/shell.txt`.
- Inspected the exact requested baseline-to-implementation diff: precisely three production files; default one worker, file composition four, one loaded CPU ONNX session, ordered map, scoped worker cleanup.
- No identity thresholds, admission values, QUALITY_BOUNDS, sentinel, readiness, frame, or lifecycle changes in that diff. Live test double asserts one worker.

## F2 — Question, primitives, invariant, verdict

Can independent acoustic probes run concurrently without changing ordered identity decisions? The primitive chain is audio interval -> normalized vector -> ordered mean -> serial album update and retrospective sweep. Only independent interval computation runs concurrently. Samples, interval inclusion, normalization/reduction order, policy, attribution, and diagnostics must remain identical.

Verdict: PASS on both retained real inputs. Full result byte equality: **2/2 fresh serial versus original baseline, 2/2 fresh production versus original baseline**. Thus serial and production agree for both fixtures. No probe or evidence cap/cache introduced. A mismatch, lost probe, changed live scheduling, leaked worker, suite failure, or no wall-time improvement would reject the gate.

## F3 — Complete suite results

- Python: **1929 passed, 2 skipped, 37 subtests passed**, 21 dependency/deprecation warnings; **263.00 s**. Full `tests` directory, with `WP28_REAL_FIXTURES` enabled.
- Existing skips only: `test_live_identity_real_corpus.py:60` (operator-owned corpus unavailable), `test_live_speaker_accuracy.py:44` (real F-cert corpus unavailable).
- Both WP28 real fixture tests ran: **2/2 passed, 0 skipped**. Perfect-vector cases **4/4** (1/2 voices x 3/15 windows); reverse completion preserves reduction order; failure preserves abstention and closes workers; empty/clipped intervals preserve behavior.
- Frontend: **250 passed / 28 files**, **2.70 s**. Existing shared dependencies read through the symlink; runner config loader. Three Node localstorage-path warnings, no failures.
- Whitespace and verification-layout gates PASS. Full logs: `fresh/python-full.txt`, `fresh/frontend-full.txt`.

## F4 — Fresh timing and equality

All timings below are seconds. Resolver and embedding are elapsed wall time. ONNX and feature stages sum worker durations; those sums overlap and must not be added to wall time.

| Stage | 3 windows serial | 3 windows production | 15 windows serial | 15 windows production |
| --- | ---: | ---: | ---: | ---: |
| Resolver wall | 61.135778 | 17.894112 | 320.838881 | 93.031965 |
| Embedding wall | 60.794574 | 17.539216 | 319.276420 | 91.461618 |
| ONNX worker sum | 60.517016 | 60.741316 | 317.806065 | 321.704709 |
| Features worker sum | 0.235444 | 0.409214 | 1.246623 | 2.258323 |
| Audio read | 0.035636 | 0.035791 | 0.187635 | 0.191555 |
| Asset hash | 0.302141 | 0.301640 | 1.509319 | 1.517224 |
| Session creation | 0.035331 | 0.034322 | 0.030197 | 0.030541 |

| Population / outcome (same in both arms) | 3 windows | 15 windows |
| --- | ---: | ---: |
| Embedding calls | 9 | 45 |
| ONNX probes / intervals | 107 | 575 |
| Embedded audio seconds | 391.32 | 2059.98 |
| Sessions created | 1 | 1 |
| Canonical identities | 3 | 3 |
| Unattributed segments | 0 | 0 |
| Raw window-local segments (overlap included) | 110 | 590 |
| Exact repeats within window | 0 | 0 |
| Exact repeats across overlapping windows | 1 | 14 |

- 3 windows: **3.417x speedup**, **70.73% wall-time reduction**. Complete count dictionaries and requested audio seconds equal between arms.
- 15 windows: **3.449x speedup**, **71.00% wall-time reduction**. Complete count dictionaries and requested audio seconds equal between arms.
- Fresh four-worker process peak: **1,416,167,424 bytes** after both fixtures (macOS process high-water RSS); serial peak **976,224,256 bytes**. These are not current memory or concurrent-file capacity measurements.
- Reports: `fresh-serial-{6,30}.json`, `fresh-production-{6,30}.json`; machine-readable verdict: `fresh/summary.json`. Original-text result bytes remain only in ignored scratch.

## F5 — Failed attempts, limitations, deviations

- Fresh attempt: none failed; no reruns or implementation repairs.
- Historical failures retained under `initial/`: missing pytest basetemp parent caused setup errors (controlled reproduction: 1 error); initial and diagnostic runs interrupted, no completed counts claimed. The launcher already creates the parent.
- Historical constructor mismatch: 1 failed / 1402 passed / 1 skipped / 6 subtests in 265.91 s. Fake constructor was fixed before this verification and asserts live remains serial. Corrected initial full gate: 1929 passed / 2 skipped / 37 subtests; frontend 250 / 28 files. None waived.
- Real inputs repeat two public one-minute clips with three actual voices. The 110/590 window-local segments include overlap; they are not WP19's stitched 92/464 scored segments. Equality is complete-output preservation on these retained inputs, not broader identity accuracy.
- Other hosts, corpora, simultaneous files, and end-to-end decoding latency remain unmeasured. No decoder calls were made (0/300); no tunnel/server was needed.
- Historical prototype deviation retained: scripted CPU experiment with full JSON state, not interactive TUI; prototype was absorbed into production and regression tests. Fresh verification deviations: **none**.
- All writes confined to this worktree. Verification changes are report/evidence only; no npm install, asset rebuild, push, merge, rebase, deployment, GitHub operation, or peer message.
- Verification command and its test/probe processes exited. Post-run process inspection found no remaining WP28 verifier, suites, probe, pytest, or Vitest process (only the inspection command itself matched).

Final local evidence commit is the commit containing this report; verified code HEAD above remains unchanged.
