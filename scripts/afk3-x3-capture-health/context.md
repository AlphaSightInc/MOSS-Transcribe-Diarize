# Context — x3-capture-health

Iteration 0.

Branch `afk3/x3-capture-health` from `dev`. Every defect in the PRD was found by independent adversarial
review with a reproduction; they are facts, not hypotheses. Read `docs/phase1-afk-charter.md`
(binding) and the closed decisions in `.wayfinder/tickets/` before your first change.

## Known pre-existing test failures — not yours

`l2-stage0/test_legacy_ingest.py` (55 != 92) and four `test_macos_uds_tracer.py` tests fail
identically at `pre-afk-20260813`. `l15/test_l1_baseline.py` fails with `l15_product_tree_drift`:
that guard correctly refuses to run when the product tree moved — **do not edit its pin**, that
would falsify a measurement baseline.

## Validation

```bash
.venv/bin/pytest -q          # ~1006 pass, 2 skip, 387 subtests
python3 scripts/afk-guardrails/preflight.py x3-capture-health
```

## Acceptance checklist

- [ ] Route passes its `HelperPresenceSnapshot` to the server-side projection; the production
  `/snapshot` path, not only a direct unit call, exercises the fusion.
- [ ] Projection distinguishes `starting`, `awaiting_audio`, `recording`, and `failed`, using
  server-observable frame recency, sequence gaps, lane accounting, sustained silence,
  backpressure, and reported lane health.
- [ ] The real route probe proves that each unhealthy case avoids the healthy recording claim:
  missing system lane, stale post-frame arrival, all-silent frames, sustained sequence rejects,
  and a server-reported failed lane.
- [ ] Terminal stop/failure preserves a client-readable server-authored reason, including a
  microphone-permission denial.
- [ ] `.venv/bin/pytest -q tests/test_live_capture_status.py tests/test_live_api.py` passes, and
  the committed re-runnable route probe plus raw output live under
  `evidence/phase1/x3-capture-health/`.
- [ ] The focused gate remains green after merging current `dev`; `progress.txt` identifies what
  each criterion proves and any uncovered boundary.

## Ranked candidates
1. **Done (iteration 1):** turn the PRD into the checklist above. `dev` was already merged at
   `9704074`; preflight was reported OK by this run's launcher. No product claim follows from
   that plumbing state.
2. Inspect the current projection, route, and focused tests to define the smallest production
   vertical slice and identify the available server facts without inventing thresholds.
3. Implement that slice with a route-level regression test; only then add the committed
   five-scenario route probe and raw evidence.
