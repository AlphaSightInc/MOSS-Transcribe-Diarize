# R4-10 pre-terminal harness verification result

Executed 2026-09-21 from `round4/preterm` at `71f23c0c`.

- `tests/test_preterm_rerun_harness.py`: **PASS**, 2 passed.
- `prototypes/preterm-rerun/run.py --plan-only`: **PASS**, zero decoder requests; total 56 (alternation system 15, microphone 13; overlap system 15, microphone 13).
- D27 reference readiness: **MISSING system** on this pre-fixture base; execution is therefore refused and the pre-terminal quality rows remain **UNMEASURED**.
- Full backend: **PASS**, 2,132 passed / 5 skipped / 8 xfailed / 37 subtests (JUnit: 2,182 total, 0 errors, 0 failures; 174.926 s).
- Frontend: **PASS**, 312/312; TypeScript and Vite build pass.

Falsifiers not observed: missing-layer bypass, unclassified retained-final edit, unaudited fixture substitution, or decoder dispatch during plan-only.
