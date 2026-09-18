# Local qualification

Candidate `ab4744511b415455551761ad116db0801370561d`; clean at start: True.
Local measurement only; no deployment or attended-capture acceptance.

| Gate | Status | Counts | Seconds |
|---|---|---|---|
| tree_clean | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0 |
| python_import | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0 |
| asset_parity | PASS | {"expected":17,"compared":17,"different":0} | 0.789 |
| pytest | PASS | {"collected":1912,"executed":1910,"passed":1910,"failed":0,"skipped":2,"errors":0,"deselected":0,"failure_names":[],"subtests":37,"reported":1912,"exit_code":0} | 160.574 |
| frontend | PASS | {"collected":249,"executed":249,"passed":249,"failed":0,"skipped":0,"failure_names":[]} | 3.187 |
| bundle_helpers | PASS | {"collected":9,"executed":9,"passed":9,"failed":0,"skipped":0,"errors":0,"deselected":0,"failure_names":[],"subtests":0,"reported":9,"exit_code":0} | 1.28 |
| typecheck | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 1.253 |
| verify_layout | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.048 |
| stack | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 5.481 |
| workspace | FAIL | {"expected":14,"executed":13,"passed":12,"failed":1,"skipped":1,"unrunnable":0} | 255.414 |
| workspace_row_1 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.178 |
| workspace_row_2 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 3.242 |
| workspace_row_3 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 2.169 |
| workspace_row_4 | FAIL | {"expected":1,"executed":1,"passed":0,"failed":1,"skipped":0,"unrunnable":0} | 108.518 |
| workspace_row_5 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.061 |
| workspace_row_6 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.408 |
| workspace_row_7 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.163 |
| workspace_row_8 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 38.826 |
| workspace_row_9 | SKIP | {"expected":1,"executed":0,"passed":0,"failed":0,"skipped":1,"unrunnable":0} | 0.003 |
| workspace_row_10 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 5.11 |
| workspace_row_11 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.087 |
| workspace_row_12 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.194 |
| workspace_row_13 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 57.092 |
| workspace_row_14 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 37.795 |
| demo_lanes | FAIL | {"expected":2,"executed":2,"passed":0,"failed":2,"skipped":0,"unrunnable":0} | 87.286 |
| lifecycle | PASS | {"expected":7,"executed":7,"passed":7,"failed":0,"skipped":0,"unrunnable":0} | 11.253 |
| reshare | PASS | {"expected":6,"executed":6,"passed":6,"failed":0,"skipped":0,"unrunnable":0} | 34.958 |
| identity_stress | PASS | {"expected":3,"executed":3,"passed":3,"failed":0,"skipped":0,"unrunnable":0} | 194.452 |
| level_ladder | PASS | {"expected":6,"executed":6,"passed":6,"failed":0,"skipped":0,"unrunnable":0} | 170.859 |
| browser_stress_all | FAIL | {"expected":16,"executed":14,"passed":13,"failed":1,"skipped":0,"unrunnable":2} | 694.833 |
| file_6min | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 80.936 |
| file_failures | PASS | {"expected":5,"executed":5,"passed":5,"failed":0,"skipped":0,"unrunnable":0} | 44.093 |
| file_30min | PASS | {"expected":3,"executed":3,"passed":3,"failed":0,"skipped":0,"unrunnable":0} | 1223.493 |
| capacity_4x600 | FAIL | {"expected":4,"executed":4,"passed":0,"failed":4,"skipped":0,"unrunnable":0} | 699.552 |
| teardown | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0 |

stack: SQLite runtime pin bypassed by existing local recipe; not deployment parity
workspace_row_9: no_configured_relay_models
identity_stress: One saved identity per reference voice, distinct across voices, zero within-voice switches/unresolved segments; unused births reported separately
level_ladder: PASS means six finalized measurements; retention has no supplied acceptance threshold. Unique vocabulary is not transcript accuracy.
browser_stress_all: Native hidden-tab cases are UNRUNNABLE if Chromium never becomes hidden; missing rows mean bench could not execute
file_6min: Existing WP16 bars: durable outcome, five exact exports for speech, audio download, foreign read 404; failures typed and visible after reload
file_failures: Existing WP16 bars: durable outcome, five exact exports for speech, audio download, foreign read 404; failures typed and visible after reload
file_30min: Existing WP16 bars: durable outcome, five exact exports for speech, audio download, foreign read 404; failures typed and visible after reload
capacity_4x600: Existing capacity clean bar includes no detected foreign load; contention is recorded without pausing

Runtime: 3724.259 s.
Decoder: {"requests": 1879, "peak_in_flight": 2, "rejected_by_budget": 0, "active_at_teardown": 0, "budget_exhausted": false, "shared_metrics": "sampled every 2 seconds; not own request attribution"}
Raw content-bearing stdout stays in ignored runtime scratch. Retained logs contain only status/count projections.
