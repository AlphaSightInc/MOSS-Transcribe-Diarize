# Context — x3-capture-health

Iteration 2.

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
2. **Done (iteration 2):** inspected the projection, `/snapshot` route, v2 snapshot contract,
   helper presence, terminal cleanup, and focused tests. `_snapshot_response()` obtains
   `v2_session` for the response but passes only `HelperPresenceSnapshot` to
   `project_live_capture_status()`, so the projection discards the server's lane accounting and
   health. `LiveV2SessionSnapshot` already supplies per lane `accepted_samples`,
   `accounted_samples`, `failed_samples`, `retained_samples`, `next_sequence`, `health`, and
   `failure_code`; helper presence additionally supplies lane drops/discontinuities. The focused
   gate is green (49 passed; 327 subtests), but its current route test explicitly accepts the
   false-healthy outcome for a failed microphone lane. Frame arrival time, cumulative sequence
   rejects/backpressure, and sustained-silence facts are not retained in either snapshot: a
   `LiveV2Frame` carries `silent` and a client capture timestamp only while it remains retained.
3. **Next — smallest threshold-free production slice:** pass the typed v2 snapshot into the
   projection on the real `/snapshot` route. Add route regressions for (a) a helper reporting
   capture while one lane has accepted zero server frames, which must be `awaiting_audio` rather
   than healthy recording, and (b) a server v2 lane with `health="failed"`, which must not be
   healthy recording even if the helper heartbeat has not named it. This establishes the real
   route seam and uses only existing server facts. Do not claim frame recency, sustained silence,
   accumulated sequence rejects, or backpressure until a measured observation carrier exists;
   any threshold for those needs the required prototype first.
