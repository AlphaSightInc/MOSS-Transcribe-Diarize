# PANE 3.2 fresh-context verification attempt 1

**Verdict: FAIL**

Executed `VERIFY.md` literally from `/private/tmp/moss-round3-20260919/identity` on 2026-09-19. No product code was edited. No commit, push, merge, deploy, pane message, process change, or network-service opening was performed.

## Custody and scope

- Branch: `round3/identity` — expected.
- Tested `HEAD`: `11755eef845fd2d67ce2db578896d8295a7f36c1`.
- WP55a-P required/source revision: `a7a738cf9f9ff246f64c52c112e0bf597ba58241`.
- Initial `git status --short`: no output (clean).
- `git diff --exit-code a7a738cf9f9ff246f64c52c112e0bf597ba58241 -- moss_transcribe_diarize tests frontend`: exit 0, no output.

## Check results

### WP55a-P — FAIL

- Literal block exit: 1; wall time 2.74 s.
- Script output: `WP55a-P must run on unmodified a7a738cf`.
- Script exit: 1 (`SystemExit` with a string); expected exit 2.
- Because `test "$wp55a_status" -eq 2` failed under `set -e`, the literal block did not run its `jq` assertion.
- Read-only inspection of the existing results artifact found: `gate_verdict="FAIL"`, `selected_policy=null`, 0 qualifying policies, exact raw arm 1 production-resolver match `true`, P3 total wrong `92.01`, baseline total wrong `92.01`. These artifact values were **not revalidated by the refused run**.

### WP55b-P step 1 — PASS

- Script exit: 2, as expected; literal block exit 0.
- `jq` assertion exit 0 and output `true`.
- `gate_verdict="FAIL"`; clean snippets frozen: 0.
- Decoder requests: 0; decoder budget: `0 of gated 12 used`; network calls: 0; audio playback: 0.
- IP1 CPU ONNX: `NOT RUN`; oracle matrix: `NOT UNLOCKED`.
- Retained useful candidates: 1 of 3; two rejected for boundary spill.
- Artifact recorded pane revision `11755eef845fd2d67ce2db578896d8295a7f36c1` and source revision `a7a738cf9f9ff246f64c52c112e0bf597ba58241`.

### Backend suite — FAIL

- Exact result: **1 failed, 2036 passed, 5 skipped, 37 subtests passed**.
- Warnings: 21.
- Pytest time: 181.09 s (`0:03:01`).
- Failure: `tests/phase2/test_tls_preparation.py::test_verify_layout_current_tree`.
- Exact cause from stderr: `FAIL: VERIFY.md belongs under docs/verify/<wp>/`.
- Exit: 1.
- Additional shutdown output reported a destroyed pending Playwright task and a `TargetClosedError` future.

### Frontend suite — PASS

- Test files: 28 passed.
- Tests: **288 passed / 288**.
- Vitest duration: 2.67 s; command wall time 3.03 s.
- Exit: 0.

### Typecheck — PASS

- `tsc --noEmit`: exit 0, no diagnostics.
- Command wall time: 1.41 s.

### Build — PASS

- Vite 8.2.1: 34 modules transformed; build completed in 82 ms (command wall time 0.41 s).
- Outputs: `styles.css` 53.79 kB (10.79 kB gzip); `app.js` 131.29 kB (42.81 kB gzip), source map 411.24 kB.
- Exit: 0.

## Final worktree and process state

- Pre-report `git status --short` showed verifier-generated drift:
  - ` M evidence/round3/wp55b-p/short-speaker-results.json`
  - ` M prototypes/identity/short-speaker-results.json`
- Both diffs only changed `scope.pane_revision` from `e47b345a214207313b462b3e72aeaddee3a94dda` to `11755eef845fd2d67ce2db578896d8295a7f36c1`.
- Therefore `git diff --exit-code` returned 1: final worktree was not clean.
- Post-report `git status --short` additionally showed `?? VERIFY-RESULT.md`.
- `lsof -nP -iTCP:18312 -sTCP:LISTEN`: no output; no listener on TCP 18312.
- The literal `pgrep -af 'ssh .*127.0.0.1:18312:127.0.0.1:8000'` emitted transient PID `62711` and made the block exit 1. A repeated match emitted a different transient PID `62954`; both vanished before inspection. This was the command wrapper matching its own full argument string, not an SSH process.
- Independent exact-process check found one live `ssh` process, PID `62138`, forwarding **18311** to 8000. No `ssh` process forwarding 18312 was present. No process was stopped or modified.

## Falsifiers reached

Verification is falsified by all three independent differences:

1. WP55a-P ran at `11755eef...`, not its required `a7a738cf...`, and refused with exit 1.
2. Backend count was 2036 passed / 1 failed, not 2037 passed / 0 failed.
3. Final worktree contained two generated JSON modifications.
