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

## Lead-issued fresh-context rerun — 2026-09-21

**PASS** from clean branch `round4/impl-i2` at
`d6c9979e4f3e2097aa77746f2b7838c8dc2b2e30` in the specified clone
`/private/tmp/moss-round4-20260920/impl-i2`.

- Checkout/status: PASS; correct branch and clean initial tree.
- Offline frontend install: PASS; 157 packages added, 158 audited, 0
  vulnerabilities.
- Import custody: PASS; resolved to
  `/private/tmp/moss-round4-20260920/impl-i2/moss_transcribe_diarize/__init__.py`.
- Focused controls: PASS; 144 passed / 0 failed / 19 subtests; 4 warnings.
- S17 plan-only: PASS; `capture.status=READY`; 3 raw/derived streams; 184 planned;
  0 executed/spent.
- Backend: PASS; 2,181 passed / 0 failed / 5 skipped / 2 xfailed / 37 subtests;
  21 warnings.
- Frontend: PASS; 28 files passed; 312/312 tests passed.
- TypeScript: PASS; `tsc --noEmit` exited 0.
- Vite build: PASS; 34 modules transformed; build exited 0.
- Generated assets: PASS; no diff after build.
- Identity files: PASS; byte-identical to `0de56e1a`.
- Product diff: PASS; exactly `live_lane_decode.py`,
  `live_transcript_convergence.py`, `phase2_file.py`,
  `terminal_label_capture.py`, and `windowed_transcription.py`.
- Final status: PASS; clean `round4/impl-i2` tree before this result append.
- Decoder/provider/network/tunnel calls: 0/0/0/0.

Verdict: **PASS**. S17 remains **UNMEASURED**; only its request plan was verified.
