# MVP fix campaign ledger — 2026-09-18

**Integrated source repairs are substantial; whole-product acceptance remains incomplete.**
WP34 freezes integration at `a625d1a17d103fd522fb734335aa691aa09085f7` (WP31 accepted and merged),
as of **2026-09-18T09:04:52.867295+00:00**. Source fixes, branch verification, measured workflows and release
acceptance remain separate. No deployment, attended G7, physical echo, visual sign-off,
final-SHA capacity or live summary success is claimed.

## Population and custody

Exactly **WP1–WP34 (34 rows)**. WP1–WP22 below preserve WP23's historical snapshot
at `c609d7f3`; their past-tense status is superseded where stated in the current-state
addendum below. WP23–WP33 have new pinned rows; WP34 is this documentation change.
Current branch pins, creation bases, all commits and exact changed-file inventories:
[`WP34 source index`](../../evidence/mvpfix/wp34/source-index.json).
The [WP23 source index](../../evidence/mvpfix/wp23/source-index.json) remains historical.
Other worktrees are read-only. Test scopes, skipped cases, subtests and repeated runs
are never summed. WP25/WP30/WP33 are **in flight as of the timestamp above**;
WP33 has zero commits beyond its creation base, so ancestor status is not a WP33 merge.
Committed source results are copied under `evidence/mvpfix/wp34/sources/` for portable
inspection. WP25's additional working-tree result is marked incomplete/uncommitted.
No new speech, encoder, GPU or provider measurement was performed by WP34.

Verdicts: **fixed** = scoped repair backed by evidence; **falsified** = proposed
mechanism rejected; **measured** = observations, including failures; **blocked** =
acceptance/progress requires missing evidence/authority. A row may contain more than one.

## Historical integration through WP19 (WP23 snapshot)

Source: `git log --first-parent --reverse 37979e53..c609d7f3`;
[retained full messages](../../evidence/mvpfix/wp23/integration-history.txt).
WP4 entered as an ancestor of WP7, not as a separate first-parent merge.

| Order | Merge | Package |
|---:|---|---|
| 1 | `622088b1` | WP7, including WP4 |
| 2 | `db8b0614` | WP3 |
| 3 | `ccc4e88c` | WP2 |
| 4 | `1a19a69b` | WP5 |
| 5 | `b31683a6` | WP1 |
| 6 | `b3e5d4d6` | WP9 |
| 7 | `5dd97206` | WP10 |
| 8 | `33a419f2` | WP11 |
| 9 | `3d5fdfe0` | WP6 |
| 10 | `5179368e` | WP13 |
| 11 | `f599c1a6` | WP14 |
| 12 | `024218b4` | WP16 |
| 13 | `de35ef36` | WP17 |
| 14 | `c2e45867` | WP18 |
| 15 | `5094206d` | WP20 (negative evidence, no product fix) |
| 16 | `8938cb2c` | WP15 |
| 17 | `c609d7f3` | WP19 |

Integration maintenance: `a92bb4aa` asset rebuild explicitly records **frontend
230/230**, typecheck/build pass. `79467f08` records **export oracle 22/22** (focused,
not full Python), fixing the TypeScript import. `d8ee6f41`, `8068afce`, `d769b010`
rebuild assets; `a73a51bd` adapts the silence-birth fixture to WP10's composition
root; `41cfebb9` relocates WP14 verification. **No final integrated full-Python
count is stated in the retained first-parent commit messages.** Do not relabel
WP10's 1792 or WP19's 1889 branch passes as a recorded final-integration count.
WP23's new local run on this integrated base: **1901 Python passed, 2 skipped,
37 subtests; 249 frontend passed (28 files)**. Logs: `evidence/mvpfix/wp23/`.
This is a local regression result, not same-head speech/capacity qualification.

WP8, WP12, WP21 and WP22 are **not merged** at this pin. WP23 imports and refreshes
WP8's two requested documents; this is not a merge of WP8's review branch.

## Historical work-package rows WP1–WP22

### WP1 — Can serial source decoding preserve words and separate speaker namespaces through saving?

**Verdict:** fixed (lane architecture); measured limits. **Tip:** `2ffd80e7ffd2dff48d6eba29f3c0d70b72e25e71`; branch `mvpfix/wp1-lane-decode`; base `37979e53`.

**Commits:** `baf9b9e6` experiment(wp1): retain partial serial lane runtime evidence; `efec6cc7` experiment(wp1): pass lane falsifiers and isolate failed refinement ownership; `2cb9d014` fix(live): decode source lanes serially with isolated speaker identity; `644833ee` fix(replay): retain lane provenance across snapshot reconstruction; `da3d1818` test(wp1): retain fixed-build evidence and prepare fresh-context verification; `2ffd80e7` docs(wp1): record fresh verification and base storage comparison.

**Verification:** 1718 passed, 3 failed, 2 skipped; 37 subtests. Frontend 206/206 (24 files). [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp1-lane-decode/VERIFY-RESULT.md).

**Measurements:** 26/26 saved/final matches; 26/26 disjoint lane speaker sets; six fixed cases; parity Stop 11.395471 s. 646 historical requests. Storage failures depend on fixtures inside protected checkout; third failure is old latency fixture.

**Unmeasured / remaining:** Matched mono live cost; complete final-SHA ladder; physical capture.

**Files (relative to source worktree):**

- Product: `moss_transcribe_diarize/app/live_coordinator.py`, `moss_transcribe_diarize/app/live_identity.py`, `moss_transcribe_diarize/app/live_lane_decode.py`, `moss_transcribe_diarize/app/live_mixer.py`, `moss_transcribe_diarize/app/live_provider_bundle.py`, `moss_transcribe_diarize/app/live_service_runtime.py`, `moss_transcribe_diarize/app/live_session.py`, `moss_transcribe_diarize/app/live_transcript_convergence.py`, `moss_transcribe_diarize/live_service_replay.py`.
- Tests/oracles: `tests/phase2/test_owner_bound_live_meeting.py`, `tests/phase2/workspace_reachability_fixtures.py`, `tests/test_live_lane_decode.py`, `tests/test_live_service_replay.py`.
- Evidence/docs/bench/tooling: `.gitignore`, `VERIFY-RESULT.md`, `VERIFY.md`, `docs/design-lane-decode.md`, `evidence/mvpfix/wp1/`, `prototypes/lane-decode-proto/.gitignore`, `prototypes/lane-decode-proto/NOTES.md`, `prototypes/lane-decode-proto/README.md`, `prototypes/lane-decode-proto/audit_evidence.py`, `prototypes/lane-decode-proto/experiment.sh`, `prototypes/lane-decode-proto/failure_state.py`, `prototypes/lane-decode-proto/pytest_local.py`, `prototypes/lane-decode-proto/run.py`, `prototypes/lane-decode-proto/run_e2e.py`, `prototypes/lane-decode-proto/score.py`, `prototypes/lane-decode-proto/stack.py`. Exact leaf paths in source-index.

### WP2 — Can lane provenance survive consumers and overlapping exports?

**Verdict:** fixed. **Tip:** `db851d2fb9a12abc142c91a146079463d8c73dcc`; branch `mvpfix/wp2-lane-consumers`; base `37979e53`.

**Commits:** `b5096c14` Preserve published lane segments across transcript consumers; `0a63fa18` Record WP2 prototype evidence and fresh verification procedure; `e820644f` Retain WP2 successful and failed measurement logs; `2d2dc7e2` fix: preserve provisional tail precedence in lane consumers; `db851d2f` test: record fresh WP2 verification and ordering correction evidence.

**Verification:** Focused Python 48/48; frontend 218/218 (25 files); restored-test control 216/218 before correction, 218/218 after. No full Python count reported. [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp2-lane-consumers/VERIFY-RESULT.md).

**Measurements:** Tagged 9 rows/9 lanes/4 IDs; legacy 5/0/2. Restored provisional-last ordering; five export formats.

**Unmeasured / remaining:** WP1 integration and human visual acceptance at this component pin.

**Files (relative to source worktree):**

- Product: `frontend/src/api/meetings.ts`, `frontend/src/api/mossPoller.ts`, `frontend/src/api/types.ts`, `frontend/src/components/MeetingHistory.tsx`, `frontend/src/components/TranscriptPane.tsx`, `frontend/src/lib/finalSummary.ts`, `frontend/src/lib/mergeTranscript.ts`, `frontend/src/lib/transcriptExport.ts`, `frontend/src/lib/transcriptKeys.ts`, `frontend/src/lib/transcriptOrder.ts`, `frontend/src/lib/transcriptSearch.ts`, `frontend/src/styles/index.css`. Generated frontend assets also changed.
- Tests/oracles: `frontend/src/api/mossPoller.test.ts`, `frontend/src/components/speakerRename.test.tsx`, `frontend/src/lib/laneConsumers.test.ts`, `frontend/src/lib/transcriptExport.test.ts`, `tests/phase2/test_lane_consumer_geometry.py`, `tests/phase2/test_lane_consumer_store.py`.
- Evidence/docs/bench/tooling: `VERIFY-RESULT.md`, `VERIFY.md`, `docs/design-lane-consumers.md`, `evidence/mvpfix/wp2/`, `frontend/.gitignore`, `frontend/vite.config.ts`. Exact leaf paths in source-index.

### WP3 — Can silence and capture failures be guarded without suppressing quiet speech?

**Verdict:** fixed guards; falsified echo suppression. **Tip:** `2e7206c7d52fed1676adc3304fe63d12a2405116`; branch `mvpfix/wp3-capture-guards`; base `37979e53`.

**Commits:** `b7695017` fix: reject live frames that declare the wrong sample rate; `fb73b30e` fix: guard silent decodes and release failed browser capture resources; `cf866016` docs(wp3): record failed fresh verification and retained checks; `2e7206c7` fix(wp3): opt in to capture correlation and audit guard evidence.

**Verification:** Final literal Python 455 passed, 2 failed (SQLite fixture order), 19 subtests; frontend 215/215 (25 files). [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp3-capture-guards/VERIFY-RESULT.md).

**Measurements:** Near-speech false suppression 80/12960 spans; echo false pass 3651/4320. Candidate never promoted; correlation opt-in/report-only. Guard-seam and fixture repairs followed in WP10/WP6.

**Unmeasured / remaining:** Physical speakers/AEC; no safe echo suppression demonstrated.

**Files (relative to source worktree):**

- Product: `frontend/src/capture/captureClient.ts`, `frontend/src/components/ControlPanel.tsx`, `moss_transcribe_diarize/app/live_adapters.py`, `moss_transcribe_diarize/app/live_capture_guard.py`, `moss_transcribe_diarize/app/live_mixer.py`, `moss_transcribe_diarize/app/live_transcript_convergence.py`, `moss_transcribe_diarize/app/live_transport.py`. Generated frontend assets also changed.
- Tests/oracles: `frontend/src/components/ControlPanel.captureFailure.test.tsx`, `tests/phase2/test_owner_bound_live_meeting.py`, `tests/phase2/test_wave1_qualification.py`, `tests/test_live_capture_guard.py`, `tests/test_live_vad.py`.
- Evidence/docs/bench/tooling: `VERIFY-RESULT.md`, `VERIFY.md`, `docs/handoffs/attended-echo-protocol.md`, `evidence/mvpfix/wp3/`, `prototypes/streaming-diarization/capture-guards/`, `scripts/attended-echo/capture.html`, `scripts/attended-echo/measure.py`. Exact leaf paths in source-index.

### WP4 — Can lane/G7/export instruments and file failures report truthfully?

**Verdict:** fixed instruments/outcomes; blocked provider acceptance. **Tip:** `a7bb420139fbd34da4c95d12aee1e0d2a00cb18d`; branch `mvpfix/wp4-oracles-n1`; base `37979e53`.

**Commits:** `755a94e4` Record WP4 oracle false-positive prototype and file boundary evidence; `5adff063` Persist safe file failure reasons and speechless notices; suggest Flash Lite; `a3ab4f82` Require attended operator phrase and add reference-aware lane scoring; `56045484` Compare every transcript export against its selected API meeting; `c14e9e24` Measure lane acceptance through Stop and reopen; retain bounded live failures; `a7bb4201` docs(wp4): record fresh-context verification and live limits.

**Verification:** Phase-2 805 passed; F6 separately 2 passed; frontend 209/209 (24 files). [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp4-oracles-n1/VERIFY-RESULT.md).

**Measurements:** Lane valid fixtures 2/2; negative fixtures 4/4 rejected; exports 5/5 positive and 15/15 corruptions rejected. Eight-word operator phrase introduced; WP7 later sets 7/8 ordered tolerance. Paid summary calls 0.

**Unmeasured / remaining:** Gemini Flash Lite 50/180 s functional checks; real attended G7. WP8 found lane export integration defects later fixed by WP11.

**Files (relative to source worktree):**

- Product: `frontend/src/api/meetings.ts`, `frontend/src/components/FinalSummary.tsx`, `frontend/src/components/MeetingHistory.tsx`, `frontend/src/lib/finalSummary.ts`, `moss_transcribe_diarize/app/phase2.py`, `moss_transcribe_diarize/app/phase2_file.py`, `moss_transcribe_diarize/app/phase2_url.py`, `moss_transcribe_diarize/lane_word_oracle.py`, `moss_transcribe_diarize/phase2_g7_canary.py`. Generated frontend assets also changed.
- Tests/oracles: `frontend/src/components/FinalSummary.test.tsx`, `frontend/src/components/MeetingHistory.test.tsx`, `tests/e2e/export_oracle.py`, `tests/e2e/verify_demo_lanes.py`, `tests/e2e/verify_summaries.py`, `tests/e2e/verify_workspace.py`, `tests/phase2/test_atomic_cutover.py`, `tests/phase2/test_attended_g7_canary.py`, `tests/phase2/test_browser_workspace.py`, `tests/phase2/test_candidate_storage.py`, `tests/phase2/test_demo_lane_measurement.py`, `tests/phase2/test_export_oracle.py`, `tests/phase2/test_file_failure_reasons.py`, `tests/phase2/test_lane_word_oracle.py`, `tests/phase2/test_voiceprint_latency_measurement.py`, `tests/phase2/test_workspace_lifecycle.py`.
- Evidence/docs/bench/tooling: `.gitignore`, `VERIFY-RESULT.md`, `VERIFY.md`, `docs/handoffs/g7-preadmission-runbook.md`, `evidence/mvpfix/wp4/`, `frontend/vite.config.ts`, `prototypes/streaming-diarization/draft-lane/`, `prototypes/streaming-diarization/wp4-oracle-falsifiers/`. Exact leaf paths in source-index.

### WP5 — Do adversarial browser actions preserve meetings and truthful outcomes?

**Verdict:** measured; blocked hidden-tab. **Tip:** `3bfec55834745e9141b4182399057f790581ee47`; branch `mvpfix/wp5-browser-stress`; base `37979e53`.

**Commits:** `43174c8f` Add WP5 real-browser stress bench and adjudicated base evidence; `fa3d00dd` Keep fresh verification tooling out of shared dependency caches; `29d69b0e` Make cache-isolated verification use explicit frontend config directory; `3bfec558` docs(wp5): record fresh browser verification and hidden-tab probe.

**Verification:** Frontend 206/206 (24 files), locator sentinels 3/3; no full Python run in result. [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp5-browser-stress/VERIFY-RESULT.md).

**Measurements:** Baseline 11 pass/2 fail/1 blocked of 14; fresh 6 pass/2 known N1 fail of 8. Hidden state 0/5 observations.

**Unmeasured / remaining:** Native hidden capture; physical mic/echo; summary provider; later candidate browser rerun.

**Files (relative to source worktree):**

- Product: none.
- Tests/oracles: none.
- Evidence/docs/bench/tooling: `VERIFY-RESULT.md`, `VERIFY.md`, `evidence/mvpfix/wp5/`, `prototypes/browser-stress/NOTES.md`, `prototypes/browser-stress/README.md`, `prototypes/browser-stress/run.py`, `prototypes/browser-stress/stack.py`, `prototypes/browser-stress/verify.sh`. Exact leaf paths in source-index.

### WP6 — What is the actual multi-session capacity and contention cost?

**Verdict:** measured; capacity not accepted. **Tip:** `06a6737a6626c51123fd2f14ab50b9e2ef5735fe`; branch `mvpfix/wp6-capacity-baseline`; base `37979e53`.

**Commits:** `a20595a5` test: keep Phase-2 SQLite fixture stable across file order; `c3d15928` prototype: prepare WP6 capacity campaign pending decoder authority; `24b31e95` fix(wp6): pause capacity replay until foreign decoder traffic clears; `57907d76` fix(wp6): report unavailable finalization and retain capacity baseline evidence; `06a6737a` Measure WP6 with isolated tape cap and correct capacity evidence.

**Verification:** Final Python 1701 passed, 1 failed (old latency fixture), 2 skipped; 37 subtests. Initial 1698 passed/4 failed. Retention 42 passed/19 subtests; frontend 206/206. [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp6-capacity-baseline/VERIFY-RESULT.md).

**Measurements:** Five attempts/13 sessions: 9 complete, 4 interrupted. 4x600: 2/4 final, 2 helper-lease interruptions; 3 pauses total 269.986569 s; 12/32 foreign-load samples; 2887 requests overall.

**Unmeasured / remaining:** Clean four-session acceptance, eight-session overload, final-candidate capacity; missing interrupted collector states.

**Files (relative to source worktree):**

- Product: none.
- Tests/oracles: `tests/conftest.py`, `tests/phase2/conftest.py`.
- Evidence/docs/bench/tooling: `.gitignore`, `VERIFY-RESULT.md`, `VERIFY.md`, `evidence/mvpfix/wp6/`, `prototypes/capacity-campaign/NOTES.md`, `prototypes/capacity-campaign/copy_manifest.py`, `prototypes/capacity-campaign/run.py`, `prototypes/capacity-campaign/stack.py`. Exact leaf paths in source-index.

### WP7 — Do identities, private voiceprints and naming survive adversarial inputs?

**Verdict:** measured; universal identity claim falsified on old base. **Tip:** `cf8147f5d44735c0964596f0a82082c990a38f31`; branch `mvpfix/wp7-identity-stress`; base `a7bb4201`.

**Commits:** `195fa253` Calibrate operator phrase tolerance and expose lane switch attribution; `ed74e6da` Measure identity stress and retain mixed verdict with bounded real decoder evidence; `5509a757` Record shutdown of WP7 measurement services; `cf8147f5` docs(wp7): record fresh offline verification and mixed verdict.

**Verification:** Phase-2 811/811; selected frontend 5/5 (2 files), not full frontend. [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp7-identity-stress/VERIFY-RESULT.md).

**Measurements:** 13/13 final meetings; known 2/2 correct, unknown 2/2 abstain; API recognition 3.520 s. Same voice on two lanes collapsed on pre-WP1 base; silence birth and switch attribution findings retained.

**Unmeasured / remaining:** Browser name latency, full five-speaker/470-probe rerun, physical AEC. Saved naming restriction later changed by WP9.

**Files (relative to source worktree):**

- Product: `moss_transcribe_diarize/lane_word_oracle.py`, `moss_transcribe_diarize/phase2_g7_canary.py`.
- Tests/oracles: `tests/e2e/verify_demo_lanes.py`, `tests/phase2/test_attended_g7_canary.py`, `tests/phase2/test_lane_word_oracle.py`.
- Evidence/docs/bench/tooling: `.gitignore`, `VERIFY-RESULT.md`, `VERIFY.md`, `docs/handoffs/g7-preadmission-runbook.md`, `evidence/mvpfix/wp7/`, `prototypes/identity-stress/NOTES.md`, `prototypes/identity-stress/browser_check.py`, `prototypes/identity-stress/cpu_probe.py`, `prototypes/identity-stress/hygiene_followup.py`, `prototypes/identity-stress/re_enroll.py`, `prototypes/identity-stress/run.py`, `prototypes/identity-stress/stack.py`, `prototypes/identity-stress/summarize.py`. Exact leaf paths in source-index.

### WP8 — Do proposed contracts and independently generated exports agree?

**Verdict:** measured; falsified lane export oracle. **Tip:** `fcb247c25099c7499d30cd92e5306b5301d57c88`; branch `mvpfix/wp8-contract-review`; base `37979e53`.

**Commits:** `ca9acb03` docs(wp8): review lane consumers and draft effective product contract; `fcb247c2` docs(wp8): verify review and reproduce integrated export mismatch.

**Verification:** 31 ticket rows, 25 assertion rows, 12 audit rows, 7 pins, 39 paths checked; integrated focused Python 22 passed; no full suites. [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp8-contract-review/VERIFY-RESULT.md).

**Measurements:** Actual serializers: legacy 5/5 accepted, lane overlap 0/5 solely labels. F2 ordering/end projection mismatch; F3 overlap expected-failure loophole. WP11/WP14 subsequently repair these.

**Unmeasured / remaining:** Release/host acceptance; original external ledger corrections remain proposed. WP8 branch is not merged.

**Files (relative to source worktree):**

- Product: none.
- Tests/oracles: none.
- Evidence/docs/bench/tooling: `VERIFY-RESULT.md`, `VERIFY.md`, `docs/audits/mvpfix-crossreview-20260917.md`, `docs/handoffs/pr32-description-draft.md`, `docs/production-contract-20260917.md`, `evidence/mvpfix/wp8/`. Exact leaf paths in source-index.

### WP9 — Can owned saved speakers be renamed without active capture?

**Verdict:** fixed. **Tip:** `8f8847fc3e9be3fc6da4cdd2393fe285c66429dc`; branch `mvpfix/wp9-rename-identity`; base `a92bb4aa`.

**Commits:** `154869cd` fix: allow owned saved meeting speaker names after capture; `97f09c3a` docs: retain WP9 test outputs including baseline failures; `8f8847fc` test(wp9): record fresh full-suite verification and base failure proof.

**Verification:** Python 1753 passed, 19 failed, 22 errors, 2 skipped (1796 items), 37 subtests; affected 20/20. Frontend 239/239 (27 files). [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp9-rename-identity/VERIFY-RESULT.md).

**Measurements:** All six affected base files reproduce 128 pass/19 fail/22 errors: inherited guard-seam failures, addressed by WP10 and integration adapter a73a51bd. Saved names persist; cross-owner mutation refused.

**Unmeasured / remaining:** Final integrated browser acceptance; broad suite at this old branch was not green.

**Files (relative to source worktree):**

- Product: `frontend/src/api/speakers.ts`, `frontend/src/components/TranscriptPane.tsx`, `moss_transcribe_diarize/app/phase2.py`, `moss_transcribe_diarize/app/phase2_speaker_identity.py`. Generated frontend assets also changed.
- Tests/oracles: `frontend/src/components/TranscriptPane.test.tsx`, `frontend/src/components/savedNames.test.ts`, `frontend/src/components/speakerRename.test.tsx`, `tests/phase2/test_saved_speaker_naming.py`, `tests/phase2/test_wp9_silence_birth.py`.
- Evidence/docs/bench/tooling: `.gitignore`, `CONTEXT.md`, `VERIFY-RESULT.md`, `VERIFY.md`, `evidence/mvpfix/wp9/`, `prototypes/rename-after-stop/NOTES.md`, `prototypes/rename-after-stop/run.py`, `prototypes/rename-after-stop/silence.py`, `prototypes/rename-after-stop/verify.sh`. Exact leaf paths in source-index.

### WP10 — Where can digital silence be skipped without breaking inference contracts?

**Verdict:** fixed. **Tip:** `8977e4d1d4a99ba69d01d53e6d5057580e85387b`; branch `mvpfix/wp10-zero-guard-seams`; base `79467f08`.

**Commits:** `79a6d38e` prototype(wp10): harness and shared seams for the zero-guard placement question; `f369f218` fix(wp10): decide digital silence at dispatch, not inside the decode seam; `4a21a38e` test(wp10): pin the dispatch guarantees, and make the draft-lane snapshot self-consistent; `2c5318ec` docs(wp10): record the candidate matrix, the verdict and fresh-shell verification; `8977e4d1` docs(wp10): retain the harness logs the matrix is read from.

**Verification:** Python 1792 passed, 2 skipped, 37 subtests; frontend 230/230 (26 files). Focused 147/147, relocated WP3 40/40, guarantees 9/9. [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp10-zero-guard-seams/VERIFY-RESULT.md).

**Measurements:** Dispatch owns zero decision; shared predicate replaces adapter suppression; 7/7 requirements. Three candidate placements measured.

**Unmeasured / remaining:** Physical echo; silence guard is exact-zero behavior, not low-volume filtering.

**Files (relative to source worktree):**

- Product: `moss_transcribe_diarize/app/live_adapters.py`, `moss_transcribe_diarize/app/live_coordinator.py`, `moss_transcribe_diarize/app/live_provider_bundle.py`, `moss_transcribe_diarize/app/live_silence.py`, `moss_transcribe_diarize/app/live_tape.py`, `moss_transcribe_diarize/app/live_transcript_convergence.py`, `moss_transcribe_diarize/app/transcription_outcome.py`.
- Tests/oracles: `tests/phase2/test_draft_lane.py`, `tests/test_live_capture_guard.py`, `tests/test_live_service_replay.py`, `tests/test_live_zero_span_dispatch.py`.
- Evidence/docs/bench/tooling: `VERIFY-RESULT.md`, `VERIFY.md`, `evidence/mvpfix/wp10/`, `prototypes/zero-guard-seams/.gitignore`, `prototypes/zero-guard-seams/NOTES.md`, `prototypes/zero-guard-seams/falsify.py`, `prototypes/zero-guard-seams/run_candidates.sh`. Exact leaf paths in source-index.

### WP11 — Can saved provenance and independent expected exports agree?

**Verdict:** fixed. **Tip:** `57286fdf7ae75e3593c3f68eec9b862603b96811`; branch `mvpfix/wp11-export-labels`; base `b31683a6`.

**Commits:** `c30174b8` Fix export speaker labels and preserve lanes through saved live meetings; `e0bb7104` Record WP11 integrated export evidence and fresh verification contract; `57286fdf` Record WP11 fresh verification and inherited suite failures.

**Verification:** Python 1809 passed, 19 failed, 2 skipped, 37 subtests; frontend 233/233 (26 files); export oracle 50/50. [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp11-export-labels/VERIFY-RESULT.md).

**Measurements:** Lane-aware labels/order/max end and native saved source_lane; inherited seam failures retained, subsequently integrated with WP10.

**Unmeasured / remaining:** Final same-SHA download acceptance; full suite at component pin failed.

**Files (relative to source worktree):**

- Product: `frontend/src/lib/fileUpload.ts`, `frontend/src/lib/transcriptExport.ts`, `moss_transcribe_diarize/app/phase2_live.py`. Generated frontend assets also changed.
- Tests/oracles: `frontend/src/lib/fileUpload.test.ts`, `frontend/src/lib/laneConsumers.test.ts`, `frontend/src/lib/transcriptExport.test.ts`, `tests/e2e/export_oracle.py`, `tests/phase2/test_export_oracle.py`, `tests/phase2/test_owner_bound_live_meeting.py`.
- Evidence/docs/bench/tooling: `VERIFY-RESULT.md`, `VERIFY.md`, `docs/design-lane-consumers.md`, `evidence/mvpfix/wp11/`, `prototypes/browser-stress/README.md`, `prototypes/browser-stress/run.py`. Exact leaf paths in source-index.

### WP12 — What drives Stop cost, and can existing identity evidence replace terminal embedding?

**Verdict:** measured; acceptance blocked/stopped. **Tip:** `a2ee97eb4461c7c2d035635a696319b5385b2712`; branch `mvpfix/wp12-stop-latency-identity`; base `b31683a6`.

**Commits:** `33be55ec` Overlap independent terminal lane jobs after live drain; `9d10e0d8` Align decoder and draft fixtures with integrated input contracts; `a02a8491` Retain WP12 timing evidence and fresh verification procedure; `60b3b584` Measure WP12 Stop drain and terminal acoustic work; verify full suites; `c410db8f` Prototype lane terminal overlap; stop on 180s attribution mismatch; `a2ee97eb` Adjudicate WP12 terminal speakers against reference; measure mono 180s.

**Verification:** Latest current-context Python 1805 passed, 2 skipped, 37 subtests; frontend 230/230 (26 files). Latest continuation explicitly not a new /new acceptance. [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp12-stop-latency-identity/VERIFY-RESULT.md).

**Measurements:** 24 s serial 11.327668 s -> concurrent acoustic 6.839325 s -> candidate overlap mapping 3.788534 s (separate retained runs). Candidate 60/180 s: 7.490138/16.964282 s; mono180 12.717313 s. Six same-input cases 135/135 exact; source adjudication confirms 54 restored assignments, two Lex turns/16 words still unassigned.

**Unmeasured / remaining:** Not merged/accepted; no 30-minute timing; no claim the fixture is single-voice. Earlier baseline-equivalence falsification superseded by source truth.

**Files (relative to source worktree):**

- Product: `moss_transcribe_diarize/app/live_lane_decode.py`.
- Tests/oracles: `tests/phase2/test_draft_lane.py`, `tests/phase2/test_runner_composition.py`, `tests/test_live_lane_decode.py`, `tests/test_live_pipeline_seams.py`, `tests/test_live_rolling_wiring.py`, `tests/test_live_service_replay.py`.
- Evidence/docs/bench/tooling: `.gitignore`, `VERIFY-RESULT.md`, `VERIFY.md`, `docs/design-streaming-diarization.md`, `evidence/mvpfix/wp12/`, `prototypes/streaming-diarization/wp12-stop-identity/`. Exact leaf paths in source-index.

### WP13 — Can TLS renewal be prepared and mutable verification outputs isolated?

**Verdict:** fixed preparation; blocked host trust. **Tip:** `8d01ab06bb17c9a11533b1df323a3da59fe4f802`; branch `mvpfix/wp13-tls-hygiene`; base `d8ee6f41`.

**Commits:** `38b35eea` Prepare two-port TLS renewal and isolate mutable test evidence; `8d01ab06` docs(wp13): record fresh verification and retained blockers.

**Verification:** Focused 27 passed; Python 1809 passed, 19 failed, 2 skipped, 37 subtests; frontend 239/239 (27 files). [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp13-tls-hygiene/docs/verify/wp13/VERIFY-RESULT.md).

**Measurements:** 17640/17640 chunk numeric rows unchanged. Historical normal client TLS: 7861 self-signed FAIL, 7862 trusted PASS. Renewal dry-run effects 0, prerequisites untested.

**Unmeasured / remaining:** Installation, DNS writes, real renewal/reload, Chrome trust and current host status.

**Files (relative to source worktree):**

- Product: none.
- Tests/oracles: `tests/phase2/test_lane_consumer_geometry.py`, `tests/phase2/test_tls_preparation.py`.
- Evidence/docs/bench/tooling: `.gitignore`, `docs/handoffs/demo-script.md`, `docs/handoffs/e2e-smoke-for-operator.md`, `docs/handoffs/tls-renewal-runbook.md`, `docs/verify/wp13/VERIFY-RESULT.md`, `docs/verify/wp13/VERIFY.md`, `evidence/mvpfix/wp13/`, `evidence/mvpfix/wp3/`, `ops/tls/NOTES.md`, `ops/tls/renew.py`, `ops/tls/verify.py`, `prototypes/streaming-diarization/capture-guards/`, `scripts/check_verify_layout.sh`. Exact leaf paths in source-index.

### WP14 — Does the integrated build pass browser/lane/lifecycle acceptance?

**Verdict:** measured failures; fixed lease-expiry wording. **Tip:** `d562d76824e124a960230f01b9ab3f1990b303c9`; branch `mvpfix/wp14-integrated-e2e`; base `8068afce`.

**Commits:** `1b1fc692` fix(ui): explain expired live capture connections; `4b1d3401` test(e2e): measure integrated acceptance and lease recovery honestly; `b30ea628` docs(e2e): retain WP14 measurements and fresh verification contract; `d562d768` docs(wp14): record fresh verification and retained acceptance limits.

**Verification:** Initial Python 1848 passed/1 failed/2 skipped; unchanged repeat 1849 passed/2 skipped, 37 subtests. Frontend 242/242 (27 files). [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp14-integrated-e2e/VERIFY-RESULT.md).

**Measurements:** Workspace 11 pass/2 fail/1 skip of 14: quality and recognition fail, summaries skip. Lifecycle 7/7; reshare 3/6 budget-blocked. Browser bench extended to 16 cases; not a 16/16 passing claim.

**Unmeasured / remaining:** Native hidden capture; summary key/config; final-SHA reshare. WP17 corrects mic reference/recognition, WP20 retains quality failure.

**Files (relative to source worktree):**

- Product: `frontend/src/components/ControlPanel.tsx`. Generated frontend assets also changed.
- Tests/oracles: `frontend/src/components/ControlPanel.test.tsx`, `tests/e2e/stress_lifecycle.py`, `tests/e2e/stress_reshare.py`, `tests/e2e/test_smoke_options.py`, `tests/e2e/verify_demo_lanes.py`, `tests/e2e/verify_workspace.py`, `tests/phase2/test_demo_lane_measurement.py`.
- Evidence/docs/bench/tooling: `VERIFY-RESULT.md`, `VERIFY.md`, `evidence/mvpfix/wp14/`, `prototypes/browser-stress/NOTES.md`, `prototypes/browser-stress/run.py`. Exact leaf paths in source-index.

### WP15 — Does accepted Stop transfer completion away from helper lease authority?

**Verdict:** fixed lifecycle; measured long-run limits. **Tip:** `e721fc7d0a4cc712d17fa8d0db03d9fe401f9b4e`; branch `mvpfix/wp15-stop-lease-longrun`; base `3d5fdfe0`.

**Commits:** `6fa503ff` fix: end helper lease authority when Stop accepts capture; `826af986` docs: preserve cleanly formatted WP15 verification evidence; `e721fc7d` Verify WP15 Stop lifecycle and unpaused 600-second durability.

**Verification:** Python 1860 passed, 2 skipped, 37 subtests; frontend 242/242 (27 files); fresh prototype 8/8. [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp15-stop-lease-longrun/VERIFY-RESULT.md).

**Measurements:** Unpaused 600 s complete; 2589 words, MP3 600 s; Stop 179.408107 s; RSS first/peak/final 631.406/1201.047/1200.516 MiB; 460 calls. Three tapes each 19.2 MB -> zero after release.

**Unmeasured / remaining:** Unpaused 1800 s, memory plateau, 57.6 MB per-tape edge. 8/27 samples had sibling contention; not isolated latency.

**Files (relative to source worktree):**

- Product: `moss_transcribe_diarize/app/live_transport.py`.
- Tests/oracles: `tests/phase2/test_accepted_stop_lease.py`.
- Evidence/docs/bench/tooling: `.gitignore`, `VERIFY-RESULT.md`, `VERIFY.md`, `docs/adr/0004-browser-session-reattach.md`, `evidence/mvpfix/wp15/`, `prototypes/capacity-campaign/stack.py`, `prototypes/stop-lease/NOTES.md`, `prototypes/stop-lease/longrun.py`, `prototypes/stop-lease/run.py`. Exact leaf paths in source-index.

### WP16 — Do long files, silence, damaged media and URL failures produce truthful saved results?

**Verdict:** fixed zero-audio and upload preflight; measured. **Tip:** `67c020fd2c17a583532dc07afda932743eb25c22`; branch `mvpfix/wp16-file-url-long`; base `5179368e`.

**Commits:** `76665702` fix(file): skip digital silence and preflight upload capacity; `d36f0be3` test(wp16): retain real browser scale and failure evidence; `67c020fd` docs(wp16): record fresh verification and WP17 port collision.

**Verification:** Python 1870 passed, 2 skipped, 37 subtests; frontend 244/244 (27 files); evidence 16 cases; exports 50/50. Overall literal verification FAIL only on other-owner port 17877. [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp16-file-url-long/docs/verify/wp16/VERIFY-RESULT.md).

**Measurements:** Five 30-minute cases each 15 windows and 31 IDs/3 reference voices; WER 10.3915–10.7937% /4725 words. Silence 32 fabricated words -> 0 with no decoder call; huge upload refused 507 before body.

**Unmeasured / remaining:** Natural long-meeting diversity; video-bearing MP4. Identity fragmentation subsequently repaired WP19; truncation notice WP18.

**Files (relative to source worktree):**

- Product: `frontend/src/lib/fileUpload.ts`, `moss_transcribe_diarize/app/phase2.py`, `moss_transcribe_diarize/app/phase2_file.py`. Generated frontend assets also changed.
- Tests/oracles: `frontend/src/lib/fileUpload.test.ts`, `tests/phase2/test_file_digital_silence.py`, `tests/phase2/test_file_mp3_artifact.py`, `tests/phase2/test_multi_file_url_browser.py`.
- Evidence/docs/bench/tooling: `.gitignore`, `docs/verify/wp16/VERIFY-RESULT.md`, `docs/verify/wp16/VERIFY.md`, `evidence/mvpfix/wp16/`, `prototypes/streaming-diarization/wp16-file-url-long/`. Exact leaf paths in source-index.

### WP17 — Are quiet-mic additions a merge defect, and why is enrolled recognition missing?

**Verdict:** fixed observation lifetime/reference; measured quality failure. **Tip:** `371af1bedf0796b1b9a43e40654cb249aeee95ab`; branch `mvpfix/wp17-lane-quality-voiceprint`; base `41cfebb9`.

**Commits:** `7870eb2c` fix: retain causal lane observations through voiceprint publication; `685319f4` test: include source sentence tail in microphone lane reference; `12b9e163` docs: retain WP17 lane differential and recognition verification evidence; `371af1be` docs: verify WP17 independently and correct verification layout.

**Verification:** Initial Python 1868 pass/1 layout fail/2 skip; relocated docs then 1869 passed/2 skipped, 37 subtests. Frontend 242/242 (27 files). [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp17-lane-quality-voiceprint/docs/verify/wp17/VERIFY-RESULT.md).

**Measurements:** Recognition 4/4 API routes 3.526378542–3.528290542 s. Mic 10/48 additions -> corrected 5/53 (9.43396%); 400000/400000 source PCM samples equal. Quality 0/2 full cases pass; 8/8 saved lane comparisons equal, 628 words.

**Unmeasured / remaining:** Browser recognition latency; actual AEC mic; acoustic truth of remaining five additions; general accuracy.

**Files (relative to source worktree):**

- Product: `moss_transcribe_diarize/app/live_coordinator.py`.
- Tests/oracles: `tests/e2e/fixtures/lane-microphone-reference.json`, `tests/e2e/verify_demo_lanes.py`, `tests/phase2/test_demo_lane_measurement.py`, `tests/test_live_lane_decode.py`.
- Evidence/docs/bench/tooling: `docs/adr/0009-private-account-voiceprint-bank.md`, `docs/verify/wp17/VERIFY-RESULT.md`, `docs/verify/wp17/VERIFY.md`, `evidence/mvpfix/wp17/`, `prototypes/streaming-diarization/wp17/`. Exact leaf paths in source-index.

### WP18 — Does simply enabling file embedding repair recurring speaker splits?

**Verdict:** falsified wiring-only repair; fixed truncation notice. **Tip:** `57fa5e7b81cb9777b396ee15c0689c9bf8b1da4b`; branch `mvpfix/wp18-file-identity`; base `d769b010`.

**Commits:** `82ab6d27` fix(file): retain reported truncation and record WP18 identity falsifier; `cfc69b7e` docs(wp18): specify fresh-context verification and unresolved identity boundary; `57fa5e7b` docs(wp18): record fresh verification failure and reproduced identity falsifier.

**Verification:** Python 1873 passed, 1 failed (lease setup), 2 skipped, 37 subtests; frontend 244/244 (27 files). [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp18-file-identity/docs/verify/wp18/VERIFY-RESULT.md).

**Measurements:** Six-minute old/new wiring both 7 IDs; perfect-vector one/two voices yield 3/6 IDs. Competing same-voice exemplars give margin zero. Truncated MP3 warning now becomes fixed safe notice.

**Unmeasured / remaining:** Identity remedy at this pin (later WP19); no blanket proof all damaged media is detected.

**Files (relative to source worktree):**

- Product: `moss_transcribe_diarize/app/phase2_audio.py`, `moss_transcribe_diarize/app/phase2_file.py`.
- Tests/oracles: `tests/phase2/test_file_digital_silence.py`, `tests/phase2/test_file_failure_reasons.py`, `tests/phase2/test_file_mp3_artifact.py`, `tests/phase2/test_file_truncation_notice.py`.
- Evidence/docs/bench/tooling: `.gitignore`, `docs/design-streaming-diarization.md`, `docs/verify/wp18/VERIFY-RESULT.md`, `docs/verify/wp18/VERIFY.md`, `evidence/mvpfix/wp18/`, `prototypes/streaming-diarization/wp18-file-identity/`. Exact leaf paths in source-index.

### WP19 — Can one canonical album per file speaker repair repeated-window identity?

**Verdict:** fixed; accepted and merged. **Tip:** `164603966230b452575f31d8ff0db88943c82efd`; branch `mvpfix/wp19-file-identity-album`; base `c2e45867`.

**Commits:** `ad7575ae` test: make owner-bound helper lease expiration deterministic; `448a4cf3` feat: resolve file-window speakers with the live identity album; `30418b2e` docs: specify fresh-context WP19 acceptance verification; `16460396` docs(wp19): record fresh-context acceptance and lease proof.

**Verification:** Python 1889 passed, 2 skipped, 37 subtests; frontend 249/249 (28 files); lease 20/20 independent runs. [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp19-file-identity-album/docs/verify/wp19/VERIFY-RESULT.md).

**Measurements:** Same inputs: 6 min 7->3 IDs; 30 min 31->3. 84/92 and 420/464 segments correct; overlap seconds 322.11/338.04 and 1592.97/1684.98; zero abstentions. Resolver 62.894428 s/3 windows and 332.007926 s/15; fresh six-minute replay 62.804387 s.

**Unmeasured / remaining:** Cross-corpus identity; final-candidate file throughput. Save/reopen/enroll/export controls use real archives with fake vectors, not attended accuracy.

**Files (relative to source worktree):**

- Product: `moss_transcribe_diarize/app/file_identity_album.py`, `moss_transcribe_diarize/app/phase2.py`, `moss_transcribe_diarize/app/phase2_speaker_identity.py`, `moss_transcribe_diarize/app/phase2_web_cli.py`, `moss_transcribe_diarize/app/runner_composition.py`.
- Tests/oracles: `frontend/src/components/fileAlbumExports.test.ts`, `tests/phase2/test_file_album_acceptance.py`, `tests/phase2/test_owner_bound_live_meeting.py`, `tests/phase2/test_runner_composition.py`, `tests/test_file_identity_album.py`.
- Evidence/docs/bench/tooling: `.gitignore`, `docs/design-streaming-diarization.md`, `docs/verify/wp19/VERIFY-RESULT.md`, `docs/verify/wp19/VERIFY.md`, `evidence/mvpfix/wp19/`, `prototypes/streaming-diarization/wp19-file-identity-album/`. Exact leaf paths in source-index.

### WP20 — Does mixed endpointing cause the observed overlap word errors?

**Verdict:** falsified endpointing remedy; measured quality failure. **Tip:** `717daaa8f010647a99b04132e0053338bb6f8ede`; branch `mvpfix/wp20-lane-endpointing`; base `de35ef36`.

**Commits:** `8b46938a` Measure WP20 lane endpointing and reject unsupported overlap fix; `717daaa8` docs(wp20): record fresh offline verification and rejected endpointing hypothesis.

**Verification:** Python 1874 passed, 2 skipped, 37 subtests; frontend 244/244 (27 files). [Source result](/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp20-lane-endpointing/docs/verify/wp20/VERIFY-RESULT.md).

**Measurements:** Full-reference boundaries identical: system 12/12, mic 10/10. Overlap immediate 24/106 and 6/53; final 13/106 and 5/53. 0/2 complete quality cases pass. 179 actual windows replayed: canonical 137/137, rolling 30/30, terminal 11/12 exact.

**Unmeasured / remaining:** No new endpoint scheduler/fix; snapshot timing and decoder padding variability remain. Different 48 s inputs have boundary differences, not proven improvements.

**Files (relative to source worktree):**

- Product: none.
- Tests/oracles: none.
- Evidence/docs/bench/tooling: `docs/design-streaming-diarization.md`, `docs/verify/wp20/VERIFY-RESULT.md`, `docs/verify/wp20/VERIFY.md`, `evidence/mvpfix/wp20/`, `prototypes/streaming-diarization/wp20/`. Exact leaf paths in source-index.

### WP21 — Can one command produce a truthful isolated local qualification bundle?

**Verdict:** blocked/in progress; partial dry run measured. **Tip:** `33112b07c20b9389391c0a2c9683307cd4dd70ab`; branch `mvpfix/wp21-qualify-bundle`; base `c2e45867`.

**Commits:** `33112b07` feat(wp21): add isolated local qualification bundle and explicit bench gaps.

**Verification:** No VERIFY-RESULT at snapshot. Dry-run summary only: Python 1877 passed, 2 skipped, 37 subtests (1879 collected); frontend 244/244. No fresh result exists at this snapshot; branch/brief and partial records are the sources.

**Measurements:** Retained source `evidence/qualify/33112b07c20b-20260918T063331479663Z/summary.md` (copied into WP23 evidence as `wp21-partial-summary.md`): 33112b07 dry run 214.292 s, runner FAIL KeyboardInterrupt; 0 decoder requests/peak 0; 17/17 asset parity. No real-workflow acceptance. Required interface gaps UNRUNNABLE per README; --long not measured.

**Unmeasured / remaining:** Fresh determinism run and final integrated execution. Not merged; do not treat partial static success as qualification.

**Files (relative to source worktree):**

- Product: none.
- Tests/oracles: none.
- Evidence/docs/bench/tooling: `.gitignore`, `evidence/mvpfix/wp21/`, `scripts/mvpfix-qualify.sh`, `tools/qualify/NOTES.md`, `tools/qualify/README.md`, `tools/qualify/decoder.py`, `tools/qualify/pytest_counts.py`, `tools/qualify/run.py`, `tools/qualify/test_bundle.py`. Exact leaf paths in source-index.

### WP22 — What retains memory, and does a real 30-minute capture finish durably?

**Verdict:** blocked/pending at snapshot. **Tip:** `8938cb2cd7d4a03e52f7c59f3f680a5cf3a5a999`; branch `mvpfix/wp22-memory-longrun`; base `8938cb2c`.

**Commits:** none since branch creation.

**Verification:** No committed WP22 changes and no WP22 VERIFY-RESULT; counts unavailable. No fresh result exists at this snapshot; branch/brief and partial records are the sources.

**Measurements:** Branch at 8938cb2c, before WP19; brief requires GPU-free profile first and lead-confirmed WP12 integration before real 1800 s run. WP15 is the measured baseline, not WP22 results.

**Unmeasured / remaining:** Object-growth attribution, bounded fix, 5/15/30-minute profile, post-Stop release and real 1800-second acceptance.

**Files (relative to source worktree):**

- Product: none.
- Tests/oracles: none.
- Evidence/docs/bench/tooling: none committed. Exact leaf paths in source-index.

## Current integrated milestones — WP34 refresh

The historical rows above remain observations at their original pins, not present
merge claims. **WP12, WP21, WP22 and WP31 are now merged. WP8 remains unmerged.**
WP23 imported WP8's documents without merging its branch. First-parent history
continues after order 17 (`c609d7f3`) as follows; full messages are retained in
[WP34 integration history](../../evidence/mvpfix/wp34/integration-history.txt).

| Order | Merge | Package |
|---:|---|---|
| 18 | `0ce5122d` | WP23 |
| 19 | `1745b96f` | WP12 accepted mapping |
| 20 | `625dbaa9` | WP21 qualification bundle |
| 21 | `d3ca29dc` | WP24 visual/copy pack |
| 22 | `d49fc50a` | WP26 unmatched terminal fallback |
| 23 | `f5fff0b2` | WP27 early Share |
| 24 | `9e58205b` | WP22 memory/30-minute run |
| 25 | `ea89af0c` | WP28 file resolver performance |
| 26 | `d8fa767f` | WP29 tape exhaustion |
| 27 | `0e97c71b` | WP32 independent cross-review |
| 28 | `a625d1a1` | WP31 data durability |

The lead's WP34 brief reports the integrated full-suite progression **1,865 → 1,901
→ 1,910 → 1,919 → 1,920 → 1,941 passed**. **Attribution limit:** these counts are
not present in the retained first-parent merge/build commit messages, so no invented
count-to-merge mapping is supplied. This sequence is brief-reported history, not six
independently verified commit-message results. Committed reports independently record
WP23's integrated-base 1901 and WP32's integrated-base 1941, with their scopes below.
WP34's own full-suite result is recorded in its row; branch counts are not interchangeable.

**Earlier-row updates:** WP12 accepted `f47f0dc9`: Stop 3.788534/7.490138/16.964282 s
at 24/60/180 s; branch focused 28 passed, full 1809 passed/2 skipped/37 subtests,
frontend 230 passed (see current `docs/verify/wp12/VERIFY-RESULT.md`; fresh-shell,
not `/new`, explicitly recorded). WP26 later recovers its two unmatched Lex turns.
WP21 `46f72fd6`: fresh status comparison 35/35 unchanged, **qualification FAIL**;
1877 Python passed/2 skipped/37 subtests, frontend 244, helpers 7; 300 requests;
workspace 10 pass/3 fail/1 skip of 14. WP25 continues the missing bench integration.
WP22 `3d498020`: fresh 1911 Python passed/2 skipped/37 subtests, frontend 249;
real 1800 s capture saved 6269 words and 1800 s MP3, Stop 101.697916 s under
contention. RSS near 5/15/30 min 932.4375/981/973.25 MiB, post-final 1148.953125 MiB.
WP29 fixes exhausted-tape reporting; residual memory ownership remains unknown.
Sources: `docs/verify/wp12/`, `wp21/`, `wp22/`, `wp26/`, `wp29/`.

### Lead's integrated ladder — source `1745b96f`

[Retained JSON](../../evidence/mvpfix/wp34/integrated-ladder-1745b96f.json), copied
from the brief's external `lane-level-ladder-integrated-1745b96f.json`: **8 cases,
n=1 each**, shared GPU with sibling work, isolated 57.6 MB per-tape manifest.

| Input | Words | Speakers | System unique witness | Mic unique witness |
|---|---:|---:|---|---|
| System only | 86 | 1 | 37/37 | 0/32 |
| Mic only, unity | 56 | 1 | 0/37 | 32/32 |
| Mic only, .03 (−30.5 dB) | 60 | 1 | 0/37 | 32/32 |
| Overlap, unity | 142 | 2 | 37/37 | 32/32 |
| Overlap, mic .316 (−10 dB) | 142 | 2 | 37/37 | 32/32 |
| Overlap, mic .1 (−20 dB) | 146 | 2 | 37/37 | 32/32 |
| Overlap, mic .03 (−30.5 dB) | 146 | 2 | 37/37 | 32/32 |
| Overlap, system quiet .316 | 142 | 2 | 37/37 | 32/32 |

All **5/5 overlap cases** retain both unique-token witnesses; each speaker has
zero opposite-source unique hits. These vocabulary witnesses do not measure ordered
word error rate, acoustic echo, same-lane overlap, Stop latency or final-head capacity.
The last case's name identifies system attenuation; the source's `mic_gain_db` field
still says −10.0, so its lane label is not silently reinterpreted as a mic measurement.

## Work-package rows WP23–WP34

For every row below, changed files mean creation-base → pinned tip (all leaves in
source-index); generated assets are identified separately from source. Source results
are `docs/verify/wp<N>/VERIFY-RESULT.md` at that row's tip unless marked absent.

### WP23 — Can the closure ledger preserve evidence and acceptance boundaries?

**Verdict:** documentation verified; merged. **Tip:** `50ea910e7d38bdb709aa7cb216b72ca8a2f5b867`; branch `mvpfix/wp23-closure-docs`; base `c609d7f3e03091becda8aa8588655447a51ea434`. **As of:** 2026-09-18T09:04:52.867295+00:00.

**Commits:** `ff8bcb79` docs(wp23): refresh closure ledger, contract and attended handoff; `50ea910e` docs(wp23): record fresh ten-row closure verification.

**Verification:** Fresh spot-check **10/10 rows, 5/5 numerical claims**, 0 corrections. Preparation only: **1901 Python passed, 2 skipped, 37 subtests; 249 frontend / 28 files**. No fresh suite rerun. [Pinned source result](../../evidence/mvpfix/wp34/sources/wp23-VERIFY-RESULT.md).

**Measurements:** 22 package rows, 31 issue states (16 open/15 closed), 34 local links/0 missing. Six deliverables. No product measurement.

**Unmeasured / remaining:** Final candidate speech/capacity, attended/provider/host acceptance; historical in-flight states superseded above.

**Files (product / tests / evidence):**

- Product: none.
- Tests/oracles: none.
- Evidence/docs/bench: `docs/handoffs/attended-session-plan.md`, `docs/handoffs/e2e-smoke-for-operator.md`, `docs/handoffs/mvpfix-campaign-20260918.md`, `docs/handoffs/pr32-description-draft.md`, `docs/known-limitations-20260918.md`, `docs/production-contract-20260917.md`; `evidence/mvpfix/wp23/`, `docs/verify/wp23/` where present; **17 changed files**; exact leaves in source-index.

### WP24 — Do UI states render truthfully at supported widths?

**Verdict:** scoped presentation repairs verified; merged; owner sign-off pending. **Tip:** `550911b15357341ddcf0332e6a4214aa37f3204d`; branch `mvpfix/wp24-visual-copy-pack`; base `0ce5122de781630b7ec0c933a6ba5d9cfba95236`. **As of:** 2026-09-18T09:04:52.867295+00:00.

**Commits:** `205dc611` fix(ui): correct sign-off copy, contrast, and outcome clipping; `8d3a2850` docs(wp24): retain 52-state visual sign-off pack and regeneration bench; `550911b1` verify(wp24): record fresh sign-off pack and full-suite results.

**Verification:** **1908 Python passed, 2 skipped, 37 subtests; 250 frontend / 28 files**; typecheck/build pass. Layout failure corrected; assets unchanged in fresh verification. [Pinned source result](../../evidence/mvpfix/wp34/sources/wp24-VERIFY-RESULT.md).

**Measurements:** 52 states × 3 viewports = **156 PNG/copy pairs**; 0 measured overflow/name/contrast/header-panel failures; contrast **8009 pass/616 manual/0 fail**; focus 3/3; 7 fresh decoder calls. Five presentation defects repaired.

**Unmeasured / remaining:** Owner judgment, physical/native capture, D3 shared-mode copy. Early-Share F4 repaired by WP27; pre-session ended-track gap remains WP32 F2.

**Files (product / tests / evidence):**

- Product: `frontend/src/components/TranscriptPane.tsx`, `frontend/src/styles/index.css`; generated frontend assets also changed.
- Tests/oracles: `frontend/src/components/TranscriptPane.test.tsx`, `frontend/src/components/speakerRename.test.tsx`, `tests/phase2/test_wp24_copy_accessibility.py`.
- Evidence/docs/bench: `prototypes/ui-signoff-pack/`; `evidence/mvpfix/wp24/`, `docs/verify/wp24/` where present; **428 changed files**; exact leaves in source-index.

### WP25 — Can the local qualification bundle execute all required benches truthfully?

**Verdict:** measured failures; in flight. **Tip:** `1dd59f66e4a9d1a24db44cf53cb961223d59755c`; branch `mvpfix/wp25-qualify-run`; base `625dbaa97b55fb5be66e06db9bfe4d8c985fd935`. **As of:** 2026-09-18T09:04:52.867295+00:00.

**Commits:** `ab474451` Make WP25 qualification gates runnable with isolated runtime arguments; `1dd59f66` Record WP25 long qualification failures and fresh-context verification recipe.

**Verification:** **No committed VERIFY-RESULT** at pin. Long-run suite: **1910 Python passed, 2 skipped, 37 subtests; 249 frontend; 9 helpers**. Working-tree fresh report still says run in progress; no completed fresh suite verdict claimed. [Pinned source result](../../evidence/mvpfix/wp34/sources/wp25-VERIFY-RESULT.md).

**Measurements:** Committed long bundle: workspace **12 pass/1 fail/1 skip of 14**; demo lanes **0/2**; lifecycle 7/7; reshare 6/6; identity 3/3; ladder 6 finalized measurements; browser **13 pass/1 fail/2 unrunnable of 16**; file 6-min 1/1, failures 5/5, 30-min 3/3; capacity **0/4**. **1879 requests**, peak 2, 3724.259 s. Long workspace alternation system final **11/106=10.37736%**; standalone **9/106=8.49057%**; mic immediate **11/53=20.75472%**. Fresh partial checks retain the latter 8.49% and mic failure.

**Unmeasured / remaining:** Clean 4×600 rerun/final-head acceptance pending; contended timeouts occurred before terminal start, four voiced system lanes with silent mic frames, not eight voiced lanes. Hidden capture and summary key remain absent. Working-tree capacity adjudication is provisional, captured separately.

**Files (product / tests / evidence):**

- Product: none.
- Tests/oracles: `tools/qualify/test_bundle.py`.
- Evidence/docs/bench: `prototypes/browser-stress/`, `prototypes/capacity-campaign/`, `prototypes/identity-stress/`, `prototypes/streaming-diarization/`, `tools/qualify/`; `evidence/mvpfix/wp25/`, `docs/verify/wp25/` where present; **67 changed files**; exact leaves in source-index.

### WP26 — Can unmatched terminal partitions recover identity without guessing?

**Verdict:** production fallback fixed and replay verified; merged. **Tip:** `648be68463df14ebeb17c8f66d3e063a24866a1e`; branch `mvpfix/wp26-unassigned-terminal`; base `625dbaa97b55fb5be66e06db9bfe4d8c985fd935`. **As of:** 2026-09-18T09:04:52.867295+00:00.

**Commits:** `dfb9b261` fix: probe terminal lane segments left unmapped by overlap; `648be684` docs(wp26): record fresh verification and reference attribution.

**Verification:** **1912 Python passed, 2 skipped, 37 subtests; 249 frontend / 28 files**; typecheck/build pass; **0/60 decoder requests**. Literal /new event not independently attested in source result. [Pinned source result](../../evidence/mvpfix/wp34/sources/wp26-VERIFY-RESULT.md).

**Measurements:** Real encoder replay recovers **2/2 segments, 16 words, 4.86 s**; **54/54 existing assignments unchanged, 56/56 word/time/lane rows preserved**. Two probes 0.750903 s total. Survey 49 sessions/18 stores; accepted WP12 1/3 sessions affected (2/127 segments), WP17 0/27.

**Unmeasured / remaining:** Native original-vector/live Stop replay and arbitrary-meeting prevalence unmeasured. P5 still open: same-lane historical −10 dB witnesses retain only 1/41 or 0/54 quiet-source unique tokens; not WER.

**Files (product / tests / evidence):**

- Product: `moss_transcribe_diarize/app/live_lane_decode.py`.
- Tests/oracles: `tests/test_live_lane_decode.py`.
- Evidence/docs/bench: `docs/design-streaming-diarization.md`, `prototypes/streaming-diarization/`; `evidence/mvpfix/wp26/`, `docs/verify/wp26/` where present; **43 changed files**; exact leaves in source-index.

### WP27 — Can early Share and late setup completions retain errors and recover cleanly?

**Verdict:** capture ordering fixed; merged; one pre-existing recovery gap remains. **Tip:** `379eac08d967348145046c1221c631f885454b19`; branch `mvpfix/wp27-early-share`; base `d3ca29dcfb79da24d05da9a4599fd0b50e7e25df`. **As of:** 2026-09-18T09:04:52.867295+00:00.

**Commits:** `7f4051a8` fix(capture): retain early-share errors through microphone setup; `379eac08` test(wp27): verify early-share ordering and repair success fixtures.

**Verification:** Initial **1916 passed/1 failed/2 skipped/37 subtests** (verification layout); corrected **1917 passed/2 skipped/37 subtests; 264 frontend / 28 files**, typecheck/build pass. Fixture control **2 failed/21 passed**, corrected 23/23; restored panel control **13 failed/1 passed of 14**. [Pinned source result](../../evidence/mvpfix/wp34/sources/wp27-VERIFY-RESULT.md).

**Measurements:** 41 fresh traces: **15/15 errors offer Reset/zero meters; 11/11 completed cleanups idle; 2/2 true mic successes retain Share explanation**. Early Share invokes zero chooser calls.

**Unmeasured / remaining:** Physical devices/native picker unmeasured; ended-track before session can still leave configuring/no Reset (WP32 F2, WP33 in flight).

**Files (product / tests / evidence):**

- Product: `frontend/src/components/ControlPanel.tsx`; generated frontend assets also changed.
- Tests/oracles: `frontend/src/components/ControlPanel.captureFailure.test.tsx`.
- Evidence/docs/bench: `docs/design-capture-setup.md`; `evidence/mvpfix/wp27/`, `docs/verify/wp27/` where present; **29 changed files**; exact leaves in source-index.

### WP28 — Can interval embeddings run concurrently without changing ordered identity decisions?

**Verdict:** file resolver optimization verified; merged. **Tip:** `ef2b15506e6d9773142e1c7acc4830c0b1457a72`; branch `mvpfix/wp28-file-resolver-perf`; base `d49fc50a99ec71867ddee8642f1e9b1f87e9a87e`. **As of:** 2026-09-18T09:04:52.867295+00:00.

**Commits:** `418258c6` perf(file): parallelize interval embeddings without changing album decisions; `263c4bc5` docs(wp28): prescribe actual fresh-context verification; `ef2b1550` docs(wp28): record fresh-context verification and timing evidence.

**Verification:** **1929 Python passed, 2 skipped, 37 subtests; 250 frontend / 28 files**. WP28 real fixtures **2/2 ran**, not skipped. No fresh failure/retry. [Pinned source result](../../evidence/mvpfix/wp34/sources/wp28-VERIFY-RESULT.md).

**Measurements:** Fresh 3-window serial/production **61.135778/17.894112 s**; 15-window **320.838881/93.031965 s** (**3.449×**, 71.00% less wall time). Full result equality **2/2 serial and 2/2 production against baseline**. Same 107/575 probes; live remains serial. Four-worker process high-water RSS 1,416,167,424 bytes.

**Unmeasured / remaining:** Other hosts/corpora, simultaneous files and end-to-end decode throughput unmeasured; output equality does not improve WP19 attribution accuracy.

**Files (product / tests / evidence):**

- Product: `moss_transcribe_diarize/app/file_identity_album.py`, `moss_transcribe_diarize/app/live_provider_bundle.py`, `moss_transcribe_diarize/app/speaker_identity.py`.
- Tests/oracles: `tests/test_file_resolver_performance.py`, `tests/test_live_provider_bundle.py`.
- Evidence/docs/bench: `docs/design-streaming-diarization.md`, `prototypes/streaming-diarization/`; `evidence/mvpfix/wp28/`, `docs/verify/wp28/` where present; **51 changed files**; exact leaves in source-index.

### WP29 — Can exhausted retained audio preserve committed words with truthful outcomes?

**Verdict:** exhaustion reporting/persistence fixed; merged; residual memory unknown. **Tip:** `1c615121802b142766e3af71eac3d4570d85bdc7`; branch `mvpfix/wp29-tape-exhaustion`; base `f5fff0b2d2faed729180984b69ded6be396cf614`. **As of:** 2026-09-18T09:04:52.867295+00:00.

**Commits:** `1497e6a9` fix(live): preserve truthful finalization when lane tapes exhaust; `9ac68d11` test(wp29): retain exhaustion and repeated-session RSS evidence; `1c615121` docs(wp29): record fresh-context verification results.

**Verification:** **1932 Python passed, 2 skipped, 37 subtests; 265 frontend / 28 files**; typecheck/build pass; retained audit **9/9 exhaustion and 2/2 RSS sessions**. Zero fresh failures. [Pinned source result](../../evidence/mvpfix/wp34/sources/wp29-VERIFY-RESULT.md).

**Measurements:** Five generic failed refinements become unavailable; 2 single-lane gaps report one each; mixed-only leaves lane refinement final; departure stays interrupted. **9/9 saved/live/reopen agree**, 60 s partial MP3 for 90 s capture, 7 notices. Repeated stub 600 s sessions post-final RSS **595.3125→621 MiB**, **+25.6875 MiB** for the second session, identical measured Python owner estimates.

**Unmeasured / remaining:** Native allocation owner and later-session growth unknown; two sessions do not establish a per-session law or plateau. HTTP/SQLite/MP3 excluded from RSS bench. WP32 F1 mic-only truncation diagnostic remains open.

**Files (product / tests / evidence):**

- Product: `moss_transcribe_diarize/app/live_lane_decode.py`, `moss_transcribe_diarize/app/phase2.py`, `moss_transcribe_diarize/app/phase2_live.py`.
- Tests/oracles: `frontend/src/components/MeetingHistory.test.tsx`, `tests/phase2/test_tape_exhaustion.py`, `tests/test_live_lane_decode.py`.
- Evidence/docs/bench: `docs/adr/0003-live-session-audio-retention.md`, `prototypes/streaming-diarization/`; `evidence/mvpfix/wp29/`, `docs/verify/wp29/` where present; **49 changed files**; exact leaves in source-index.

### WP30 — Do repeated sessions release owners, and does overload preserve fair accounting?

**Verdict:** measurement preparation; in flight. **Tip:** `e5185fa26399e140b9f7930f08fc8e6b18085af6`; branch `mvpfix/wp30-overload-semantics`; base `9e58205b9a9b825ade3eeae73866b6c1880ceda4`. **As of:** 2026-09-18T09:04:52.867295+00:00.

**Commits:** `e5185fa2` bench: measure repeated two-lane sessions with timed decoder stubs.

**Verification:** **No committed VERIFY-RESULT or full-suite count** at pin. [Pinned source result](../../evidence/mvpfix/wp34/sources/wp30-VERIFY-RESULT.md).

**Measurements:** Committed **1×10 s timed-stub smoke**: final/completed, 40 acknowledged frames, 160000 accepted/accounted samples, saved words equal, 12 stub calls, tapes empty; lane albums/sweep ledgers remain reachable. One bench commit, no production fix.

**Unmeasured / remaining:** Six-session accumulation, four/eight-session overload, real-ASR capacity and native ownership not established by smoke. No synthetic WER claim.

**Files (product / tests / evidence):**

- Product: none.
- Tests/oracles: none.
- Evidence/docs/bench: `prototypes/capacity-campaign/`; `evidence/mvpfix/wp30/`, `docs/verify/wp30/` where present; **15 changed files**; exact leaves in source-index.

### WP31 — Do upgrade, restore, restart and rollback preserve saved data?

**Verdict:** local durability verified; accepted and merged; full rollback fidelity falsified. **Tip:** `33a91c8b0baf5d43bc698ae81bd9f69ce80ba75a`; branch `mvpfix/wp31-data-durability`; base `ea89af0cfa8a69f3df08cdb061036eac5e009cd4`. **As of:** 2026-09-18T09:04:52.867295+00:00.

**Commits:** `778068d8` test: measure real-store durability and document upgrade boundaries; `40ac0f13` docs: finalize fresh durability verification handoff; `33a91c8b` test(wp31): verify durability and fix verification document layout.

**Verification:** Initial **1944 passed/1 failed/4 skipped/37 subtests** (verification layout); corrected **1945 Python passed/4 skipped/37 subtests; 264 frontend / 28 files**. Retained verifier exit 0; fresh decoder requests **0/60**. [Pinned source result](../../evidence/mvpfix/wp34/sources/wp31-VERIFY-RESULT.md).

**Measurements:** **13 stores/60 meetings**, 47 old transcripts preserved, 13 new meetings, 60 referenced audio; original 235/235 exports. Schema refusals 4/4; idle restores 13/13. Base reader **8/8 reads, 0/8 lane rendering, 32/40 exports**; integrated 8/8 lanes/40/40 exports. DB-only active copy lost 1 committed row; SQLite online backup retained it.

**Unmeasured / remaining:** Rollback is a reduced-capability reader; base writes to lane meetings unmeasured. Nonempty voiceprint banks, host reboot/cold cache and atomic live DB+audio backup unmeasured. No product-source repair demonstrated.

**Files (product / tests / evidence):**

- Product: none.
- Tests/oracles: `tests/phase2/test_data_durability.py`.
- Evidence/docs/bench: `docs/data-durability-upgrades.md`, `prototypes/data-durability/`; `evidence/mvpfix/wp31/`, `docs/verify/wp31/` where present; **39 changed files**; exact leaves in source-index.

### WP32 — Do integrated repairs preserve contracts and truthful evidence?

**Verdict:** cross-review verified; merged; F1–F5 require disposition. **Tip:** `94e19b1fa3b258a27551ff1e63077270f4b3d86f`; branch `mvpfix/wp32-final-crossreview`; base `d8fa767f3ccbb577584643d7e23f80f55d92b2f5`. **As of:** 2026-09-18T09:04:52.867295+00:00.

**Commits:** `2df225bb` audit(wp32): review integrated invariants and retain adversarial witnesses; `94e19b1f` verify(wp32): complete fresh ten-row check and full suites.

**Verification:** **10/10 audit statements, 0 discrepancies; 1941 Python passed, 4 skipped, 37 subtests; 265 frontend / 28 files**; focused 108 passed/2 skipped; ended-track 1 passed/23 filtered; typecheck pass. [Pinned source result](../../evidence/mvpfix/wp34/sources/wp32-VERIFY-RESULT.md).

**Measurements:** Product audit **6 scoped PASS/3 QUALIFIED/1 FAIL**. F1 truncation flags **2/3 correct, 3/3 final**; F2 configuring/no Reset witness; F3 legacy exports **4/5 byte equal**, JSON 497→523 bytes; F4 required summary SKIP may exit 0; F5 **3 valid/2 invalid** historical mutation controls.

**Unmeasured / remaining:** WP33 fixes in flight, none accepted at snapshot. Real-encoder parallel parity/native hangs, universal legacy parity, provider and physical acceptance unmeasured.

**Files (product / tests / evidence):**

- Product: none.
- Tests/oracles: none.
- Evidence/docs/bench: `docs/audits/mvpfix-final-crossreview-20260918.md`; `evidence/mvpfix/wp32/`, `docs/verify/wp32/` where present; **41 changed files**; exact leaves in source-index.

### WP33 — Can WP32 F1–F5 be repaired without policy changes?

**Verdict:** in flight; zero commits beyond creation base. **Tip:** `0e97c71b503435b76e47c158daa0c7554a85a89f`; branch `mvpfix/wp33-crossreview-fixes`; base `0e97c71b503435b76e47c158daa0c7554a85a89f`. **As of:** 2026-09-18T09:04:52.867295+00:00.

**Commits:** none.

**Verification:** **No committed VERIFY-RESULT or WP33 suite count** at pin; inherited WP32 result is not WP33 verification. [Pinned source result](../../evidence/mvpfix/wp34/sources/wp33-VERIFY-RESULT.md).

**Measurements:** Brief requires OR of per-lane truncation, pre-session ended-track recovery, legacy JSON **497 bytes/5 formats** restored, required SKIP→INCOMPLETE, qualification/repair of two invalid terminal mutation controls. These are targets, not achieved results.

**Unmeasured / remaining:** All five findings remain open on the integrated pin. Uncommitted sibling work not incorporated or certified.

**Files (product / tests / evidence):**

- Product: none.
- Tests/oracles: none.
- Evidence/docs/bench: **0 changed files**; exact leaves in source-index.

### WP34 — Can final-state documents distinguish integrated repairs from incomplete acceptance?

**Verdict:** documentation refresh prepared; fresh-context spot-check pending.
**Branch:** `mvpfix/wp34-ledger-refresh`; base `a625d1a17d103fd522fb734335aa691aa09085f7`.
The containing documentation commit identifies this row; final evidence commit will
be reported in `docs/verify/wp34/VERIFY-RESULT.md` and the pane (no self-referential SHA).

**Verification:** preparation **1945 Python passed, 5 skipped, 37 subtests**
(169.04 s); **265 frontend tests / 28 files** (2.62 s). Logs under
`evidence/mvpfix/wp34/`; fresh **10-row**
spot-check prescribed in `docs/verify/wp34/VERIFY.md`. No fresh verification claimed yet.

**Measurements:** source census **11/11 branch tips**, **8/11 committed results**,
**3/11 absent** (WP25/WP30/WP33); **12 new rows** including this one, **34 total**.
WP33 ancestor-with-zero-work falsifies a naive merged predicate. Lead ladder **8 cases**.
Missing merge-message counts remain brief-reported; no invented provenance.

**Unmeasured / remaining:** no new live/provider/host/attended qualification. Snapshot
may advance after its timestamp. WP25 partial working-tree records are explicitly provisional.

**Files (product / tests / evidence):** product/tests none; campaign ledger,
`docs/known-limitations-20260918.md`, `docs/handoffs/pr32-description-draft.md`,
`docs/production-contract-20260917.md`, `docs/handoffs/attended-session-plan.md`,
`docs/verify/wp34/`, `evidence/mvpfix/wp34/`. Own scratch is uncommitted and removed.
