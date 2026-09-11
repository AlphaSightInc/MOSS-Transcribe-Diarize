# Draft lane — default off

Question: can reader-only words beat the canonical freeze floor without changing identity,
quality surfaces, or delaying canonical work? Minimum primitives: one bounded audio window,
one optional request, and an under-lock lifecycle/coverage fence. The canonical queue and
committed audio prefix remain authoritative. No new identity evidence or policy.

A throwaway seven-case state probe (fresh, queued canonical, draft busy, preview covered,
committed, aborted, oversized) admitted only fresh/bounded work and refused publication after
coverage or abort. Absorbed into `tests/phase2/test_draft_lane.py`; no prototype scheduler ships.
Regression tests also hold a draft in flight while canonical commits, and exercise the real
reader without a browser. These test runtime scheduling, not GPU contention.

Runtime option `draft_lane_seconds=None` (CLI omitted) is off. An enabled lane uses one
request across the runtime, at most 2.5 seconds and 286 generated tokens, the existing runner
and prompt resolution. It never enters the canonical/rolling arbiter or identity preparation.
Snapshots expose `draft` beside, never inside, `session`; `draft_stats` is content-free.
Drafts never advance the canonical version, so enabled snapshot polling must not suppress
updates using that version alone. Canonical/provisional coverage retires draft text atomically.

Unknown: an already-running GPU request cannot be preempted by a later canonical request.
Real single/two-session measurements are required before recommending enablement. Until then,
keep off. Falsifier: added canonical delay, changed final word error rate, stale publication,
or no worthwhile latency gain. Bounds and identity policy stay untouched.

Measurement pending. No transcript text belongs in this evidence directory.
