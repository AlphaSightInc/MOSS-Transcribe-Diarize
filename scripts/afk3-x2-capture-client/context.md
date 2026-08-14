# Context — x2-capture-client

Iteration 4.

Branch `afk3/x2-capture-client` from `dev`. Every defect in the PRD was found by independent adversarial
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
python3 scripts/afk-guardrails/preflight.py x2-capture-client
```

## Acceptance checklist

- Preserve the settled core: one shared AudioContext; worklet-port-driven POSTs only; one
  arithmetic clock anchor per lane; descriptor-derived geometry; exactly nine v2 keys.
- Serialize POSTs independently per lane. For lane frames: retry capacity 429 without
  consuming its sequence; do not resend queue-backpressure 429 whose sequence was accepted;
  handle failure-less 429 without wedging; resync/recreate on 409; stop on 400.
- Emit the server's browser failure vocabulary from real browser events: track end,
  AudioContext state change, sustained clipping, and silent microphone. `stop()` must send a
  final `stopped` heartbeat; no timer-based heartbeat is permitted.
- Use `context.sampleRate` in frame metadata, enforce the `>= 1e-4` preflight-signal gate,
  and bump `deviceEpoch` plus mark `discontinuity` when a lane is replaced/restarted.
- Prove the 429/409/400 and heartbeat branches with non-vacuous tests. After merging current
  `dev`, run `npm --prefix frontend run typecheck && npm --prefix frontend test`; commit raw,
  rerunnable evidence under `evidence/phase1/x2-capture-client/`. The client does not prove
  attended display capture or server/inference behavior.

## Current implementation evidence

`dev` (`23afb6d`) remains an ancestor of this branch; no merge is pending. The owned r2 baseline
has now been restored from `afk2/r2-capture-client` without its loop state or server files:
`frontend/src/capture/captureClient.ts`, its focused test, and
`frontend/public/worklets/lane-framer.js`. `App.tsx` remains untouched and still does not mount
the client, per ownership.

Iteration 4 replaced the baseline fire-and-forget frame POST with an independent queue per lane.
Frames obtain their sequence only at the serial queue head. A structured 429 with
`failure.code == v2_lane_retention_capacity_reached` stays at that head, so the next worklet-port
frame retries the identical body before a later frame can post. Other failures retain the
baseline's drop-and-report behaviour for now. The focused production-path tests prove both one
in-flight post per lane and capacity bodies `[0, 0, 1]`; they would fail if serialization or the
unconsumed retry were removed. Validation: `npm --prefix frontend test --
src/capture/captureClient.test.ts` (7 passed), `npm --prefix frontend run typecheck` (pass), and
`python3 scripts/afk-guardrails/preflight.py x2-capture-client` (`PREFLIGHT OK`).

## Ranked candidates

1. Add the remaining frame-taxonomy vertical slice: explicitly prove the consumed queue-429 and
   failure-less 429 advance rather than retry, resync/recreate after 409, and stop capture on 400.
   Preserve the per-lane worklet-driven queue and do not introduce timers.
2. Add real browser-health state/failure reporting and a final `stopped` heartbeat, with a test
   that rejects timer-based heartbeats.
3. Add lane replacement/restart semantics: actual context sample rate in frames, thresholded
   preflight signal, epoch increment, and marked discontinuity. Do not touch `App.tsx`; mounting
   remains orchestrator-owned.
