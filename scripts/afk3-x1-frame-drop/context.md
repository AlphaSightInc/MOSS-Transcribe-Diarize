# Context — x1-frame-drop

Iteration 6.

Branch `afk3/x1-frame-drop` from `dev`. Every defect in the PRD was found by independent adversarial
review with a reproduction; they are facts, not hypotheses. Read `docs/phase1-afk-charter.md`
(binding) and the closed decisions in `.wayfinder/tickets/` before your first change.

## Current branch-validation baseline — not x1 work

The iteration-6 full-suite run has three failures: the L15 baseline intentionally refuses the
product-tree drift from `9089b332`, and two Darwin-only macOS lifecycle/UDS tests fail
(`test_built_macos_app_finishes_launch_and_honors_application_terminate` and
`test_built_macos_app_cli_cross_real_uds_and_private_tls_server`). All remaining tests passed:
`1007 passed, 4 skipped, 479 subtests passed`. Neither `tests/test_macos_uds_tracer.py` nor the
L15 baseline paths differ from `pre-afk-20260813...HEAD`; x1 must not edit their pins or tests to
manufacture a green suite. The strict all-suite exit is therefore an external baseline blocker,
not an x1 regression.

## Validation

```bash
.venv/bin/pytest -q          # ~1006 pass, 2 skip, 387 subtests
python3 scripts/afk-guardrails/preflight.py x1-frame-drop
```

## Gate checklist

- [x] Slow-POST probe proves captured frames are queued rather than silently discarded, and has a
  direct elapsed-time vs admitted-frame assertion that fails on regression.
- [x] G7 runs hidden for more than five minutes at descriptor-enforced
  `frame_samples=8000`, joins strict-v2 admissions, and preserves its raw arrays.
- [x] A forced 409 exercises `recreateSession`, drains sends before resetting sequence state,
  resumes cleanly, and leaves a failed-recreate button usable.
- [x] All three claims have committed, re-runnable probes and raw artifacts under
  `evidence/phase1/x1-frame-drop/`; `preflight.py x1-frame-drop` confirms their citations and
  ownership. `iteration-6` also verified those six probe/artifact paths are tracked.
- [ ] Strict all-suite validation exits green after merging current `dev`: `dev` is already an
  ancestor (0 behind / 11 branch commits), but `pytest -q` exits 1 only on the inherited baseline
  failures above. Do not mask them with exclusions; needs their owning work, not an x1 change.

## G7 production-geometry result

`probe_g7_hidden_tab.py` requires `--frame-samples`, configures that only on its local runtime,
and verifies that the page then receives the same geometry from `/api/live/descriptor`. Its route
middleware retains only HTTP-200 strict-v2 frame admissions and joins those records to post-ACK
worklet telemetry by lane plus wire sequence. The 310 s run at 8,000 / 16,000 geometry had 620
hidden route admissions on each lane over 309.491/309.492 s: both exactly equalled the elapsed
cadence expectation. All 621 heartbeat POSTs were 200; hidden p50/p95/max was 498/505/507 ms,
below the 2 s helper lease. Raw arrays: `evidence/phase1/x1-frame-drop/iteration-5-g7-hidden-8000.json`.

This deterministic local production-route result does not cover real-provider inference, physical
microphone input, or attended display capture. The pre-existing slow-POST and forced-409 probes
also passed again against the added route instrumentation using temporary outputs.

## Current integration state

`dev` (`23afb6d`) is already an ancestor of this branch through merge `ccd906d` (verified again
at iteration 6: `git rev-list --left-right --count dev...HEAD` = `0 11`), so the required
merged-result is current `HEAD`; no merge is necessary. The full-suite command at that head was
`1007 passed, 4 skipped, 479 subtests passed` plus the three inherited failures documented above.
`python3 scripts/afk-guardrails/preflight.py x1-frame-drop` remains `PREFLIGHT OK`.

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

1. Blocked outside x1: restore the inherited L15/macOS baseline suite to a green exit, then rerun
   the exact full-suite command on this unchanged merged head. Do not change those out-of-scope
   tests, their pins, or test selection from this ticket.
