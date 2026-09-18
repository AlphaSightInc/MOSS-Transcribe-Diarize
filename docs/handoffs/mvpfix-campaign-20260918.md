# MVP fix campaign ledger — 2026-09-18

**Integrated code fixes are substantial; whole-product acceptance remains incomplete.**
This ledger freezes integration at `c609d7f3e03091becda8aa8588655447a51ea434`
(WP19 accepted and merged). It separates a source fix, its branch tests, a measured
workflow, and release acceptance. None implies the next. No deployment, attended G7,
physical echo, visual sign-off, final-SHA capacity or live summary success is claimed.

## Population and custody

Exactly **WP1–WP22 (22 rows)**. Local branch/source snapshot captured by WP23 on
2026-09-18; moving branches may later advance. Each row pins its branch tip and
branch-creation base; commits and changed files are computed over that range, not
all inherited integration history. Full paths and commit subjects are in
[`source-index.json`](../../evidence/mvpfix/wp23/source-index.json). Source worktrees
are read-only. `VERIFY-RESULT.md` counts below are copied with their original scope;
focused, full, repeated and historical results are never summed. Skipped corpora
and separate subtests are not passed test items. No new speech/provider run by WP23.

Verdicts: **fixed** = scoped repair backed by evidence; **falsified** = proposed
mechanism rejected; **measured** = observations, including failures; **blocked** =
acceptance/progress requires missing evidence/authority. A row may contain more than one.

## Actual integration order and recorded suite counts

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

## Work-package rows

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
