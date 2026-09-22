# I4b fresh-context verification result

## Recorded controls

- RED, lead-shaped local stack + Chromium + P2 stub: row 5 PASS, row 10
  `Error` after 0.183 s, then row 8 blocked. The separate prototype retained
  the raw message in `NOTES.md`.
- GREEN, same launcher shape: row 5 PASS; row 10 made one non-throwing
  `bank_missing_name` attempt in 31.641 s; row 8 PASS and identified that
  row-10 meeting. The P2 proxy completed 115/115 loopback requests; real
  decoder/provider/GPU requests were 0.
- The real-Chromium media-source regression test passed.
- Full backend plus bundle self-tests passed: `2361 passed, 5 skipped,
  2 xfailed, 37 subtests passed in 257.80s`.
- Fresh-context verification on this branch passed: the AST check found the
  reopen in `_fresh_row10_context`, and its isolated focused suite passed
  `59 passed in 40.43s`; `git diff --check` and worktree status were clean.

The loopback run proves browser/harness control flow only. It does not measure
real decoder recognition, latency, or audio quality.
