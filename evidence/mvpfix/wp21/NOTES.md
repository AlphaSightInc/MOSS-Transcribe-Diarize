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

Attempt 2: preparation interrupted before decoder load to correct an overly broad
UNRUNNABLE classification. WP7 needs no new argument if the owned stack uses its fixed
17867 app port; its fixed evidence paths resolve inside this checkout and can be restored.
The bundle now runs single/gap/alternating unchanged; writes to its two historical evidence
files are backed up and restored byte-for-byte. Local prototype invariants judge saved
identity count per reference voice, distinct voices, switches and unresolved segments.
This adds no product policy. Browser all/WP16/capacity remain incompatible with own tunnel.

## Completed bounded dry run

Baseline: evidence/qualify/5ae9566f017e-20260918T064038829598Z/summary.json.
Runtime 705.520 seconds; clean at start; manifest 57,600,000 tape bytes.
Python: 1879 collected/reported, 1877 executed/passed, 2 skipped, 37 passed subtests,
0 failures, 21 warnings. Frontend 244/244; helpers 6/6; typecheck/layout pass.
Asset parity 17/17 bytes equal, restored. Stack and teardown pass.
Workspace: 10 PASS, 3 FAIL (4/5/10), 1 SKIP (9, no configured relay models), 14 rows.
Standalone lane cases: 0/2 pass. Lifecycle 7/7; reshare 6/6.
Identity: single PASS; gap and alternating interrupted after the request cap was reached.
Ladder: process failed, 0/6 cases emitted; the request cap was already reached.
Browser all: 16 UNRUNNABLE; WP16: six-minute file 1 UNRUNNABLE + five failure classes
UNRUNNABLE. Default 30-minute files (3) and 4x600 capacity (4 sessions) skipped.
Own decoder calls exactly 300; peak in-flight 1; active at teardown 0. 267 shared-metric
samples, zero sampling errors; sampled shared running max 1 and waiting max 0.
Own ports 17867/18121/18122 had no listeners after teardown. WP7 historical output restored;
tracked production/tests/frontend/prototypes unchanged. No audio/transcripts/secrets in Git.

The 300-request dry-run budget cannot complete this unchanged bench composition: workspace
also internally invokes both lane cases. Exhaustion is a measurement limit, not acoustic
rejection of the unmeasured ladder or interrupted identity cases. Increasing a later run's
budget needs later authority; this command currently caps --budget at the authorized 300.
The local stack bypasses SQLite's exact version pin, as the supplied recipe does.

Before fresh rerun: strengthened missing-reference-voice falsifier and added budget-at-gate
metadata; helper tests now 7/7. Re-scored retained identity metrics: 3/3 statuses unchanged.
This reporting-only delta means a fresh gate-status comparison is not strict same-code
runtime determinism, even with zero status deltas. No extra decoder calls were made.
