# FIX-3.2 pre-ruling fresh-context verification result

**Verification: FAIL — 16 command-level checks passed, 1 failed.**

The retained work outcome remains `BLOCKED_INCOMPLETE_MATRIX`. This verification
does not classify (a), (b), or (c). The sole verification failure is the stopped
resource boundary: the GPU lease is held, not `FREE`.

## Exact results

### 1. Custody and scope — 4 passed, 0 failed

- Branch: `round3/fix-identity` — pass.
- HEAD: `fa1ed99845c3bca61c0acb3da030a7e5c1bfa8ff` — command passed.
- Initial `git status --short`: no output — pass.
- Diff from `738cdfdde092b8ba9341179fb1d33e1c34cbd24c` across
  `moss_transcribe_diarize`, `tests`, `frontend`, and
  `docs/known-limitations-20260918.md`: no diff, exit 0 — pass.

### 2. Retained receipt and non-conclusion — 2 passed, 0 failed

- Receipt predicate: `true`, exit 0 — pass. Exact retained values:
  `revision=738cdfdde092b8ba9341179fb1d33e1c34cbd24c`,
  `hop=direct_tunnel_127.0.0.1_18261`, `remote_requests=59`,
  `request_budget=80`; pre-terminal errors are alternation system `16`,
  alternation microphone `11`, overlap system `24`, overlap microphone `6`;
  verdict `BLOCKED_INCOMPLETE_MATRIX`.
- Notes match — pass: line 33 says `No (a)/(b)/(c) classification is made.`;
  line 34 says the known-limitations document is `unchanged because` the base
  revision and proxy comparisons are absent.

### 3. Lane controls and suites — 5 passed, 0 failed

- Lane controls: **10 passed, 0 failed** in 0.63 s — pass.
- Backend: **2,100 passed, 5 skipped, 37 subtests passed, 0 failed**;
  21 warnings in 197.94 s — pass.
- Frontend: **310 passed, 0 failed** across 28 passed test files in 3.00 s — pass.
- Typecheck: exit 0 — pass.
- Build: exit 0; 34 modules transformed — pass.

### 4. Stopped resource boundary — 5 passed, 1 failed

- GPU lease first line expected `FREE`; actual:
  `HELD by PANE-3.3 since 2026-09-20T01:25:02Z; port 18271; budget 400 requests`
  — **fail**.
- No TCP listener on port 17861 — pass.
- No TCP listener on port 18261 — pass.
- No matching SSH tunnel process for
  `127.0.0.1:18261:127.0.0.1:8000` — pass.
- Final pre-report `git status --short`: no output — pass.
- Final pre-report `git diff --exit-code`: no diff, exit 0 — pass.

No tunnel was opened, lease acquired, decoder called, product code edited,
diagnosis changed, commit created, push/merge/deploy performed, or peer messaged.
