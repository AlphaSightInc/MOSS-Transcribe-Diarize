# WP27 fresh-context verification — PASS after verification repairs

- Branch: `mvpfix/wp27-early-share`.
- Initial clean commit / verified production source: `7f4051a8a71e86bdb82b606bd990079a265625b8`.
- Fresh session: `01a0b381-b854-77c0-b04c-09c2a80acdb4` (`CODEX_THREAD_ID`), 2026-09-18 EDT.
- Implementation session recorded in NOTES: `01a0b378-4e04-72c2-808a-98ad350f5fc5`; distinct from this session. No implementation conversation was inherited.
- Worktree: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp27-early-share`.
- Read AGENTS.md, COMMON.md, WP27 brief, execution-plan sections 1–2, root VERIFY.md, NOTES.md, design note and the base-to-candidate source/test diff.
- Production source and generated assets remain byte-for-byte unchanged from the initial commit. Verification test/document corrections below are included in this result's commit.

## F1 — Literal first run failed; retained, diagnosed, repaired

Command: `sh evidence/mvpfix/wp27/verify.sh`.

Python: **1916 passed, 1 failed, 2 skipped, 37 subtests passed**, 21 warnings, **157.13 s**, script exit **1**.
Failure: `tests/phase2/test_tls_preparation.py::test_verify_layout_current_tree` — `FAIL: VERIFY.md belongs under docs/verify/<wp>/`.
The script stopped before frontend/typecheck/build. This was not the tolerated historical latency-fixture failure.
Moved root VERIFY.md to `docs/verify/wp27/VERIFY.md` and corrected its result path. The existing layout rule now passes; no Python change.
Evidence: `evidence/mvpfix/wp27/fresh-attempt-1-{origin,python-full}.txt`.

## F2 — Two descriptor-success fixtures were false positives; corrected

The deferred descriptor responses omitted required `preflight_status_lines.browser_microphone_silent`.
Real `parseCaptureDescriptor` (`frontend/src/capture/captureClient.ts:268`) rejected them; the historical trace labelled "microphone succeeded" actually showed a descriptor error.
Added real-attachment/no-microphone-error assertions at `ControlPanel.captureFailure.test.tsx:204`, and a nonempty context assertion at `:234` so cleanup cannot pass without acquiring a resource.
Assertions against old fixtures: **2 failed, 21 passed / 23**, **749 ms** (`fresh-fixture-red.txt`).
Corrected responses at `:202` and `:233`: **23 passed / 23**, **733 ms** (`fresh-fixture-green.txt`).
No new algorithm, threshold, policy, or production fix was needed.

## F3 — Interleavings and independent pre-fix control

Prototype question: which ordering of microphone setup, Share, failure and Reset loses actionable errors or resources?
Historical prototype: **9 failed / 10 baseline**, **10 passed / 10 candidate**; descriptor-success claims were undercovered as explained above.
Fresh control used the corrected current tests and real CaptureClient, replacing ONLY ControlPanel.tsx with `git show d3ca29dc:frontend/src/components/ControlPanel.tsx` temporarily, restoring candidate bytes in `finally`.
Selected all 14 WP27 cases using the test-name filter recorded in NOTES.md: **13 failed, 1 passed / 14**, 9 older cases excluded, **609 ms**, expected exit **1**.
This is a panel restoration control, not a full base-checkout suite. Candidate passes every case below in the final full suite.

| ID | Reachable ordering | Pre-fix corrected control |
|---|---|---|
| I1 | Descriptor pending → early Share → microphone success | FAIL: Share explanation overwritten |
| I2 | Microphone permission pending → early Share → microphone success | FAIL: Share explanation overwritten |
| I3 | Descriptor pending → early Share → setup rejection | FAIL: Share failure lost |
| I4 | Microphone permission pending → early Share → microphone rejection | FAIL: Share failure lost |
| I5 | Descriptor pending → early Share → Reset → old descriptor success | FAIL: old setup revives microphone state/resources |
| I6 | Microphone permission pending → early Share → Reset → old microphone success | FAIL: old setup revives microphone state/resources |
| I7 | Microphone receiving → chooser rejection/cancellation → Reset/retry | FAIL: lane/recovery copy absent; retained trace also has stale 43% meter |
| I8 | Microphone receiving → chooser returns no audio → Reset/retry | FAIL: lane/recovery copy absent; retained trace also has stale 43% meter |
| I9 | Microphone denied before Share | FAIL: explicit lane/recovery copy absent; Reset already existed |
| I10 | Attach both → microphone sound → shared-audio sound | PASS: readiness only after both lanes have sound |
| I11 | Descriptor pending → early Share → Reset → new setup ready → old rejection | FAIL: retired failure overwrites new ready state |
| I12 | Microphone pending → early Share → Reset → new setup ready → old rejection | FAIL: retired failure overwrites new ready state |
| I13 | Chooser pending → second chooser rejected → Reset → first chooser succeeds | FAIL: late completion overwrites reset status |
| I14 | Chooser pending → second chooser rejected → Reset → first chooser rejects | FAIL: late rejection overwrites reset status |

Early Share calls the real client and fails synchronously before any chooser: **0 chooser calls**. Actual chooser cancellation while the initial microphone is pending is unreachable; I7 covers admitted cancellation after microphone attachment.
14 WP27 cases were added to 9 existing capture-failure cases; this session strengthened existing cases without changing the test count.

## F4 — Production fix and fresh trace review

All paths below are under `frontend/src/components/`:
- `ControlPanel.tsx:54`, `:75`, `:433`: independent lane errors persist until Reset; combined status names failures and recovery action; errors clear meters.
- `ControlPanel.tsx:127`, `:145`, `:163`, `:174`, `:178`: current client owns callbacks/completions; retired setup is closed and late chooser tracks are stopped.
- `ControlPanel.tsx:257`, `:276`: Reset retires the client and clears lane errors. Existing Reset button remains available on error (`:429`).
- `ControlPanel.captureFailure.test.tsx:194`: 14 real-client ordering cases, including the corrected fixtures above.

Reviewed **41 fresh snapshots** (`fresh-frontend-full.txt`, summary `fresh-trace-review.json`): **15/15 error snapshots** offer Reset and have zero meters; **11/11 completed cleanup snapshots** are idle with stopped tracks, closed contexts, and zero handlers; **2/2 true microphone successes** attach a handler while retaining the Share explanation. Both-failure traces name both lanes; late failures leave the new ready panel intact. Normal readiness still requires sound from both lanes.
CaptureClient is not mocked. Browser device/audio APIs and HTTP are simulated; unrelated poller/final-summary collaborators are stubbed. These traces do not measure physical devices.

## F5 — Final full gates

Reran literally `sh evidence/mvpfix/wp27/verify.sh` after the two repairs; **exit 0**. This rerun occurred inside the fresh verification session, not another fresh session.

| Gate | Actual result | Retained evidence under evidence/mvpfix/wp27/ |
|---|---|---|
| Python import origin | Inside assigned worktree | fresh-origin.txt |
| Entire Python suite | **1917 passed, 2 skipped, 37 subtests passed**, 21 warnings; **157.14 s** | fresh-python-full.txt |
| Entire frontend suite | **264 passed / 264**, **28 files / 28**; **2.61 s** | fresh-frontend-full.txt |
| Typecheck | **exit 0**; separate elapsed time not instrumented | fresh-typecheck.txt |
| Production build | **exit 0**, **34 modules**, **63 ms** | fresh-build.txt |
| Asset equality | **exit 0**, **0-byte diff** | fresh-assets-diff.txt |
| Whitespace check | `git diff --check`, **exit 0** | executed by verify.sh |

## F6 — Limits and deviations

Physical microphone/permission/chooser behavior unmeasured. No GPU, provider call, shared service, tunnel, push, merge, rebase, deploy, or GitHub operation was used. Worktree-local scratch was removed by verify.sh; no server was started.
Pre-existing pre-session track-ended recovery gap remains: `captureClient.ts:1110` marks a lane failed without notifying the panel's pre-session failure callback, so the panel can remain configuring without Reset. Earlier failed attempts retain this observation; source inspected here, no separate physical reproduction or repair claimed.
Readiness logic, identity policy, QUALITY_BOUNDS, nine-key frame protocol, sentinel and backend lifecycle code are unchanged.
Deviations from the original verification file: relocated verification documents to satisfy the repository's enforced layout; repaired two invalid success fixtures and added non-vacuous assertions. No fresh-session claim is made for a second context reset. Initial failure and historical evidence remain retained.

Evidence formatting: the final staged whitespace check flagged trailing spaces/blank EOF lines emitted by pytest/Vitest. Removed those whitespace-only artifacts from fresh text logs; all diagnostic text and counts retained. No test or production change followed the passing full gate.
