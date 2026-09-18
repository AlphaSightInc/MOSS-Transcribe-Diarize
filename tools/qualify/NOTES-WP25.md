# WP25 isolation prototype
Question: can existing case logic run with independently supplied endpoints and paths?
Primitives: endpoint, scratch/output directory, counted dispatch, observed result.
Invariant: unchanged case inputs/predicates and product policy; missing results never pass.
Unknowns: live failures, latency, total calls, concurrent sibling load.
Falsifier: any case bypasses the owned proxy, writes outside this checkout, or disappears.
Tool decision: inspect concrete runtime dependencies; validate real input dimensions and
existing HTTP accounting before changing interfaces. A failed dependency blocks its gate.
Command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python tools/qualify/prototype_wp25.py`.
Measured: 4/4 hard-coded dependencies found; 2/2 corpus inputs are 960000 frames,
16 kHz mono. Existing helper suite: 7 passed, 1.58s; budget HTTP control 200,200,429.
Verdict: runtime parameters are separable; absorb into existing benches. No claim of
live correctness. Batch JSON replaces interactive TUI for reproducibility; prototype removed.
Capacity retains its clean/no-contention predicate, but --allow-contention suppresses pauses
as WP25 explicitly requires. Contaminated measurements remain failures, never clean capacity.

Preflight full suites: Python 1910 passed / 2 skipped / 1912 collected, 37 subtests,
151.04s; frontend 249/249; helpers 9/9; typecheck/layout passed; assets 17/17 exact.
The static-only wrapper initially raised at final display because --out was relative;
fixed by resolving the output parent. Suite measurements were already retained. No GPU
calls occurred in preflight. Tree-clean FAIL is expected before the implementation commit.
