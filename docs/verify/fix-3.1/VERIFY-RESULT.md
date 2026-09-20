# FIX-3.1 fresh-context verification result

**Verdict: PASS**

- Tested SHA: `867a573ca8f6e12410629af303d6d0dc243f6b3c`.
- Branch: `round3/fix-scheduling` — PASS.
- Ancestor: `738cdfdd` — PASS.
- Initial tracked state: clean — PASS.
- Python custody: PASS; `moss_transcribe_diarize` resolved inside this clone.

## Required commands, in listed order

1. Python suite — PASS: `2108 passed, 5 skipped, 37 subtests passed, 21 warnings` in `185.46s`.
2. Frontend tests — PASS: `28` files, `310` tests.
3. Frontend typecheck — PASS: `0` TypeScript errors.
4. Frontend build — PASS: `34` modules transformed.

## Independent FIX-3.1 inspection

- PASS: headed reference start/end preservation and ordered interval-bound visible-word credits.
- PASS: finally wrong/missing words have null first/stable clocks.
- PASS: headed harness enforces exact `300.0s` mono PCM lane replay and Chromium args exactly `--mute-audio`.
- PASS: read-only per-owner scheduler clocks project through existing operator status.
- PASS: no scheduling-policy or endpoint changes found.
- PASS: healthy and violating controls exist; bucket-only visible-word evidence is explicitly refused by test.
- PASS: `git diff --check 738cdfdd..HEAD` clean.

## Retained S9 evidence and request receipt

- Session: `300.0s`; finalization `final`.
- API: `856 correct + 20 wrong + 13 missing = 889` rows.
- DOM: `842 correct + 29 wrong + 18 missing = 889` rows.
- Wrong/missing rows with non-null first/stable fields: API `0`, DOM `0`.
- Negative finite latencies: API `0`, DOM `0`.
- Requests: `160` starts, `160` ends, `160 <= 250`; peak `1 <= 2`; final active `0`.

## Environment gates

- Ports `17851`, `19251`, `18251`: free.
- GPU lease text: exact `FREE` (newline-terminated).

Failures: none. No source repair, push, merge, deploy, or peer message performed.
