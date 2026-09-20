# FIX-3.2 full-suite gate

Post-ruling candidate based on `fa1ed99845c3bca61c0acb3da030a7e5c1bfa8ff`
on `round3/fix-identity`; only documentation/evidence changes were uncommitted.

- Backend: **2,100 passed / 0 failed / 5 skipped / 37 subtests**; 21 warnings;
  pytest 199.11 s; wall 200.22 s, user 132.28 s, sys 57.76 s.
- Frontend: **28 files / 310 tests passed**; Vitest 2.99 s.
- Typecheck: PASS.
- Build: PASS; 34 modules; Vite 115 ms.
- Post-build generated assets: no delta. Only intended docs/evidence changes remain.
