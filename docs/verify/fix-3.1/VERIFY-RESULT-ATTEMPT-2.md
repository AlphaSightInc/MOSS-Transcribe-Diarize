# FIX-3.1 fresh-context verification — layout failure receipt

**Verdict: FAIL**

- Tested SHA: `c2736d1c264d4943d89544b736490e0662d363f3`
- Branch `round3/fix-scheduling`: PASS.
- Ancestor `738cdfdd`: PASS.
- Initial tracked state: clean. Python import custody: PASS; package resolved inside this clone.

## Required commands, sequential order

1. Python suite: FAIL (exit 1): `1 failed, 2107 passed, 5 skipped, 37 subtests passed, 21 warnings` in `189.53s`.
   - Failure: `tests/phase2/test_tls_preparation.py::test_verify_layout_current_tree`.
   - Exact cause: `FAIL: VERIFY.md belongs under docs/verify/<wp>/`.
2. Frontend tests: PASS (exit 0): `28` files, `310` tests.
3. Frontend typecheck: PASS (exit 0): zero TypeScript errors.
4. Frontend build: PASS (exit 0): `34` modules transformed.

## Independent FIX-3.1 inspection

- PASS: headed reference start/end preservation and ordered interval-bound visible-word credits.
- PASS: final wrong/missing rows null first/stable clocks; healthy and violating controls exist.
- PASS: exact `300.0s` mono PCM lane replay and headed Chromium exact `--mute-audio` control.
- PASS: per-owner clocks are read-only and project through existing operator status.
- PASS: no scheduling-policy or product-endpoint changes found.
- PASS: bucket-only visible-word evidence refusal has a test.

## Retained S9 evidence and request receipt

- API: `856 correct + 20 wrong + 13 missing = 889`; DOM: `842 + 29 + 18 = 889`.
- Wrong/missing rows with non-null first/stable fields: API `0`, DOM `0`.
- Negative or invalid finite latencies: API `0`, DOM `0`.
- Session `300.0s`; meeting `closed`; finalization `final`.
- Receipt: `160` starts = `160` ends <= `250`; peak `1` <= `2`; final active `0`.

## Environment gates

- Ports `17851`, `19251`, `18251`: free — PASS.
- GPU lease text exact `FREE`: not found in repo, environment, or searched temporary/project roots — FAIL; unconfirmed.

No source repaired. No push, merge, deploy, or peer message performed.
