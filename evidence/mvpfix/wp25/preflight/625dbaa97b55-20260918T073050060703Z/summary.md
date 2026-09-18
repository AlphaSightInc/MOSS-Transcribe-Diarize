# Local qualification

Candidate `625dbaa97b55fb5be66e06db9bfe4d8c985fd935`; clean at start: False.
Local measurement only; no deployment or attended-capture acceptance.

| Gate | Status | Counts | Seconds |
|---|---|---|---|
| tree_clean | FAIL | {"expected":1,"executed":1,"passed":0,"failed":1,"skipped":0,"unrunnable":0} | 0 |
| python_import | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0 |
| asset_parity | PASS | {"expected":17,"compared":17,"different":0} | 0.751 |
| pytest | PASS | {"collected":1912,"executed":1910,"passed":1910,"failed":0,"skipped":2,"errors":0,"deselected":0,"failure_names":[],"subtests":37,"reported":1912,"exit_code":0} | 152.229 |
| frontend | PASS | {"collected":249,"executed":249,"passed":249,"failed":0,"skipped":0,"failure_names":[]} | 3.049 |
| bundle_helpers | PASS | {"collected":9,"executed":9,"passed":9,"failed":0,"skipped":0,"errors":0,"deselected":0,"failure_names":[],"subtests":0,"reported":9,"exit_code":0} | 1.736 |
| typecheck | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 1.228 |
| verify_layout | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.045 |
| teardown | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0 |


Runtime: 159.217 s.
Decoder: {"requests": 0, "peak_in_flight": 0, "rejected_by_budget": 0, "active_at_teardown": 0, "budget_exhausted": false, "shared_metrics": "sampled every 2 seconds; not own request attribution"}
Raw content-bearing stdout stays in ignored runtime scratch. Retained logs contain only status/count projections.
