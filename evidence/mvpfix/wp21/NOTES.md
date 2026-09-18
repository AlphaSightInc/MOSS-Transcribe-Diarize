# WP21 preparation and dry-run record

Assigned branch started clean at c2e458676cf27b9e4da69bea20a1612152f1516a.
Integration had advanced to 5094206d (WP20 merged). No merge/rebase was authorized;
this dry run measures the assigned checkout, not WP20 or final integrated acceptance.
Prototype question/verdict: tools/qualify/NOTES.md; five interface witnesses / five.
Implementation is scripts/tools/docs/evidence only. No production or bench changes.

Validation purpose: helper tests falsify status omissions, denominator inflation, content
leakage and actual HTTP budget overshoot; full Python/frontend gates detect regressions
outside the helper tests. Asset rebuild compares bytes and restores original assets.
Failures are retained information, not permission to repair unrelated product code.
Fresh rerun procedure/result will live under docs/verify/wp21/.

Attempt 1 (33112b07): full Python 1877 passed / 2 skipped / 37 subtests, frontend
244 passed, helper 4 passed, typecheck/layout passed, asset bytes 17/17 equal.
Readiness incorrectly sent unauthenticated GET: observed descriptor HTTP 401 while
root HTTP 200 and server service_ready. Stopped owned runner with SIGTERM; teardown
passed, decoder calls 0. Retained aborted bundle is not the determinism baseline.
Fixed readiness to bootstrap with existing Client; real local HTTP regression checks
cookie propagation. Counts now distinguish reported tests from executed non-skips;
helper gate records individual tests. Tree cleanliness is an explicit gate.
