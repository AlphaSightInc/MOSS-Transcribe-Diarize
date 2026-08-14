# Context — x1-frame-drop

Iteration 0.

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

## Gate checklist (recorded iteration 1)

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

## Ranked candidates

1. Characterize the existing worklet/POST behavior with a committed slow-POST probe and define
   the smallest bounded queue policy from measured state.
2. Implement the resulting queue/counter behavior in the capture prototype, then make the
   elapsed-vs-admitted-frame assertion prove it.
3. Exercise recreate-after-409 only after send-drain semantics exist; then re-run production-
   geometry G7 with raw arrays.
