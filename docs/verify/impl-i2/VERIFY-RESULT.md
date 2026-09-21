# I2 fresh-clone verification result

**PASS** on implementation commit `0cd80ad49da28f4ddbf3f35f37a0f3f9251d838f`.

- Fresh clone: `/private/tmp/moss-round4-20260920/impl-i2-verify`.
- Import resolved inside that clone.
- Focused controls: 144 passed / 0 failed / 19 subtests.
- S17 plan-only: `READY`; raw span, raw-to-normalized, and normalized partition
  streams present; 184 planned; 0 spent.
- Backend: 2,181 passed / 0 failed / 5 skipped / 2 xfailed / 37 subtests.
  The two xfails are the unchanged Jamie strict controls.
- Frontend: 312/312; TypeScript clean; Vite clean.
- Generated frontend assets unchanged after build.
- Identity constant files byte-identical to frozen `0de56e1a`.
- Product diff contains only the five I2-owned files named in `VERIFY.md`.
- Fresh-clone tree clean after verification.
- Decoder/provider/network/tunnel calls: 0/0/0/0.

S17 remains **UNMEASURED** pending its separately authorized 184-request rerun. The
implementation makes an isolated raw partition explain `S00`; it does not force an
identity or claim a repair.
