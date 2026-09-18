# Local qualification

Candidate `1dd59f66e4a9d1a24db44cf53cb961223d59755c`; clean at start: False.
Local measurement only; no deployment or attended-capture acceptance.

| Gate | Status | Counts | Seconds |
|---|---|---|---|
| tree_clean | FAIL | {"expected":1,"executed":1,"passed":0,"failed":1,"skipped":0,"unrunnable":0} | 0 |
| python_import | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0 |
| asset_parity | PASS | {"expected":17,"compared":17,"different":0} | 0.817 |
| pytest | PASS | {"collected":1912,"executed":1910,"passed":1910,"failed":0,"skipped":2,"errors":0,"deselected":0,"failure_names":[],"subtests":37,"reported":1912,"exit_code":0} | 154.926 |
| frontend | PASS | {"collected":249,"executed":249,"passed":249,"failed":0,"skipped":0,"failure_names":[]} | 3.542 |
| bundle_helpers | PASS | {"collected":9,"executed":9,"passed":9,"failed":0,"skipped":0,"errors":0,"deselected":0,"failure_names":[],"subtests":0,"reported":9,"exit_code":0} | 1.74 |
| typecheck | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 1.381 |
| verify_layout | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.044 |
| stack | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 5.496 |
| workspace | FAIL | {"expected":14,"executed":13,"passed":11,"failed":2,"skipped":1,"unrunnable":0} | 255.908 |
| workspace_row_1 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.11 |
| workspace_row_2 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 3.248 |
| workspace_row_3 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 2.17 |
| workspace_row_4 | FAIL | {"expected":1,"executed":1,"passed":0,"failed":1,"skipped":0,"unrunnable":0} | 108.554 |
| workspace_row_5 | FAIL | {"expected":1,"executed":1,"passed":0,"failed":1,"skipped":0,"unrunnable":0} | 0.06 |
| workspace_row_6 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.404 |
| workspace_row_7 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.165 |
| workspace_row_8 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 38.529 |
| workspace_row_9 | SKIP | {"expected":1,"executed":0,"passed":0,"failed":0,"skipped":1,"unrunnable":0} | 0.003 |
| workspace_row_10 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 5.344 |
| workspace_row_11 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.081 |
| workspace_row_12 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.196 |
| workspace_row_13 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 57.221 |
| workspace_row_14 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 38.071 |
| demo_lanes | FAIL | {"expected":2,"executed":2,"passed":0,"failed":2,"skipped":0,"unrunnable":0} | 87.323 |
| lifecycle | PASS | {"expected":7,"executed":7,"passed":7,"failed":0,"skipped":0,"unrunnable":0} | 11.225 |
| reshare | PASS | {"expected":6,"executed":6,"passed":6,"failed":0,"skipped":0,"unrunnable":0} | 35.008 |
| identity_stress | PASS | {"expected":3,"executed":3,"passed":3,"failed":0,"skipped":0,"unrunnable":0} | 194.906 |
| level_ladder | PASS | {"expected":6,"executed":6,"passed":6,"failed":0,"skipped":0,"unrunnable":0} | 161.787 |
| browser_stress_all | FAIL | {"expected":16,"executed":14,"passed":13,"failed":1,"skipped":0,"unrunnable":2} | 757.265 |
| file_30min | SKIP | {"expected":3,"executed":0,"passed":0,"failed":0,"skipped":3,"unrunnable":0} | 0 |
| file_6min | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 78.524 |
| file_failures | PASS | {"expected":5,"executed":5,"passed":5,"failed":0,"skipped":0,"unrunnable":0} | 43.43 |
| capacity_4x600 | SKIP | {"expected":4,"executed":0,"passed":0,"failed":0,"skipped":4,"unrunnable":0} | 0 |
| teardown | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0 |

stack: SQLite runtime pin bypassed by existing local recipe; not deployment parity
workspace_row_9: no_configured_relay_models
identity_stress: One saved identity per reference voice, distinct across voices, zero within-voice switches/unresolved segments; unused births reported separately
level_ladder: PASS means six finalized measurements; retention has no supplied acceptance threshold. Unique vocabulary is not transcript accuracy.
browser_stress_all: Native hidden-tab cases are UNRUNNABLE if Chromium never becomes hidden; missing rows mean bench could not execute
file_30min: Requires --long
file_6min: Existing WP16 bars: durable outcome, five exact exports for speech, audio download, foreign read 404; failures typed and visible after reload
file_failures: Existing WP16 bars: durable outcome, five exact exports for speech, audio download, foreign read 404; failures typed and visible after reload
capacity_4x600: Requires --long

Runtime: 1807.553 s.
Decoder: {"requests": 724, "peak_in_flight": 2, "rejected_by_budget": 0, "active_at_teardown": 0, "budget_exhausted": false, "shared_metrics": "sampled every 2 seconds; not own request attribution"}
Raw content-bearing stdout stays in ignored runtime scratch. Retained logs contain only status/count projections.
