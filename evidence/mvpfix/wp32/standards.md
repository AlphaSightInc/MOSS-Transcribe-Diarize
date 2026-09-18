# WP32 Standards axis — base 37979e53 → d8fa767f

## Check decisions
- Exact two-dot test diff + fixture history detects changed expectations or hidden skips; classify each deletion and report weakened gates separately from legitimate contract/fixture updates.
- Grep + blame + base comparison detects changed protected values/semantics; report each authorized semantic extension rather than claim unchanged behavior from unchanged constants.
- Read retained WP10/12/17/27 evidence detects whether fixture corrections erase reachable failures; reject unsupported efficacy claims.
- Smell heuristics guide inspection only: mysterious names, duplicated code, feature envy, data clumps, primitive obsession, repeated switches, shotgun surgery, divergent change, speculative generality, message chains, middle man, refused bequest. Report concrete harm only; no formatting/tooling findings.

Review artifacts below are source analysis, not new runtime/GPU measurements. No production mutation or full-suite execution by this axis.

## Verdict

No changed protected numeric policy value and no unjustified removal of an existing unit assertion found. There is one explicit **weakened E2E gate** (missing relay models become SKIP and process success); report it as unmeasured summary coverage. There are two new opt-in real-encoder skips, not deletions of existing tests. WP12 mutation evidence has one invalid failure mechanism affecting two terminal nodes and must not be represented as five valid assertion kills.

## Protected invariants (grep + blame)

Raw commands/results: `invariant-blame.txt`. Exact base→HEAD diff confirms wholly unchanged files for QUALITY_BOUNDS, album constants, helper lease coordinator, frame parser, and original two-Refresh test. Rows distinguish numeric preservation from intentionally changed behavior.

| Code | Invariant / source at HEAD | Verdict / required change |
|---|---|---|
| S-I1 | `phase2_acceptance.py:246` all eight QUALITY_BOUNDS (0.166655, 0.140442, 0.929636, 0.876970, 0.161430, 0.911512, 0.134804, 0.095074) | VERIFIED unchanged entire file; no change. |
| S-I2 | `app/live_provider_bundle.py:1376` match score/margin manifest readers; `app/live_identity.py:378,430,432` comparisons | VERIFIED numeric policy readers/comparisons unchanged. New lane factories reuse same config (`live_identity.py:90`, provider bundle `:1018`); permitted speakers are now lane-local. Retained measured values 0.35/0.1 at `evidence/mvpfix/wp12/identity-policy.json:2`; this file is historical measurement, not proof of a live service configuration. |
| S-I3 | `app/live_identity_album.py:45` admission 2.0 s / birth 1.0 s; provider bundle `:1064,1080` override readers | VERIFIED unchanged entire album module and unchanged reader logic. |
| S-I4 | `frontend/src/components/ControlPanel.tsx:69` both lane rms > 0 | VERIFIED unchanged readiness predicate. Added error guard prevents late meter restoring ready after failed setup. |
| S-I5 | `frontend/src/capture/captureClient.ts:174,354,780,1141` SILENCE_RMS=1e-4 | VERIFIED unchanged constant and comparisons. Backend exact-digital-zero guard is additive, deliberately distinct from readiness/browser silence threshold. |
| S-I6 | `app/live_helper_failure.py:150,161,421` positive caller-provided lease; `app/phase2_live.py` accepted Stop release | Lease duration unchanged; authority intentionally ends at accepted Stop (WP15). This is lifecycle behavior change, not a lease-threshold change. |
| S-I7 | `frontend/src/components/ControlPanel.tsx:249`; capture client `:601`; runtime `:900` | Stop UI deadline stays 5 s, transport grace unchanged. Server drain remains asynchronous; runtime deadline code unchanged. |
| S-I8 | `app/live_service_runtime.py:668,714-749` max_queue_depth | VERIFIED admission/arbiter bound unchanged; lane jobs are inside an admitted work item, so queue depth was never total model-request count. No new unbounded canonical queue. |
| S-I9 | `app/live_tape.py:270-310`; `app/live_coordinator.py:518-523` | Mixed-tape byte cap/refusal semantics preserved. Two source tapes each reuse same cap; aggregate tape storage can be 3× configured cap. This is explicit WP1 source preservation, not a global memory cap. WP29 adds truthful gaps and earlier tape release; no cap value changed. Do not claim aggregate storage unchanged. |
| S-I10 | `app/live_lane_contract.py:260-281` | VERIFIED nine required keys unchanged (lane, sequence, capture_timestamp_ns, device_epoch, silent, discontinuity, sample_rate, sample_count, pcm_base64). Optional capture_end_timestamp_ns already existed at base. Entire parser file unchanged. |
| S-I11 | `tests/phase2/test_acceptance_locator_sentinels.py:69` | VERIFIED original exact two-Refresh assertion unchanged. New `test_lane_consumer_geometry.py:40` repeats it across viewports. No hiding/removal to satisfy locators. |
| S-I12 | `frontend/src/styles/index.css:91-157` root reference tokens | VERIFIED all root token declarations unchanged. WP24 uses existing danger token for stop (previous live token), ink-2 on selected rows, responsive overflow limits; `tests/phase2/test_wp24_copy_accessibility.py:14,56` asserts contrast/geometry. Added lane badge fallback #696969 is local styling, not token mutation. |

## Every deletion-bearing test file

`test-deletion-diff.txt` preserves complete two-dot hunks for all **19** deletion-bearing test files. Added-only test files are outside assertion-removal population; additions of skip/xfail were scanned across all changed test files. There are **5 removed/replaced unit expectation statements**, all frontend, plus **4 replaced E2E failure predicates** in demo-lane verification and the workspace export/summary boolean gate changes below. Zero deleted Python `assert` or unittest assertion statements; zero added xfail.

| Code | File:HEAD line / removal | Classification and evidence |
|---|---|---|
| S-T1 | `frontend/src/components/ControlPanel.test.tsx:257,303` two old raw `helper_lease_expired` expectations | Legitimate copy-contract replacement, equally strict human-readable text. Production `ControlPanel.tsx:114`; Reset and terminal assertions remain. |
| S-T2 | `frontend/src/components/TranscriptPane.test.tsx:126,131,143` two disabled=true assertions become false; old active-page explanation changes | Intentional product contract extension, not hidden weakening: owner may name saved or observer-opened meetings. `CONTEXT.md:27`; backend owner tests `tests/phase2/test_saved_speaker_naming.py`. Provisional-only prohibition remains. |
| S-T3 | `frontend/src/components/speakerRename.test.tsx:19-40` parameterization/fixture | Coverage expands 2→6 active/completed live/file combinations, source lanes, summaries, enrollment unavailable. No assertion deleted. |
| S-T4 | `tests/e2e/stress_reshare.py:91` content-print deletion | Privacy correction only; every check retained. |
| S-T5 | `tests/e2e/verify_demo_lanes.py:60-145` removes final/count/mic-half/distinct-half predicates and old audio fixture schedule | Stronger independent reference-scored lane oracle for alternation AND overlap, pre-terminal/final/reopened, fixed QUALITY_BOUNDS. Final status still required at :143. Duration changes from arbitrary partial clips to complete reference intervals; original counts-only oracle was insufficient. |
| S-T6 | `tests/e2e/verify_summaries.py:14,48` model default | Different requested provider model (Flash Lite), no assertion removed; model availability remains explicitly skipped. Does not establish other models work. |
| S-T7 | `tests/e2e/verify_workspace.py:237,335,364,387,707,747` navigation, export predicates, summary failure | Navigation click removal fixes clipped desktop nav; capture actions still exercised. Exports replace nonempty/shape predicates with API-grounded words/labels/times/identity/lane comparison (`tests/e2e/export_oracle.py:61`), stronger. **Weakened gate:** no relay models now SKIP and exit 0, including all selected rows skipped. Count is honestly 0/1 PASS, 1 SKIP; never count this as summary acceptance. Required lead handling: acceptance aggregation must inspect SKIP counts; if CLI success itself is gate, restore non-success on unmeasured selected row. |
| S-T8 | deleted `tests/phase2/conftest.py`, moved to `tests/conftest.py:10-20` | Legitimate fixture registration move; explicit phase2 path condition preserves scope, SQLite runtime gate tests override it. No broader host-runtime waiver. |
| S-T9 | `tests/phase2/test_candidate_storage.py:151-160` script fixture checkout | Legitimate isolation correction: copies production scripts into fake checkout so fake home is outside protected tree. Same return-code/content and victim-survival assertions retained. |
| S-T10 | `tests/phase2/test_file_mp3_artifact.py:52,118` notices signature + zero→nonzero WAV | Legitimate new prepare_mix interface and digital-silence dispatch contract; full lifecycle/MP3 assertions retained. Silence has dedicated file test coverage. |
| S-T11 | `tests/phase2/test_owner_bound_live_meeting.py:161,368,640,2086` lane preparer forks, audible fixture, source_lane=None, deterministic lease callback | Legitimate fixture contracts; zero-frame tests intended decoded voice now supply minimum nonzero system sample. Timer now fires actual callback after accepted heartbeat, additionally asserts first timer cancelled. Existing expiry/fencing/reopen assertions retained. |
| S-T12 | `tests/phase2/test_runner_composition.py:147` zero→nonzero tape | Legitimate terminal request test; assertion stays HTTP request/prompt behavior, exact-zero refusal separately tested. |
| S-T13 | `tests/phase2/test_voiceprint_latency_measurement.py:19` fixture tab role/section | Legitimate reference DOM correction, no timing relaxation. |
| S-T14 | `tests/phase2/workspace_reachability_fixtures.py:57,132` independent lane identity + nonzero system PCM | Legitimate fixture interface/input corrections, no assertions removed. |
| S-T15 | `tests/test_live_pipeline_seams.py:638,680,695,714,815,861,1141,1270,1279,1283` 10 PCM call-site replacements | Legitimate zero→minimum-nonzero fixture change; same empty-cause/salvage/failure/token-cap assertions. WP10 moved guard to dispatch and dedicated tests cover silence; WP12 historical correction repeats input alignment, not weaker expected outputs. |
| S-T16 | `tests/test_live_provider_bundle.py:90-91` fake encoder signature | Adds interval_workers default and assertion ==1, strengthening live serial default protection. |
| S-T17 | `tests/test_live_rolling_wiring.py:439,449` two PCM replacements | Legitimate same hard-cap salvage vs rolling refusal test with audible input; original assertions retained. |
| S-T18 | `tests/test_live_service_replay.py:1285,1312` terminal replay nonzero PCM and helper parameter | Legitimate terminal fixture; default for pacing-only tests remains zero. All finalization/event/accounting assertions retained. |
| S-T19 | `tests/test_live_vad.py:296,332` two PCM replacements | Legitimate decoder-WAV/timing fixture; runner WAV dimensions and elapsed assertions retained. |

## Named fixture adjudications and skip inventory

| Code | Item | Verdict / limits |
|---|---|---|
| S-T20 | WP10 `tests/phase2/test_draft_lane.py:158` effective_transcript fixture | Legitimate: reader consumes published surface when present. Fixture now sets published surface consistent with committed entries; expected 1/2/0/0 retirement counts unchanged. Prototype candidates `prototypes/zero-guard-seams/NOTES.md:22` retain original failure and dispatch alternatives. Comment that empty effective surface is *never* possible is broader than necessary (later revisions can empty it); this fixture represents un-revised commits, where correction is valid. |
| S-T21 | WP12 `9d10e0d8`, retained `baseline-adjudication.json` and `fixture-mutations.txt` | 19 historical failures reproduced before correction; same assertions retained. **Evidence limit:** launcher mutation fails from `_refused(... gaps=)` missing keyword TypeError (`fixture-mutations.txt:116-120`); replay then fails final-vs-failed assertion because runtime catches the same TypeError (`:136-144`). These two nodes do not prove valid refusal-mutation efficacy. The other three nodes fail assertions as intended. Must not claim 5/5 valid assertion kills; no product defect inferred. |
| S-T22 | WP17 `tests/e2e/fixtures/lane-microphone-reference.json:3` | Legitimate reference correction backed by longer source reference and independent historical decode (`evidence/mvpfix/wp17/reference-adjudication.md:7`). Exactly five leading words restored; 48→53 reference, 58 observed unchanged, WER 20.8333%→9.43396%; five remaining additions still errors. This review read custody/provenance; did not re-listen to audio. |
| S-T23 | WP27 `379eac08`, `ControlPanel.captureFailure.test.tsx:201,233` | Legitimate successful descriptor supplies required preflight_status_lines. Adds positive proof microphone graph exists and nonzero context count, closing vacuous success. No removed expectation; old pending rejection/Reset regression coverage retained. |
| S-T24 | new `tests/test_file_resolver_performance.py:127-142` | 2 parameterized real-fixture tests skip absent WP28_REAL_FIXTURES; explicit root with missing WAVs fails. Additional tests, not replacement of existing assertions. Full-suite green without env does not establish real-encoder parity. |
| S-T25 | all changed tests/frontend tests | No new pytest skip decorators or xfail; only actual new pytest.skip is S-T24. E2E summary skip is S-T7; other textual 'skip' additions describe zero-audio dispatch. |

## Standards / design review

No harmful smell finding within this axis. Source-lane is a necessary primitive (one captured audio source, independent identity, overlap allowed); strings remain finite validated system/microphone rather than an open policy registry. New dispatch wrapper has measured purpose (seam outcome preservation), not speculative scaffolding. Identity value ownership stays in existing policy/album modules. Runtime and frontend feature changes compose existing lifecycle authorities. Repeated source-lane sorting and reader changes span consumers because that datum is represented there; absent concrete divergence they are not shotgun-surgery findings.

## Summary counts / limitations

12 protected invariant rows: 12 adjudicated, 0 numeric-policy/token/parser regressions; tape aggregate storage and Stop lease authority intentionally differ. 19 deletion-bearing files classified; 5 unit expectation replacements authorized; 4 replaced E2E demo failure predicates strengthened. 1 E2E gate weakened explicitly (missing-model SKIP→exit 0); 2 new opt-in fixture skips; 0 xfails. 4 requested WP fixture groups adjudicated. 1 historical mutation-efficacy limitation. No tests executed by this axis; root owns full suites. No production changes/commits/services/network/GPU.
