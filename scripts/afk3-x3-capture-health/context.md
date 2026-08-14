# Context — x3-capture-health

Iteration 4.

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

- [x] Route passes its `HelperPresenceSnapshot` and typed v2 session snapshot to the server-side
  projection; the production `/snapshot` path, not only a direct unit call, exercises the fusion.
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
3. **Done (iteration 3):** `_snapshot_response()` now obtains one typed
   `LiveV2SessionSnapshot`, serializes it, and passes that same object to
   `project_live_capture_status()`. The real-route regression sends a normal helper heartbeat and
   microphone frame while the system lane has accepted zero frames; `/snapshot` reports
   `awaiting_audio` and names shared audio. It then fails the server v2 system lane while the
   helper still calls it `capturing`; `/snapshot` keeps the non-terminal meeting `recording` but
   replaces the healthy copy with the server-authored lane failure. Worktree-backed validation:
   `PYTHONPATH=. .venv/bin/pytest -q tests/test_live_capture_status.py tests/test_live_api.py`
   passed (50 tests, 327 subtests); the linked helper-presence assertion passed (9 tests), and
   preflight passed. Plain `.venv/bin/pytest` resolves the desktop checkout through this shared
   virtualenv, so it cannot validate this worktree without `PYTHONPATH=.`. This slice does not
   provide recency, sustained-silence, rejection/backpressure, or terminal-reason evidence.
4. **Done (iteration 4):** the committed `LiveV2Session` probe exercises the production
   `accept -> snapshot/account_through` path. It proves that silent and voiced frames have equal
   snapshots, a snapshot remains equal after 27 ms of measured server-monotonic elapsed time,
   and repeated `LiveV2OutOfOrderFrameError` / `LiveV2LaneCapacityError` outcomes leave their
   snapshots equal. Accounting releases the sole silent retained frame. The raw JSON is
   `evidence/phase1/x3-capture-health/iteration-04-observation-contract.json`; its rerunnable
   probe and verdict are beside it. `docs/design-capture-health-observation-contract.md` proposes
   an x3-owned metadata-only registry: server arrival time, consecutive silent samples,
   consecutive sequence rejections, consecutive backpressure rejections, and the last rejection
   time. It deliberately contains no threshold or user-copy policy. Preflight passed.
5. **Next — implement only the measured observation carrier:** create/remove the typed registry
   with the v2 session in `live_transport.py`, update it after accepted and classified rejected
   frame outcomes, and supply its immutable snapshot to the projection using an injectable
   monotonic clock. Add direct and real-route tests for counter reset/lifecycle. Do not choose a
   stale/silence/rejection threshold until a separate cadence-and-recovery prototype records it.
   Terminal reason reachability remains constrained by x6-owned `live_service_runtime.py`; do not
   edit it from this ticket.
