# Context — x1-frame-drop

Iteration 2.

Branch `afk3/x1-frame-drop` from `dev`. Every defect in the PRD was found by independent adversarial
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
python3 scripts/afk-guardrails/preflight.py x1-frame-drop
```

## Gate checklist

- [ ] Slow-POST probe proves captured frames are queued/backpressured rather than silently
  discarded, and includes an elapsed-time vs admitted-frame assertion that fails on regression.
- [ ] G7 runs hidden for more than five minutes at descriptor-enforced
  `frame_samples=8000`, joins strict-v2 admissions, and preserves its raw arrays.
- [ ] A forced 409 exercises `recreateSession`, drains sends before resetting sequence state,
  resumes cleanly, and leaves a failed-recreate button usable.
- [ ] All claims have committed, re-runnable probes and raw artifacts under
  `evidence/phase1/x1-frame-drop/`; branch validation runs after merging current `dev`.

## Current integration state

`dev` (`23afb6d`) is already an ancestor of this branch through merge `ccd906d`; preflight
passed at iteration 1. Re-check the merged-result requirement after product work, before any
completion claim.

The PRD's literal `sendPaused || sendInFlight` predecessor is on the unmerged
`afk2/f1-canary-fixes` line, not this checkout. The checked-out page instead starts every frame
POST immediately and increments `seq` before its response. The P0 behavior requirement remains
open: the current path is neither a serial queue nor an explicitly backpressured sender.

## Measured decision

`probe_slow_post_characterization.py` now drives the actual page, worklet, local strict-v2 route,
and 100 ms delayed frame responses. At the route's 1,000 / 16,000 geometry (62.5 ms/frame), each
lane emitted and the route admitted 50 frames over ~3.065 s, but four responses were held at once.
The committed elapsed-vs-admitted assertion would fail if an in-flight guard returned and dropped
worklet messages. This is characterization evidence only, not a passing P0/G7 claim; raw arrays:
`evidence/phase1/x1-frame-drop/iteration-2-slow-post-characterization.json`.

The smallest bounded policy is a per-lane serial sender and FIFO whose capacity is derived from
`descriptor.bounds.max_retained_samples / descriptor.frame_samples`. On overflow it must report
the real `dropped_frames` and mark the first post-gap frame discontinuous; sequences are assigned
only when the FIFO head is sent. This avoids a new magic capacity while preserving each route
failure's existing sequence semantics.

## Ranked candidates

1. Implement the measured descriptor-derived per-lane FIFO/serial sender and true heartbeat
   counters, then turn the elapsed-vs-admitted assertion into its no-loss regression gate.
2. Exercise recreate-after-409 only after the new sender can drain deterministically; then re-run
   production-geometry G7 with raw arrays.
