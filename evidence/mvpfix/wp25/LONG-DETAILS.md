# WP25 long-run evidence

Production candidate `625dbaa97b55fb5be66e06db9bfe4d8c985fd935`; harness `ab4744511b415455551761ad116db0801370561d`.
Clean at start. No production/frontend changes from integrated candidate. Command: `bash scripts/mvpfix-qualify.sh --long --budget 2000`.
Overall qualification FAIL; runnable-gate execution completed. This is local measurement, not deployed/attended qualification.

| Gate | Status | Pass/expected; failures/skips/unrunnable | Seconds |
|---|---|---|---|
| tree_clean | PASS | 1/1; F0 S0 U0 | 0.000 |
| python_import | PASS | 1/1; F0 S0 U0 | 0.000 |
| asset_parity | PASS | 17/17; F0 S0 U0 | 0.789 |
| pytest | PASS | 1910/1912; F0 S2 U0 | 160.574 |
| frontend | PASS | 249/249; F0 S0 U0 | 3.187 |
| bundle_helpers | PASS | 9/9; F0 S0 U0 | 1.280 |
| typecheck | PASS | 1/1; F0 S0 U0 | 1.253 |
| verify_layout | PASS | 1/1; F0 S0 U0 | 0.048 |
| stack | PASS | 1/1; F0 S0 U0 | 5.481 |
| workspace | FAIL | 12/14; F1 S1 U0 | 255.414 |
| workspace_row_1 | PASS | 1/1; F0 S0 U0 | 0.178 |
| workspace_row_2 | PASS | 1/1; F0 S0 U0 | 3.242 |
| workspace_row_3 | PASS | 1/1; F0 S0 U0 | 2.169 |
| workspace_row_4 | FAIL | 0/1; F1 S0 U0 | 108.518 |
| workspace_row_5 | PASS | 1/1; F0 S0 U0 | 0.061 |
| workspace_row_6 | PASS | 1/1; F0 S0 U0 | 0.408 |
| workspace_row_7 | PASS | 1/1; F0 S0 U0 | 0.163 |
| workspace_row_8 | PASS | 1/1; F0 S0 U0 | 38.826 |
| workspace_row_9 | SKIP | 0/1; F0 S1 U0 | 0.003 |
| workspace_row_10 | PASS | 1/1; F0 S0 U0 | 5.110 |
| workspace_row_11 | PASS | 1/1; F0 S0 U0 | 0.087 |
| workspace_row_12 | PASS | 1/1; F0 S0 U0 | 0.194 |
| workspace_row_13 | PASS | 1/1; F0 S0 U0 | 57.092 |
| workspace_row_14 | PASS | 1/1; F0 S0 U0 | 37.795 |
| demo_lanes | FAIL | 0/2; F2 S0 U0 | 87.286 |
| lifecycle | PASS | 7/7; F0 S0 U0 | 11.253 |
| reshare | PASS | 6/6; F0 S0 U0 | 34.958 |
| identity_stress | PASS | 3/3; F0 S0 U0 | 194.452 |
| level_ladder | PASS | 6/6; F0 S0 U0 | 170.859 |
| browser_stress_all | FAIL | 13/16; F1 S0 U2 | 694.833 |
| file_6min | PASS | 1/1; F0 S0 U0 | 80.936 |
| file_failures | PASS | 5/5; F0 S0 U0 | 44.093 |
| file_30min | PASS | 3/3; F0 S0 U0 | 1223.493 |
| capacity_4x600 | FAIL | 0/4; F4 S0 U0 | 699.552 |
| teardown | PASS | 1/1; F0 S0 U0 | 0.000 |

## F1 — live quality failures
Workspace parent fails because row 4 fails. Row 4 first text 3.328802s passes <=4s; both controlled lane cases fail WER. Immediate bar <=0.166655; final/reopened <=0.095074. Reference words: system106, mic53.

| Invocation/case | Immediate system/mic | Final system/mic |
|---|---|---|
| Workspace alternation | 0.150943 / 0.207547 | 0.103774 / 0.094340 |
| Workspace overlap | 0.216981 / 0.113208 | 0.122642 / 0.094340 |
| Demo alternation | 0.150943 / 0.207547 | 0.084906 / 0.094340 |
| Demo overlap | 0.216981 / 0.113208 | 0.122642 / 0.094340 |
Reopened equals final in every case; attribution, duplication and unresolved word counts are zero. Actual unchanged demo gain=0.03 (-30.46dB amplitude scaling), not the brief example’s -10dB. Decoder causation is not independently established here; no tuning.

## F2 — browser failure and unavailable observations
Cases1,2,4–8,10–14,16 PASS (13). Case9 FAIL (1): visible-reason keyword check passes1/3 URL variants; both failed variants actually display specific failure reasons and durable failed status.
Unreachable UI: “URL media could not be acquired.” HTML UI: “The URL returned a web page instead of direct media.” The unchanged old predicate recognizes neither phrase. The 404 variant passes. WP16 typed-failure gate independently passes5/5; no case logic was changed to hide this mismatch.
Cases3 and15 UNRUNNABLE (2): tab foreground change and native window minimization never yielded document.hidden=true. No hidden-tab performance claim. Case14 owned restart passes credential/history/transcript equality; case16 25/35s lease variants pass.

## F3 — capacity failure
All4 sessions accepted2400 lane frames and accepted/accounted9600000 samples each, but all4 exceeded the existing90s finalization timeout. All9600 foreign-owner probes returned expected refusal. Saved-final WER and final lag are unmeasured, not zero.
Fairness passes maximum dispatch skew1<=1, refinement queue depth1<=1, RSS growth756072448B<=4GiB, GPU cache maximum0.010707912<=0.95; no foreign load detected by the existing capacity monitor. Pre-stop inference accounting is incomplete (rolling admitted/completed); real-time factor bar<1 cannot be established. Capacity alone used1107 calls. See capacity-failure-details.json for exact machine codes and counters.

## F4 — other measurements and skip
Workspace row9 SKIP: no_configured_relay_models; configured_models=0. A recognized key existed in the environment, but that alone does not configure a relay. No summary-provider dispatch occurred.
Identity3/3: one distinct saved ID per reference voice, zero within-voice switches/unresolved segments. Alternating case records one boundary-straddling segment separately.
Ladder6/6 finalized. All four overlap points retain37/37 system+32/32 microphone unique vocabulary, reproducing lead1745b96f. Alone controls retain37/37+0/32 and0/37+32/32. Vocabulary retention is not ordered WER.
Six-minute file:78.441789s to completion;945 reference/998 observed words, WER0.106878307;3 speakers;5/5 exact exports. Failure cases5/5 match typed codes and visible durable reasons.
Long WAV/MP3/M4A complete in405.536643/403.360505/407.403662s;4994/4980/4989 words;3 speakers each;15/15 exact exports; last end1799.85s each. WER0.107724868/0.103915344/0.107724868 against4725 words each. Earlier WP16 WAV88.69s used a different candidate; cause of timing difference unmeasured.

## F5 — accounting, provenance and deviations
Full run3724.259s;1879/2000 calls;peak2;budget rejections0;active at teardown0. Contention1753/1753 valid samples,0 errors;max shared running2,waiting1;68 non-atomic samples show shared>own, which is not proof of foreign attribution. Capacity monitor detected no foreign load. All seven owned ports were closed after teardown.
Full Python1910 passed/2 skipped/1912 collected;37 subtests;159.43s pytest reported(160.574s process wall). Frontend249/249;helpers9/9;assets17/17 byte-identical;typecheck/layoutPASS. Preflight suite same counts,151.04s.
Prototype:4/4 runtime dependency witnesses,2/2 real 60s mono inputs; existing proxy control200,200,429. Supported parameter isolation; absorbed throwaway prototype. Batch JSON substituted for interactive TUI.
Failed attempts retained: preflight static wrapper used relative --out and raised only during final path display; fixed before long run. Preflight tree-clean FAIL precedes implementation commit. Auxiliary read-only status command once used system Python and failed dataclass(slots=True); mandated3.12 rerun succeeded. Initial prototypes/file* discovery glob had no match. No qualification run used the wrong interpreter.
Local-stack recipe retains its existing SQLite pin bypass. Raw content stays ignored; safe result projections are committed instead of raw stdout. Capacity failure-detail strings above are post-run projections of original private metadata because general sanitizer suppresses them. No live rerun or verdict revision used to obtain them.
No push/merge/deploy/GitHub/shared restart. Only owned worktree files changed; own18125 tunnel only. Product bars, identity policy, two-Refresh sentinel, readiness, nine-key frames and lifecycle logic unchanged.
Fresh-context verification is separately required; see docs/verify/wp25/VERIFY.md.
