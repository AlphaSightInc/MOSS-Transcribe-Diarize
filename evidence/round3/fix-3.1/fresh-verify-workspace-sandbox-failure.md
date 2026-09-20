# FIX-3.1 fresh-context verification — workspace sandbox receipt

**Verdict: FAIL**

- Tested SHA: `3beafec85eae9b2a615113c15489657b2e69e784`
- Branch: `round3/fix-scheduling` — PASS.
- Ancestor: `738cdfdd` — PASS.
- Initial tracked state: clean — PASS.
- Python custody: PASS; `moss_transcribe_diarize` resolved to this clone.

## Required commands

- Python suite — FAIL (exit 1): `2021 passed, 76 failed, 11 errors, 5 skipped, 37 subtests passed, 18 warnings` in `134.89s`.
  - Observed failures include sandbox-denied Chrome launch/process control and UNIX-socket bind.
  - Scoped operator-status control isolation: `1 failed, 1 warning`; `/tmp` UNIX-socket bind returned `EPERM`.
- Frontend tests — FAIL (exit 1): Vitest startup failed before collection.
  - Vite could not create `frontend/node_modules/.vite-temp/...`: `EPERM`.
  - `frontend/node_modules` points outside this clone to the protected primary checkout.
- Frontend typecheck — PASS (exit 0): `0` TypeScript errors.
- Frontend build — FAIL (exit 1): Vite failed before build for the same `.vite-temp` `EPERM`.

## Independent FIX-3.1 inspection

- PASS: headed reference start/end preservation and ordered interval-bound word credits.
- PASS: finally wrong/missing words null first/stable clocks; healthy and violating controls present.
- PASS: exact `300.0s` mono PCM lane replay and headed Chromium exact `--mute-audio` control.
- PASS: read-only per-owner scheduler clocks project through existing operator status.
- PASS: no scheduling-policy or product-endpoint change found; `git diff --check` clean.

## Retained S9 evidence and request receipt

- Session `300.0s`; finalization `final` — PASS.
- API: `856 correct + 20 wrong + 13 missing = 889` — PASS.
- DOM: `842 correct + 29 wrong + 18 missing = 889` — PASS.
- Wrong/missing rows with non-null first/stable fields: API `0`, DOM `0` — PASS.
- Negative finite latencies: API `0`, DOM `0` — PASS.
- Receipt: `160` starts, `160` ends, `160 <= 250`, peak `1 <= 2`, final active `0` — PASS.
- Bucket-only refusal test exists — PASS.

## Environment gates

- Ports `17851`, `19251`, `18251`: free — PASS.
- GPU lease text exact `FREE`: not found in supplied repo or environment — FAIL; unconfirmed.

No source repaired. No push, merge, deploy, or peer message performed.
