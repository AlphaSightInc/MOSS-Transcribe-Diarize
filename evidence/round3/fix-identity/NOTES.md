# FIX-3.2 two-lane WER diagnosis

Status: **BLOCKED — 1/4 prescribed revision×hop arms complete.**

## Structural contract

- Question: regression, proxy timing artefact, or unchanged known limitation L1?
- Primitives: revision, hop, fixed alternation/overlap input, lane-specific WER,
  pre-terminal/final/reopened surfaces, exact remote-request accounting.
- Invariants: gain 0.03; unchanged `QUALITY_BOUNDS`; direct port 18261; at most
  two requests in flight; no retries; no tuning.
- Falsifier: a direct-hop difference between `a7a738cf` and `738cdfdd` would
  require bisection across the four merge commits.

## Completed arm

`738cdfdd`, direct tunnel, both cases consumed **59/80** authorized requests.
Exact lane numerators/denominators are in `integrated-direct-summary.json`.
The result matches S16 profile A exactly. Therefore the extra counting-proxy hop
is **not necessary** to reproduce S16 and cannot alone explain it.

The local wrapper failed only after the completed measurement because it assigned
zsh's read-only `status` variable. The JSON and 59-line request receipt were
already complete; no decoder retry occurred.

## Budget blocker

Only **21/80** requests remain. One required two-case arm consumed 59, so the
three remaining arms cannot be run within authorization. The second case alone
occupied the final approximately 27 requests of the completed arm. A full matrix
projects near 236 requests; exact future use remains unknown until run.

No (a)/(b)/(c) classification is made. `docs/known-limitations-20260918.md` is
unchanged because the base revision and proxy comparisons are absent. No product
fix, threshold change, bisection, or new regression test is justified.

## Commands and custody

- Clone: `/private/tmp/moss-round3-20260919/fix-identity`, branch
  `round3/fix-identity`, base `738cdfdd`.
- Harness: `tests/e2e/verify_demo_lanes.py --base https://127.0.0.1:17861
  --allow-local-self-signed --case both`.
- Stack decoder URL: `http://127.0.0.1:18261/v1` through the owned SSH tunnel.
- Initial vLLM metrics: running 0, waiting 0.
- Tunnel and stack were stopped; ports 17861 and 18261 were clear; lease returned
  to `FREE` immediately after the blocker was established.
