# Local qualification

Candidate `799169736bca4e25768610facffed44a4bb30eef`; clean at start: True.
Local measurement only; no deployment or attended-capture acceptance.

| Gate | Status | Counts | Seconds |
|---|---|---|---|
| tree_clean | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0 |
| python_import | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0 |
| asset_parity | PASS | {"expected":17,"compared":17,"different":0} | 0.976 |
| pytest | PASS | {"collected":1879,"executed":1877,"passed":1877,"failed":0,"skipped":2,"errors":0,"deselected":0,"failure_names":[],"subtests":37,"reported":1879,"exit_code":0} | 152.756 |
| frontend | PASS | {"collected":244,"executed":244,"passed":244,"failed":0,"skipped":0,"failure_names":[]} | 3.533 |
| bundle_helpers | PASS | {"collected":7,"executed":7,"passed":7,"failed":0,"skipped":0,"errors":0,"deselected":0,"failure_names":[],"subtests":0,"reported":7,"exit_code":0} | 1.794 |
| typecheck | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 1.351 |
| verify_layout | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.048 |
| stack | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 6.555 |
| workspace | FAIL | {"expected":14,"executed":13,"passed":10,"failed":3,"skipped":1,"unrunnable":0} | 296.107 |
| workspace_row_1 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.108 |
| workspace_row_2 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 3.264 |
| workspace_row_3 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 2.168 |
| workspace_row_4 | FAIL | {"expected":1,"executed":1,"passed":0,"failed":1,"skipped":0,"unrunnable":0} | 132.06 |
| workspace_row_5 | FAIL | {"expected":1,"executed":1,"passed":0,"failed":1,"skipped":0,"unrunnable":0} | 0.076 |
| workspace_row_6 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.423 |
| workspace_row_7 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.171 |
| workspace_row_8 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 38.488 |
| workspace_row_9 | SKIP | {"expected":1,"executed":0,"passed":0,"failed":0,"skipped":1,"unrunnable":0} | 0.003 |
| workspace_row_10 | FAIL | {"expected":1,"executed":1,"passed":0,"failed":1,"skipped":0,"unrunnable":0} | 5.475 |
| workspace_row_11 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.091 |
| workspace_row_12 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.179 |
| workspace_row_13 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 68.202 |
| workspace_row_14 | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 43.642 |
| demo_lanes | FAIL | {"expected":2,"executed":2,"passed":0,"failed":2,"skipped":0,"unrunnable":0} | 104.659 |
| lifecycle | PASS | {"expected":7,"executed":7,"passed":7,"failed":0,"skipped":0,"unrunnable":0} | 12.093 |
| reshare | PASS | {"expected":6,"executed":6,"passed":6,"failed":0,"skipped":0,"unrunnable":0} | 37.854 |
| identity_stress | FAIL | {"expected":3,"executed":3,"passed":1,"failed":2,"skipped":0,"unrunnable":0} | 80.415 |
| level_ladder | FAIL | {"expected":6,"executed":0,"passed":0,"failed":0,"skipped":0,"unrunnable":6} | 3.152 |
| browser_stress_all | UNRUNNABLE | {"expected":16,"executed":0,"passed":0,"failed":0,"skipped":0,"unrunnable":16} | 0 |
| file_6min | UNRUNNABLE | {"expected":1,"executed":0,"passed":0,"failed":0,"skipped":0,"unrunnable":1} | 0 |
| file_failures | UNRUNNABLE | {"expected":5,"executed":0,"passed":0,"failed":0,"skipped":0,"unrunnable":5} | 0 |
| file_30min | SKIP | {"expected":3,"executed":0,"passed":0,"failed":0,"skipped":3,"unrunnable":0} | 0 |
| capacity_4x600 | SKIP | {"expected":4,"executed":0,"passed":0,"failed":0,"skipped":4,"unrunnable":0} | 0 |
| teardown | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0 |

stack: SQLite runtime pin bypassed by existing local recipe; not deployment parity
workspace_row_9: no_configured_relay_models
identity_stress: One saved identity per reference voice, distinct across voices, zero within-voice switches/unresolved segments; unused births reported separately
level_ladder: PASS means six finalized measurements; retention has no supplied acceptance threshold. Unique vocabulary is not transcript accuracy.
browser_stress_all: run.py all includes case 14 restart with fixed WP5 paths/port and stack.py tunnel 18105; no restart/decoder arguments
file_6min: WP16 probe fixes app at 17876, metrics at 18116, output under WP16; no base/metrics/output arguments
file_failures: WP16 failure cases share fixed 18116 metrics and fixed source ports; no isolation arguments
file_30min: Default bounded run; --long requests this gate
capacity_4x600: Default bounded run; --long requests this gate

Runtime: 701.799 s.
Decoder: {"requests": 300, "peak_in_flight": 1, "rejected_by_budget": 0, "active_at_teardown": 0, "budget_exhausted": true, "shared_metrics": "sampled every 2 seconds; not own request attribution"}
Raw content-bearing stdout stays in ignored runtime scratch. Retained logs contain only status/count projections.
