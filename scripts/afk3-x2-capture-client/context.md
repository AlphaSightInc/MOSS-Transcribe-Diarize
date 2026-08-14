# Context — x2-capture-client

Iteration 0.

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

1. Merge `dev` in and confirm the capture-client preflight remains OK.
2. Map the capture-client API and test seams, then implement the smallest serialized-post
   vertical slice with branch-specific tests.
