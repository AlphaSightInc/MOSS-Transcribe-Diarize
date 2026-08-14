# Context — x5-auth-residual

Iteration 5.

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
# `.venv/bin/pytest` is an absolute launcher from the original checkout. Prefix
# `PYTHONPATH="$PWD"` so it validates this worktree's source.
env PYTHONPATH="$PWD" .venv/bin/pytest -q tests/test_live_auth.py tests/test_live_api.py tests/test_live_service_deployment.py tests/test_speaker_identity_provider.py
python3 scripts/afk-guardrails/preflight.py x5-auth-residual
```

## Acceptance checklist

- [ ] Merge current `dev` into this branch before final validation; do not re-implement or
  revert its reserved-`device_id`, whitespace-token, or token-file-permission fixes.
- [x] Shared-principal revocation survives a fresh registry start. The revocation marker persists
  without the configured bearer or its digest; `iteration-3-shared-revocation-restart.json` is the
  committed raw probe output.
- [x] Capture and view bearer lookups use `hmac.compare_digest`; the regression test injects
  digest values that reject ordinary equality, so replacing either comparison with `==` fails
  through real `authorize()` calls without mocking process-wide stdlib state.
- [x] Padded bearer values normalize at the registry comparison boundary; the route-level
  regression sends a padded `Authorization` header and receives capture authority for the
  configured token.
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
1. Build a locally-run Uvicorn wire probe for reserved-id and whitespace-token behavior.

## Completed this run

- Shared-principal revocation now persists a digest-free revoked record and restores that state
  when configured again. Focused gate: 159 passed / 355 subtests. The committed restart probe now
  records `true/true/true` for in-process rejection, persisted marker, and fresh-start rejection.
- The current merged `dev` did not contain the prior F2 constant-time branch work, so both
  digest lookup paths now use `hmac.compare_digest`. The 17-test auth file passes; the new
  `EqualityTrap` regression exercises the real capture and view paths and fails if either falls
  back to ordinary equality. It intentionally does not attempt an unreliable wall-clock timing
  measurement.
- `LiveAccessRegistry.authorize()` now strips bearer padding immediately before its digest lookup,
  matching the token-file canonicalization. The route-level regression proves a padded shared
  bearer succeeds; the focused auth/API selection passed 3 tests and preflight remained green.
