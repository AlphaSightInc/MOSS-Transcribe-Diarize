# Fix I2 verification result

PASS on branch `round4/fix-i2` from base `85aec978`.

- Backend: 2,205 passed, 0 failed, 5 skipped, 2 xfailed, 37 subtests; 216.49 s.
- Frontend: 312/312 passed; TypeScript and Vite build clean.
- Focused I2 controls: 12/12 passed, including the two unchanged review assertions.
- S17 plan-only: 184 planned requests; decoder/provider/network/tunnel calls 0/0/0/0.
- Product diff: only `live_lane_decode.py`, `live_transcript_convergence.py`, and
  `terminal_label_capture.py`; prohibited F1/F2 files unchanged.
- Capture remains passive: off/on/writer-refusal proposal-byte equality passed;
  terminal capture contains no preparer import.
- Secret search and `git diff --check`: clean.

One non-gate focused invocation collected `test_live_lane_decode.py` without the
full suite's `tests/phase2` import path: 113 passed and 2 collection-order import
failures. The mandated full backend population subsequently passed all 2,205 tests.
