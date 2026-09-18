# Local qualification

Candidate `33112b07c20b9389391c0a2c9683307cd4dd70ab`; clean at start: True.
Local measurement only; no deployment or attended-capture acceptance.

| Gate | Status | Counts | Seconds |
|---|---|---|---|
| python_import | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0 |
| asset_parity | PASS | {"expected":17,"compared":17,"different":0} | 0.861 |
| pytest | PASS | {"collected":1879,"executed":1879,"passed":1877,"failed":0,"skipped":2,"errors":0,"deselected":0,"failure_names":[],"subtests":37,"exit_code":0} | 151.938 |
| frontend | PASS | {"collected":244,"executed":244,"passed":244,"failed":0,"skipped":0,"failure_names":[]} | 3.507 |
| bundle_helpers | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.752 |
| typecheck | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 1.315 |
| verify_layout | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0.048 |
| runner | FAIL | {"expected":1,"executed":1,"passed":0,"failed":1,"skipped":0,"unrunnable":0} | 0 |

runner: KeyboardInterrupt; inspect private runtime log

| teardown | PASS | {"expected":1,"executed":1,"passed":1,"failed":0,"skipped":0,"unrunnable":0} | 0 |

Runtime: 214.292 s.
Decoder: {"requests": 0, "peak_in_flight": 0, "rejected_by_budget": 0, "shared_metrics": "sampled every 2 seconds; not own request attribution"}
Raw content-bearing stdout stays in ignored runtime scratch. Retained logs contain only status/count projections.
