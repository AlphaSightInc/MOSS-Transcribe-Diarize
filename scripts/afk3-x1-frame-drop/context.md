# Context — x1-frame-drop

Iteration 4.

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

- [x] Slow-POST probe proves captured frames are queued rather than silently discarded, and has a
  direct elapsed-time vs admitted-frame assertion that fails on regression.
- [ ] G7 runs hidden for more than five minutes at descriptor-enforced
  `frame_samples=8000`, joins strict-v2 admissions, and preserves its raw arrays.
- [x] A forced 409 exercises `recreateSession`, drains sends before resetting sequence state,
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

## P0 transport result

The page now derives one FIFO capacity per lane from
`descriptor.bounds.max_retained_samples / descriptor.frame_samples`, keeps one frame POST in
flight per lane, and assigns a wire sequence only to the FIFO head. It advances that sequence only
after a successful response; an unsuccessful response retains the same head. Queue overflow
increments the heartbeat's actual `dropped_frames` and marks the first later accepted frame
discontinuous.

`probe_slow_post_characterization.py` drives the actual page/worklet, local strict-v2 route, and
100 ms delayed frame responses. At 1,000 / 16,000 geometry (62.5 ms/frame), microphone/system
admitted 49/50 frames over 2.932/2.996 s versus 48/49 elapsed-cadence frames; the direct
admitted-vs-elapsed gate allows only the one-record observation race. Each lane held exactly one
response and had wire sequences in worklet order; queue depth peaked at 21 of the descriptor's
320-frame capacity. Raw arrays: `evidence/phase1/x1-frame-drop/iteration-3-slow-post-fifo.json`.

The 409 path now pauses all FIFO senders, waits for every old-session response, resets fresh
sequences only after that drain, retains queued PCM with wire sequences cleared, and offers an
explicit recreate control. The capture bearer remains closure-local across recreation and is
cleared on stop; a failed create re-enables the same control. The forced route probe held an
already-admitted microphone response for 600 ms while a system sequence conflict returned 409.
It showed the old microphone lane advance to one before reset, then the retried new session admit
system/microphone sequence zero and advance each to one. Raw state:
`evidence/phase1/x1-frame-drop/iteration-4-recreate-session.json`.

These are deterministic local production-route results at 1,000-frame geometry. They do not run
worklet cadence or a real provider, and they do not satisfy the required 8000-frame hidden G7.

## Ranked candidates

1. Restore G7's required `--frame-samples 8000` argument and run the hidden-tab strict-v2
   admission join for more than five minutes, preserving raw arrays.
2. Before a completion claim, merge current `dev` and run branch validation on the merged result;
   retain the known baseline failures rather than changing their pins.
