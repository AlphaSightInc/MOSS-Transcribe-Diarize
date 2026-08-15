# Context — x3-capture-health

Iteration 11.

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
- [x] Projection distinguishes `starting`, `awaiting_audio`, `recording`, and `failed`, using
  server-observable frame recency, sequence gaps, lane accounting, sustained silence,
  backpressure, and reported lane health.
- [x] The real route probe proves that each unhealthy case avoids the healthy recording claim:
  missing system lane, stale post-frame arrival, all-silent frames, sustained sequence rejects,
  retryable backpressure, and a server-reported failed lane.
- [x] Terminal stop/failure preserves a capture-owner-readable server-authored status, including
  a microphone-permission denial; terminal view authority remains revoked.
- [x] `.venv/bin/pytest -q tests/test_live_capture_status.py tests/test_live_api.py` passes, and
  the committed re-runnable route probe plus raw output live under
  `evidence/phase1/x3-capture-health/`.
- [x] The focused gate remains green after merging current `dev`; `progress.txt` identifies what
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
5. **Done (iteration 5):** `LiveCaptureObservationRegistry` now records the measured missing
   facts with an injectable server-monotonic clock: last accepted arrival, consecutive silent
   samples, consecutive sequence and retryable-backpressure rejects, and last rejection. The
   v2 route writes only after accepted / classified outcomes; a lifecycle facade releases the
   observation whenever the v2 session is released or helper expiry calls `expire`. Direct and
   real-route tests prove reset after accepted voiced audio, abort cleanup, and helper-lease
   cleanup. The focused gate passed: 52 tests, 327 subtests; preflight passed. No threshold or
   user-facing status policy changed.
6. **Done (iteration 6):** the committed local `create_app` route probe invokes authenticated v2
   frame, heartbeat, and snapshot routes at the measured 8,000-sample / 16 kHz geometry. It
   records actual server-monotonic cadence, a 2.05 s post-frame stall, four silent frames, four
   sequence rejects, and four per-lane capacity rejects; accepted route frames reset each condition
   (with a real peer-lane mixer drain before a capacity retry). The Chrome worklet baseline is
   visible p95 508.1 ms / hidden p95 506.5 ms, so the verdict is 2,000 ms no-arrival, 32,000
   consecutive silent samples, or four consecutive classified rejects. Raw output and rerunnable
   probe are `evidence/phase1/x3-capture-health/iteration-06-live-route-thresholds.json` and its
   adjacent probe; `docs/design-capture-health-observation-contract.md` records the decision.
   Terminal-readable failure remains constrained by x6-owned `live_service_runtime.py`.
7. **Done (iteration 7):** `LiveCaptureHealthPolicy` derives four descriptor frame periods from
   the live runtime's `frame_samples` and `sample_rate`, plus four classified rejections. The
   production snapshot route supplies it to the projection. A deterministic route regression
   uses the same injected server-monotonic clock as the observation registry and proves stale
   arrival, four descriptor-frame silence, four sequence rejects, and four retryable capacity
   rejects each replace the healthy copy; a subsequent accepted frame restores it. The refreshed
   rerunnable threshold probe asserts the live stale response and records it in
   `evidence/phase1/x3-capture-health/iteration-06-live-route-thresholds.json` (2,063.594 ms
   observed age against the 2,000 ms descriptor-derived threshold). Focused validation passed:
   53 tests / 327 subtests; preflight passed. Terminal-readable failure remains x6-owned.
8. **Done (iteration 8):** the rerunnable local `create_app` probe now emits and asserts a
   `server_fused_route_status_matrix` through authenticated `/snapshot`: missing system audio,
   stale arrival, sustained silence, sustained sequence rejection, retryable backpressure, and
   server-reported lane failure. Every row says `healthy_recording_claim: false`; the final row
   additionally proves the helper still says `capturing` while the v2 system lane says `failed`.
   Raw output is `evidence/phase1/x3-capture-health/iteration-06-live-route-thresholds.json`.
   No product policy changed. The focused gate passed (53 tests, 327 subtests) and preflight
   passed after the evidence refresh; terminal readability remains x6-owned.
9. **Done (iteration 9):** the committed local-route probe sends a terminal helper heartbeat
   reporting `browser_microphone_permission_denied`, then requests `/snapshot` using both the
   former capture and view credentials. The runtime retains `aborted` / `helper_failed` plus the
   typed microphone code, but cleanup has released access: the capture credential receives only
   `403 session is not owned by this device`, and the view credential only `401 invalid bearer
   authority`. Neither response has the server's capture phase or plain-language status. Raw
   output is `evidence/phase1/x3-capture-health/iteration-09-terminal-reason.json`; the committed
   probe and NOTES are adjacent. x6 completed a separate runtime-terminal snapshot fix on
   `afk3/x6-terminal-visibility`, but it is not in `dev` and does not solve this helper-abort plus
   access-release path.
10. **Done (iteration 10):** terminal media teardown now preserves the capture owner's tiny
    session-authorization binding through helper failure, clean stop, abort, and failed v2 stop;
    runtime lifecycle still rejects the view credential. The snapshot projects any runtime
    terminal lane failure before missing helper/v2 state, so microphone denial returns
    `capture_phase: failed` and the server-owned Chrome permission instruction rather than a
    403. Real-route regressions prove helper failure (capture 200/view 401/no credential fields)
    and clean-stop readability; v2 terminal writes return their existing 409 and legacy writes
    their existing terminal 429. The committed raw probe is
    `evidence/phase1/x3-capture-health/iteration-10-terminal-readable.json`; focused validation
    passed (54 tests, 327 subtests) and preflight passed.
11. **Done (iteration 11):** current `dev` (`23afb6d`) was already an ancestor of this branch's
    `c229ec1` HEAD, so no merge created a new commit. The exact merged head passed the focused
    gate (54 tests, 327 subtests) and both committed local-route probes. The refreshed
    non-terminal matrix still makes all six unhealthy scenarios non-healthy; the separate
    terminal probe still gives only the capture credential its server-authored microphone-denial
    status. `iteration-06` scope wording now correctly links that distinct terminal evidence.
    The probes remain deterministic local `TestClient` evidence, not browser-prompt or deployed
    production proof. Acceptance is now evidenced; await the required independent reviewer.
