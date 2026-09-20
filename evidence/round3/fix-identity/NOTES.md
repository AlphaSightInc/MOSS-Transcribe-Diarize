# FIX-3.2 two-lane WER diagnosis

Status: **COMPLETE — classification (c), unchanged known limitation L1.**

## Structural contract

- Question: regression, proxy timing artefact, or unchanged known limitation L1?
- Primitives: revision, hop, fixed alternation/overlap input, lane-specific WER,
  pre-terminal/final/reopened surfaces, exact remote-request accounting.
- Invariants: gain 0.03; unchanged `QUALITY_BOUNDS`; direct port 18261; at most
  two requests in flight; no retries; no tuning.
- Falsifier: a direct-hop difference between `a7a738cf` and `738cdfdd` would
  require bisection across the four merge commits.

## Completed direct arms

The lead narrowed the remaining work to one base-direct arm and raised the total
budget to 150. `738cdfdd` and fresh detached `a7a738cf`, each direct tunnel with
no proxy, consumed **59 requests each: 118/150 total**. Their exact numerators
are identical:

- Alternation pre-terminal: system **16/106**, microphone **11/53**; final:
  system **9/106**, microphone **5/53**.
- Overlap pre-terminal: system **24/106**, microphone **6/53**; final: system
  **13/106**, microphone **5/53**.

Both revisions reproduce S16 profile A exactly. The extra counting-proxy hop is
not necessary for the miss, and the round-3 merges did not change these direct
results. Classification is **(c), unchanged known limitation L1**. No bisection,
product fix, threshold change, or proxy arm is required.

The local wrapper failed only after the completed measurement because it assigned
zsh's read-only `status` variable. The JSON and 59-line request receipt were
already complete; no decoder retry occurred.

## Test boundary

This diagnosis changes documentation and evidence only. The existing production-
seam lane tests contain healthy and rejecting controls and pass 10/10. A new
red-on-`a7a738cf` regression test is inapplicable: the measured base behavior is
identical, so there is no defect fixed by this pass for such a test to distinguish.

## Commands and custody

- Integrated clone: `/private/tmp/moss-round3-20260919/fix-identity`, branch
  `round3/fix-identity`, base `738cdfdd`. Base clone:
  `/private/tmp/moss-round3-20260919/fix-identity-a7`, detached `a7a738cf`.
- Harness: `tests/e2e/verify_demo_lanes.py --base https://127.0.0.1:17861
  --allow-local-self-signed --case both`.
- Stack decoder URL: `http://127.0.0.1:18261/v1` through the owned SSH tunnel.
- Initial vLLM metrics: running 0, waiting 0.
- Tunnel and stack were stopped; ports 17861 and 18261 were clear; lease returned
  to `FREE`. Raw retained output stays outside Git; counts-only summaries are
  `integrated-direct-summary.json`, `base-direct-summary.json`, and
  `comparison-summary.json`.
