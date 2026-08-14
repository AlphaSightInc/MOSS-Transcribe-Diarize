# Context — x5-auth-residual

Iteration 1.

Branch `afk3/x5-auth-residual` from `dev`. Every defect in the PRD was found by independent adversarial
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
python3 scripts/afk-guardrails/preflight.py x5-auth-residual
```

## Acceptance checklist

- [ ] Merge current `dev` into this branch before final validation; do not re-implement or
  revert its reserved-`device_id`, whitespace-token, or token-file-permission fixes.
- [ ] Make shared-principal revocation durable across a fresh registry start, or refuse the
  revocation before reporting success. Commit a re-runnable restart-durability probe and raw
  output under `evidence/phase1/x5-auth-residual/`.
- [ ] Replace the process-wide `hmac.compare_digest` mock assertion with a test that exercises
  the real constant-time comparison property without brittle exact call ordering.
- [ ] Verify padded tokens are normalized through the comparison path, not only when the token
  file is read.
- [ ] Commit a locally-run Uvicorn probe proving the reserved-id and whitespace-token fixes on
  the real wire; TestClient alone is insufficient for the single-space case.
- [ ] Pass `.venv/bin/pytest -q tests/test_live_auth.py tests/test_live_api.py
  tests/test_live_service_deployment.py tests/test_speaker_identity_provider.py` after merging
  `dev`, with committed raw artifacts and a criterion-by-criterion `progress.txt` summary.

## Current base

`dev` is already an ancestor of `HEAD` through merge commit `b8aaa13`; this iteration confirmed
that relation and `PREFLIGHT OK`. The Phase 1 posture remains a single shared-token trust domain;
this ticket hardens operator revocation rather than restoring client-asserted identity.

## Ranked candidates
1. Trace `LiveAccessRegistry` persistence/restart semantics and add a failing, committed
   revocation-durability probe before changing production code.
2. Inspect the token comparison path and replace the fragile constant-time test with a
   feature-binding property test.
3. Build a locally-run Uvicorn wire probe for reserved-id and whitespace-token behavior.
