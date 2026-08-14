# Context — x2-capture-client

Iteration 3.

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

## Ranked candidates

`dev` (`23afb6d`) is already an ancestor of this branch; iteration 2 re-validated the merged
state with `PREFLIGHT OK`. No merge is pending.

The ranked candidate's assumed baseline is absent from the current branch, not merely untested:

- `git ls-tree -r HEAD -- frontend/src/capture frontend/public/worklets` and the same query on
  `dev` return no files. `frontend/src/App.tsx` remains the static shell and imports no capture
  client.
- The exact core described as "keep" in this PRD exists only on unmerged
  `afk2/r2-capture-client`: `c602f4a` adds `captureClient.ts`, its focused test, and
  `lane-framer.js`; `218ebfb` adds its clean-stop path. That branch's client still contains the
  defects named by this ticket (`void this.postFrame(...)`, fire-and-forget frames, all non-OK
  responses dropped, requested descriptor rate in frame metadata, and `level > 0`).
- `afk3/x1-frame-drop`, `afk3/x3-capture-health`, and `dev` also contain no capture-client files;
  there is no concurrent owned implementation to extend. The server's current frame route
  confirms the PRD's response distinction: `LiveV2LaneCapacityError` becomes a structured 429
  before admission, while queue backpressure is a failure-less 429 after `v2_session.accept`.

This invalidates the prior candidate as phrased: there is no client API or test seam in this
branch to modify. It is a context repair, not an acceptance claim.

## Ranked candidates

1. Reintroduce only the owned r2 capture baseline (`frontend/src/capture/captureClient.ts`, its
   test, and `frontend/public/worklets/lane-framer.js`) into this branch, without r2's loop state
   or out-of-scope server files; include the first serialized-post / capacity-429 regression
   slice rather than importing its known faulty behaviour untested.
2. Then add the remaining 429/409/400 branches and browser-health/lane-restart behaviours in
   separately validated vertical slices. Do not touch `App.tsx`; its integration remains owned by
   the orchestrator.
