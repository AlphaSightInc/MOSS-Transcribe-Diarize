# WP25 fresh-context verification — 2026-09-18

**Qualification FAIL. Fresh status-reproduction verification FAIL.** The complete 900-budget short bundle finished (exit 1, BUNDLE and teardown emitted). Two unexpected gate-status deltas: tree_clean and workspace_row_5. All other comparable statuses reproduced. This is not exact-SHA or numerical determinism. No gate was cut by the budget.

## Identity and scope

Fresh session began in `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp25-qualify-run`, branch `mvpfix/wp25-qualify-run`, HEAD `1dd59f66e4a9d1a24db44cf53cb961223d59755c`, clean. Candidate `625dbaa97b55fb5be66e06db9bfe4d8c985fd935`; measured harness `ab4744511b415455551761ad116db0801370561d`. `git diff --exit-code ab4744511b41 HEAD -- scripts tools/qualify prototypes` passed. The prescribed Python import resolved to this worktree's `moss_transcribe_diarize/__init__.py`.

Read VERIFY.md, COMMON.md, execution-plan sections 1–2, local AGENTS.md, and required prototype skill. Existing prototype verdict retained: parameter isolation supported by 4/4 dependency witnesses, 2/2 real 60-second mono inputs, HTTP budget control 200/200/429. No new algorithm, production code, benchmark predicate, threshold, or policy.

## Commands and authorization change

Initial user cap 400 superseded VERIFY.md's 2000:

```sh
bash scripts/mvpfix-qualify.sh --budget 400 --compare evidence/mvpfix/wp25/ab4744511b41-20260918T073411045029Z/summary.json --out evidence/mvpfix/wp25/fresh
```

While static pytest was running, user raised the short-run cap to 900. Sent SIGTERM to owned runner PID 29154; its finally block stopped owned pytest and emitted teardown PASS and BUNDLE. No decoder request occurred. Retained interrupted attempt `fresh/1dd59f66e4a9-20260918T084323167672Z`; runner FAIL/remaining gates UNRUNNABLE indicate interruption, not product observations. This was a user-directed budget restart, not a retry to chase a result.

```sh
bash scripts/mvpfix-qualify.sh --budget 900 --compare evidence/mvpfix/wp25/ab4744511b41-20260918T073411045029Z/summary.json --out evidence/mvpfix/wp25/fresh
```

The completed-run target is `fresh/1dd59f66e4a9-20260918T084357230876Z`. Both commands omit `--long`. Console remains ignored in `.wp25runtime/fresh-console.raw` and `.wp25runtime/fresh-400-interrupted-console.raw`.

Deviation: interrupted evidence was retained uncommitted before restart; therefore the second start's `tree_clean` gate truthfully fails on only `?? evidence/mvpfix/wp25/fresh/`. It should have been committed before restart. Do not call the new run clean-start or exact-SHA determinism; do not suppress this delta. Source was unchanged. No further live rerun.

## F3 — capacity timeout adjudication from retained long-run data

The 90-second limit is the campaign's wall-clock limit from immediately before POST Stop through the Stop response and subsequent polling. POST uses `deadline:30`; production continues draining after its 30-second caller wait. The campaign checks elapsed >90 after each observation, then raises `finalization_timeout_90s` and aborts. It does not wait 90 seconds after a terminal decode starts. Poll overhead can exceed 90; exact timeout timestamps were not retained.

| Session | Stop monotonic seconds | Stop→final | Last timed event after Stop | Rolling admitted/completed | Terminal starts |
|---|---:|---|---:|---:|---:|
| 1 | 105022.749654500 | unmeasured; no final by >90 s | 84.063235 s | 30/29 | 0 |
| 2 | 105022.753155833 | unmeasured; no final by >90 s | 89.445280 s | 31/30 | 0 |
| 3 | 105022.759615875 | unmeasured; no final by >90 s | 87.708519 s | 5/4 | 0 |
| 4 | 105022.753058625 | unmeasured; no final by >90 s | 85.880724 s | 22/21 | 0 |

All four retained streams have finalization `not_started`, zero terminal events and zero session-closed events. Canonical/rolling work is serial across sessions via the single canonical pump. Stop waits for both before creating a terminal plan. Thus **zero terminal requests in the observed campaign**, inferred from the event-before-dispatch code contract and absent terminal-start events; request logs do not independently tag terminal/lane. There were 64 decoder starts after the first Stop, 1107 total, peak one in capacity. Those post-Stop calls must not be called terminal calls. Each session still had one unmatched admitted rolling window at its final observation.

Terminal architecture itself is one thread per session, then up to two lane jobs per session, bounded by the owned two-request proxy. It is not a serialized four-sessions-times-two-lanes terminal path. That path was never reached here. The observed failure is drain not finishing before the campaign limit; no exact counterfactual terminal latency or performance cause is established.

Microphone frames were `bytes(fb)` with `silent=True` throughout. Canonical and rolling lane decoders skip zero PCM. The terminal decoder also has a zero-lane skip, but was never reached. This campaign therefore provides four voiced system lanes, not eight voiced lanes. Each session accepted/accounted 9,600,000 timeline samples and acknowledged 2400 lane frames; zero mic content does not remove frame accounting.

Source: `prototypes/capacity-campaign/run.py:331,367–437`; `moss_transcribe_diarize/app/live_service_runtime.py:464,900–996,1471–1490,1533–1605`; `moss_transcribe_diarize/app/live_lane_decode.py:35,204–214,252–255,310–315`. Safe numeric/event-count projection: `evidence/mvpfix/wp25/fresh/capacity-adjudication.json`. Original long capacity FAIL 0/4 remains unchanged. Saved-final WER, final lag, and complete pre-stop real-time factor remain unmeasured.

## F1 — live quality, unchanged bars

WER (word error rate) = substitutions + omissions + additions divided by reference words. System denominator 106; microphone 53. Immediate bar <=0.166655; final and reopened <=0.095074. Lower is better. Mic amplitude gain remains 0.03, not 0.316.

| Run / invocation / case | Immediate system / mic | Final = reopened system / mic |
|---|---|---|
| Long / workspace_row_4 / alternation | 0.150943 / 0.207547 | 0.103774 / 0.094340 |
| Long / workspace_row_4 / overlap | 0.216981 / 0.113208 | 0.122642 / 0.094340 |
| Long / demo_lanes / alternation | 0.150943 / 0.207547 | 0.084906 / 0.094340 |
| Long / demo_lanes / overlap | 0.216981 / 0.113208 | 0.122642 / 0.094340 |
| Fresh / workspace_row_4 / alternation | 0.141509 / 0.207547 | 0.084906 / 0.094340 |
| Fresh / workspace_row_4 / overlap | 0.216981 / 0.113208 | 0.122642 / 0.094340 |
| Fresh / demo_lanes / alternation | 0.150943 / 0.207547 | 0.084906 / 0.094340 |
| Fresh / demo_lanes / overlap | 0.216981 / 0.113208 | 0.122642 / 0.094340 |

Fresh first text 3.330545s <=4s (long 3.328802s); row-4 base-session Stop→terminal 2.050827s. Every lane case reaches final. All attribution, duplication, and unresolved-word counts are zero. Failure remains ordered word accuracy: alternation mic immediate and overlap system immediate/final. Long workspace alternation system final also failed; fresh improves to passing, without changing the aggregate gate. Do not claim numeric determinism or infer decoder causation.

## F2 — browser predicate mismatch

Fresh case 9 repeats the long case: 1/3 URL variants pass the unchanged keyword predicate, although all three show specific failure reasons and durable `failed` status. Unreachable: “URL media could not be acquired.” (predicate false). HTTP 404: “The media was not found (404).” (true). HTML: “The URL returned a web page instead of direct media.” (false). The predicate in `prototypes/browser-stress/run.py:258` searches only `unsupported`, `error:`, `unreachable`, `404`, `connection refused`, `resolve`, `not accepted:`. It therefore rejects two truthful product messages. This is a harness predicate mismatch; the qualification remains FAIL without editing the case. Safe projection: `fresh/browser-predicate-adjudication.json`.


## F7 — new row-5 failure and verification verdict

Expected long row5 PASS; fresh FAIL. Predicate requires both rename HTTP responses=200, the new name present and old stripped button text absent from visible utterance/legend labels, saved history updated for each rename, and correct final export. Measured: HTTP2/2=200; visible-label conjunction1/2; history2/2; final export1/1 (without reload). The second rename's `rows_legend_updated=false` is the only false operand. The individual new-label-present/old-label-absent operands were not retained, including in private row-05.json; root cause is unknown. Do not call this a demonstrated timing race or silently reclassify it. No rerun.

`determinism.deltas` truthfully lists tree_clean PASS→FAIL and workspace_row_5 PASS→FAIL. Workspace aggregate remains FAIL but changes from12/14 passed,F1,S1 to11/14 passed,F2,S1. The earlier progress statement12/1/1 was mistaken and corrected after full reconciliation. Source/harness unchanged; metadata-only HEAD difference makes `same_candidate=false`. Verification of unchanged statuses fails even though the bundle executed completely. No acceptance or deployment authorization follows.

## F8 — final accounting and limits

Fresh1807.553s,724/900 dispatched requests,peak2,rejected0,active0,budget not exhausted. Initial shared running/waiting0/0. Contention812/812 valid samples,errors0,max shared running2/waiting0,shared>own1 sample; non-atomic readings do not establish foreign attribution. No sibling-load pause. Long3724.259s,1879/2000,peak2,rejected0,active0;1753/1753 valid,errors0,max2/1,excess68. Interrupted attempt22.929s,0 decoder calls,teardownPASS;4PASS/1runnerFAIL/31UNRUNNABLE, with unobserved static populations left unknown. Its38 files alone account for the900-run dirty-start record.

Python1910/1912 passed,2 skipped,37 subtests; frontend249/249; helpers9/9; assets17/17; typecheck/layoutPASS. Fresh six-minute file76.398788s to completion (gate78.524s),945 reference words,998 observed,28 substitutions+10 omissions+63 additions=101 errors,WER0.106878307;3 speakers;5/5 exact exports. Typed failures5/5: empty.wav/text.mp3 transcode_failed; missing acquisition_http_404; HTML acquisition_failed; hang acquisition_timeout. No new failed detail was hidden by projection.

Ladder6/6 final and reproduces lead/long at all6 points: four overlap points37/37 system+32/32 mic; alone37/37+0/32 and0/37+32/32. Unique vocabulary is not ordered WER. Identity3/3 passes. Browser13PASS/1FAIL/2UNRUNNABLE; cases3/15 remain native-visibility unavailable; case16's25/35s variants pass. Row9 no_configured_relay_models,configured_models0; a key alone is insufficient. Long-only file30min SKIP0/3 and capacity SKIP0/4 here preserve original longPASS3/3 andFAIL0/4.

After BUNDLE, lsof found no LISTEN sockets on18125,19125,17825–17829. Runner teardown reports no owned process groups; no owned leak found. Source difference check against ab4744511b41 passed. Only fresh evidence and verification/report docs changed. No push,merge,deployment,GitHub,shared restart,ports7861/7862,benchmark edits,decoder tuning,or policy changes. Audio,transcripts,cookies,keys,screenshots,raw logs remain ignored. Existing local SQLite pin bypass remains a limit; this is local measurement, not deployment or attended qualification.

## Full gate comparison

F=failed,S=skipped,U=unrunnable. Pass numerator is not executed numerator; Python's1912 includes2 skips. Parent/child rows overlap and must not be summed as independent tests.

| Gate | Long: pass/denominator; seconds | Fresh: pass/denominator; seconds |
|---|---|---|
| tree_clean | PASS 1/1; 0.000 | FAIL 0/1 F1; 0.000 |
| python_import | PASS 1/1; 0.000 | PASS 1/1; 0.000 |
| asset_parity | PASS 17/17; 0.789 | PASS 17/17; 0.817 |
| pytest | PASS 1910/1912 S2; 160.574 | PASS 1910/1912 S2; 154.926 |
| frontend | PASS 249/249; 3.187 | PASS 249/249; 3.542 |
| bundle_helpers | PASS 9/9; 1.280 | PASS 9/9; 1.740 |
| typecheck | PASS 1/1; 1.253 | PASS 1/1; 1.381 |
| verify_layout | PASS 1/1; 0.048 | PASS 1/1; 0.044 |
| stack | PASS 1/1; 5.481 | PASS 1/1; 5.496 |
| workspace | FAIL 12/14 F1 S1; 255.414 | FAIL 11/14 F2 S1; 255.908 |
| workspace_row_1 | PASS 1/1; 0.178 | PASS 1/1; 0.110 |
| workspace_row_2 | PASS 1/1; 3.242 | PASS 1/1; 3.248 |
| workspace_row_3 | PASS 1/1; 2.169 | PASS 1/1; 2.170 |
| workspace_row_4 | FAIL 0/1 F1; 108.518 | FAIL 0/1 F1; 108.554 |
| workspace_row_5 | PASS 1/1; 0.061 | FAIL 0/1 F1; 0.060 |
| workspace_row_6 | PASS 1/1; 0.408 | PASS 1/1; 0.404 |
| workspace_row_7 | PASS 1/1; 0.163 | PASS 1/1; 0.165 |
| workspace_row_8 | PASS 1/1; 38.826 | PASS 1/1; 38.529 |
| workspace_row_9 | SKIP 0/1 S1; 0.003 | SKIP 0/1 S1; 0.003 |
| workspace_row_10 | PASS 1/1; 5.110 | PASS 1/1; 5.344 |
| workspace_row_11 | PASS 1/1; 0.087 | PASS 1/1; 0.081 |
| workspace_row_12 | PASS 1/1; 0.194 | PASS 1/1; 0.196 |
| workspace_row_13 | PASS 1/1; 57.092 | PASS 1/1; 57.221 |
| workspace_row_14 | PASS 1/1; 37.795 | PASS 1/1; 38.071 |
| demo_lanes | FAIL 0/2 F2; 87.286 | FAIL 0/2 F2; 87.323 |
| lifecycle | PASS 7/7; 11.253 | PASS 7/7; 11.225 |
| reshare | PASS 6/6; 34.958 | PASS 6/6; 35.008 |
| identity_stress | PASS 3/3; 194.452 | PASS 3/3; 194.906 |
| level_ladder | PASS 6/6; 170.859 | PASS 6/6; 161.787 |
| browser_stress_all | FAIL 13/16 F1 U2; 694.833 | FAIL 13/16 F1 U2; 757.265 |
| file_6min | PASS 1/1; 80.936 | PASS 1/1; 78.524 |
| file_failures | PASS 5/5; 44.093 | PASS 5/5; 43.430 |
| file_30min | PASS 3/3; 1223.493 | SKIP 0/3 S3; 0.000 |
| capacity_4x600 | FAIL 0/4 F4; 699.552 | SKIP 0/4 S4; 0.000 |
| teardown | PASS 1/1; 0.000 | PASS 1/1; 0.000 |

## Completion

Required final checks: `bash scripts/check_verify_layout.sh` and `git diff --check`; outcomes recorded below before commit. Lead command from this worktree: `bash scripts/mvpfix-qualify.sh --long --budget 2000`. Final local commit SHA and post-commit clean status are in the pane report (avoids a self-referential SHA).

Final checks PASS: `bash scripts/check_verify_layout.sh` (verification documents not at repository root); `git diff --check`. `git diff --cached --check` also PASS; staged scope contains82 files, all in the authorized fresh evidence and two report documents. Seven-port listener check returned no listeners; no cleanup action required.
