# WP9 naming prototype verdict

Question: can an owner rename speakers independently of active capture?
Primitives: owned durable meeting, stable speaker ID, display label, transient capture.
Each is necessary: authority, identity, presentation and lifecycle are distinct.
Invariant: exact-ID rename survives Stop/reload without changing lifecycle or evidence policy.
Falsifier: an opened terminal meeting cannot retain a chosen label, or another ID changes.

Baseline a92bb4aa: **1/5 succeeds** (capture); after Stop, reload, old history,
file return HTTP 404 (4/4). GET/history remain readable in all five cases.
Active registry rejects terminal speakers; route also rejects apps without Live.
Store naming additionally requires active status. Browser restricts naming to capture.
File documents contain speaker labels but no stable entity IDs.

Design verdict: durable naming is feasible by selecting saved segments by entity ID,
retaining original file speaker tokens as IDs on first edit, and persisting the changed
name with the existing owner authorization. Active path stays unchanged. Terminal
meetings have no retained eligible album evidence: do not fabricate enrollment or
pending intent. Existing linked voiceprints can still be explicitly renamed.

Reference: LiveTranscribe/frontend/src/components/historyPanelSurface.tsx:133–174
renders title/meta/duration/source, no speaker-name field. No card redesign justified.
Tracker snapshot #24 originally says active naming; WP9 explicitly extends this.
#26 preserves stopped transcript labels during bank edits; keep that rule.

One command: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python prototypes/rename-after-stop/run.py
Use COMMON.md interpreter; TMPDIR=$PWD/.wp9runtime/tmp. No external decoder requests.
Prototype is absorbed into this retained replay bench for the required verification.
Synthetic transcript only; ASGI HTTP routes + disposable SQLite inside own tree.
Exports/summary are frontend functions, verified with the emitted meeting documents
and frontend regressions, not fictitious backend export routes.

Failed attempt: supplied SQLite 3.50.4 refused by exact production 3.53.4 gate.
Replay uses existing phase2-test semantic override; packaged runtime unqualified.
Batch JSON state replaces interactive TUI so the lifecycle matrix is repeatable.

## Measured fix and silence result

After fix: 5/5 route renames succeed, 5/5 GET/history documents agree, 25/25 export
outputs carry chosen names, 4/4 completed-meeting summary inputs carry those names.
HTTP/SQLite paths are real; decoder/album data in the naming probe are synthetic.
Regression restore: base code fails 10/10 new saved-naming tests; silence passes.
Corrected frontend regressions on base: 6 failed, 18 passed (24 total).
Initial frontend baseline had 8 failures because 2 summary assertions incorrectly
asked the production summary builder to accept active meetings; corrected those tests.

WP7 fixture replay: Adam Frank 49–109 s, replace 25–35 s with digital zeros.
Original birth span 25.25–27.75 s: 0 nonzero bytes, 0 decoder requests,
0 identity preparations, 0 extra births, existing speaker list unchanged.
Production RunnerBoundedWavInference + LiveCoordinator already enforce this on the
integrated base. No identity change needed. Full 60 s acoustic rerun unmeasured;
this measurement isolates the exact previously observed bad span.
Run: python prototypes/rename-after-stop/silence.py (same interpreter/environment).

Prior phase2-only suite (not the full tests tree): 805 passed, 2 failed, 22 errors
(829 total), 109.74 s.
All 24 failures reproduce with original production files at a92bb4aa:
- draft reader multiple replacement fixture: expects 2 rows, receives 0;
- runner composition fixture: zero PCM expects 1 request, receives 0 (WP3 guard);
- export oracle: 22 setups fail Node's extensionless transcriptOrder import.
These are unchanged integration failures, outside WP9 fixes. Frontend 239/239,
27/27 files; typecheck/build passed. Generated JS and sourcemap rebuilt.

Boundary deviation discovered in the mandated full suite: existing tests create and
remove hardcoded /tmp Unix sockets and a /tmp temporary directory despite TMPDIR.
No outside source/worktree/shared-service changes were made. Do not repeat the full
suite uncontained; fresh verification uses the affected naming suites (which keep
all temporary files inside this worktree) and rereads retained full-suite failures.
Existing UI tests regenerated WP2 screenshots here; restored those bytes from base.
Not deployment, acoustic qualification, or an attended browser acceptance claim.

## Fresh-context verification, 2026-09-18

Verified 97f09c3a from a clean fresh-context start. Full Python `tests`: 1,753 passed,
19 failed, 22 errors, 2 skipped (1,796 items), plus 37 passed subtests, 137.99 s.
This corrects the earlier phase2-only denominator. Full frontend: 239/239 in 27 files,
including a second run consuming fresh route documents; typecheck/build pass.
Fresh route matrix: base 1/5, WP9 5/5; 25/25 exports, 4/4 completed summary inputs.
Exact silence span: 0 nonzero bytes, decoder calls, identity preparations or births.

All failing whole files rerun on scratch archive a92bb4aa, from its own cwd:
- tests/phase2/test_draft_lane.py: 14 passed, 1 failed (zero PCM yields no rows).
- tests/phase2/test_runner_composition.py: 12 passed, 1 failed (zero PCM: no request).
- tests/phase2/test_export_oracle.py: 22 errors (extensionless Node import).
- tests/test_live_pipeline_seams.py: 52 passed, 15 failed (zero guard bypasses fixtures).
- tests/test_live_rolling_wiring.py: 27 passed, 1 failed (salvage fixture bypassed).
- tests/test_live_service_replay.py: 23 passed, 1 failed, 9 passed subtests (failed vs final).
All 41 node IDs/outcomes/normalized tracebacks match WP9; 0 introduced failures.
WP10/79467f08 integration repairs remain separate; full suite is not green.

User explicitly required the full suite. Retained containment helper temporarily
relocates hardcoded /tmp destinations inside this tree and restores source files and
three screenshots. Initial relocation hit the macOS socket path limit (3 failures,
also reproduced on base); relative socket spelling resolves it, 3/3 base/full run.
Stopped initial full attempt retained, followed by the completed full run above.
No production fix made during verification. Full commands, counts, source review,
per-node classification and deviations: root VERIFY-RESULT.md and fresh-* evidence.
