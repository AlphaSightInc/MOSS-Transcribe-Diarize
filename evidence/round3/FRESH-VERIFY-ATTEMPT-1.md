# Fresh verification attempt 1

Verdict: **FAIL**, repository-layout control only.

- Source SHA: `a957f57ea41d21d4d9a5783a8d72a1bdbddab024`.
- Prototype: `SUPPORTED`; all positive and violating controls passed.
- Backend: **1 failed, 2,051 passed, 5 skipped, 37 subtests** in 181.54 s.
- Sole failure: `tests/phase2/test_tls_preparation.py::test_verify_layout_current_tree`;
  exact diagnostic: `FAIL: VERIFY.md belongs under docs/verify/<wp>/`.
- Frontend: 28 files / 288 tests passed; typecheck and build clean.
- Final reproduction/cleanliness check passed before the result file was written.

Resolution: move the verification contract/result to the required canonical directory and
rerun the failed layout control plus the entire pre-VERIFY suite before a second fresh pass.
The first targeted rerun still failed because the root path remained tracked until its
deletion was committed; no product control ran or failed. The post-commit rerun is authoritative.
