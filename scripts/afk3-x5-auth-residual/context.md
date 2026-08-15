# Context — x5-auth-residual

Iteration 6.

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

- [x] Current `dev` is already an ancestor of this branch (`git merge-base --is-ancestor dev
  HEAD` returned 0 before final validation); its reserved-`device_id`, whitespace-token, and
  token-file-permission fixes remain intact.
- [x] Shared-principal revocation survives a fresh registry start. The revocation marker persists
  without the configured bearer or its digest; `iteration-3-shared-revocation-restart.json` is the
  committed raw probe output.
- [x] Capture and view bearer lookups use `hmac.compare_digest`; the regression test injects
  digest values that reject ordinary equality, so replacing either comparison with `==` fails
  through real `authorize()` calls without mocking process-wide stdlib state.
- [x] Padded bearer values normalize at the registry comparison boundary; the route-level
  regression sends a padded `Authorization` header and receives capture authority for the
  configured token.
- [x] A locally-run Uvicorn/TLS HTTP/1.1 probe proves the reserved-id and whitespace-token
  fixes on the real wire. `iteration-6-uvicorn-wire-auth.json` records reserved pairing 403,
  a persisted pre-fix reserved-id bearer 401, raw `Bearer ` 401, and whitespace token-file
  refusal before startup.
- [x] Required four-file gate passed against this `dev`-containing branch: 161 passed, 1 warning,
  355 subtests. Preflight also passed; the criterion-by-criterion summary and committed raw
  probe artifacts are in `progress.txt`.

## Current base

`dev` remains an ancestor of `HEAD` through merge commit `b8aaa13`; iteration 7 rechecked that
relation immediately before the final gate. The Phase 1 posture remains a single shared-token
trust domain; this ticket hardens operator revocation rather than restoring client-asserted
identity.

## Ranked candidates
No open candidates. The acceptance gate is satisfied; await orchestrator review and reconciliation.

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
- `probe_uvicorn_wire_auth.py` starts local Uvicorn with TLS and a fake live runtime, then uses
  real loopback and dynamically selected private-peer connections. It proves a fresh reserved
  pairing is refused, a pre-fix persisted `shared-token` credential is no longer authoritative,
  and h11-parsed whitespace bearer input reaches a 401. It does not claim production deployment
  verification or general TLS-client coverage.
- Final integration evidence: immediately before the gate, `dev` (`23afb6d`) was an ancestor of
  the branch (`git merge-base --is-ancestor dev HEAD` -> 0). The required four-file suite then
  passed with 161 tests, 355 subtests, and one known FastAPI/TestClient deprecation warning;
  preflight returned `PREFLIGHT OK`.
