# I2 implementation evidence

- Base: `round4/integration` at `2fa9dfda`; product diff from frozen `0de56e1a` was empty.
- Baseline RED: `pytest --runxfail` over P2/P-F4 strict controls produced exactly 4/4
  failures: contained raw `S02`, passive observer, runner API, plain checkpoint caller.
- Focused GREEN: 141 passed across capture, lanes, convergence, windowing, retained
  claims, both gap branches, and P2/P-F4 controls; later final targeted set: 64 passed.
- Backend attempt 1: 2,176 passed / 5 skipped / 2 xfailed / 37 subtests / 2 failed.
  Both failures exposed a protocol-only identity-preparer assumption. After the narrow
  fix, its 61-case regression population passed.
- Backend attempt 2: 2,178 passed / 5 skipped / 2 xfailed / 37 subtests / 0 failed.
  Final fresh-clone count is recorded in `docs/verify/impl-i2/VERIFY-RESULT.md`.
- Frontend: 312/312; TypeScript clean; Vite clean and generated assets unchanged.
- S17 plan-only: `s17-plan.json` reports `READY`, raw/mapping/normalized streams, 184
  planned requests. Requests spent: 0. Decoder/provider/network/tunnel: 0/0/0/0.
- S17 remains **UNMEASURED** until its separately authorized budgeted rerun. An isolated
  raw partition means `S00` is explained and correct, not repaired.
