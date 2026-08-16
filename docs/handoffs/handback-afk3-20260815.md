# AFK3 handback - 2026-08-15

## Landed on `dev`

Primary AFK3 reconciliation is complete. All six branch tips are ancestors of `dev`, merged in the required order:

- x4 journal mode: `22c831b`
- x5 auth residual: `29e1fd9`
- x1 frame drop: `4e5c3cd`
- x2 capture client: `4a060ae`
- x3 capture health: `3f3eb25`
- x6 terminal visibility: `159752f`

Important reconciliation and follow-on commits:

- `808a5d6` reconciles terminal capture semantics, including distinct clean `stopped` presentation.
- `4928137` and branch-local cleanup commits remove the unrelated AFK2 telemetry files.
- `ec7cdcb` connects the browser capture controls and UI port.
- `8b009ad` closes final live-capture gaps found before the stop order.
- `d3cd43f` reconciles terminal reads and queued audio.
- `1db447c` bounds capture shutdown and canonical admission.

No push, `main` mutation, issue closure, deployment, or host repair was performed.

## Weighted-admission semantics (`1db447c`)

- Canonical queue depth is decode-span weight, not envelope count. A multi-span frame reserves one weight per eventual canonical decode.
- Runtime admission counts queued weight plus remaining in-flight span weight.
- V2 frame analysis is staged before session mutation. If predicted span weight does not fit, admission returns retryable backpressure without advancing the mono session; an identical retry reuses the staged observation.
- Stop previews final-tail span weight and waits within its deadline for the same total-capacity invariant before freezing the tail.
- Batched spans still execute sequentially, but remaining spans stay counted until processed.
- Browser Stop aborts an already-running heartbeat, bounds frame/final-heartbeat/Stop requests, attempts server Stop after a frame deadline, and closes local media in `finally`.
- The committed production bundle and source were rebuilt together.

## Acceptance evidence

From repository root:

```text
.venv/bin/python -m pytest -p no:randomly
2 failed, 1063 passed, 2 skipped, 4 warnings; 1067 collected
```

The only failures were the documented baselines:

- `l15_product_tree_drift` against `9089b33210401111865da7abc160ab0bcb4aa266`
- archived L2 ingest expected 92 units but found 55

The six macOS tracer tests were included and passed in that full run. A direct reconciliation run also passed `6/6`; the operator separately observed six `swift build` failures while the host was degraded, so this remains environment-sensitive rather than resolved.

Frontend:

- typecheck: pass
- Vitest: 99/99 pass
- production build: pass (`app.js` 68.74 kB, gzip 23.04 kB)

## Deliberately open

- Do not chase the degraded host: reboot remains the operator's decision. DNS, identity services, code signing, Chrome/G7, and intermittent Python startup remain outside this work.
- G7 must be repeated only after the host and Chrome are healthy; no Chrome repair or reinstall was attempted.
- The two Python baseline failures were not weakened or edited.
- The two AFK guardrail defects in the incoming handoff remain report-only.
- No post-`1db447c` adversarial-review round was run, per stop order. New review findings belong in follow-up work, not this cycle.
- A frame or Stop tail whose predicted span weight alone exceeds `max_queue_depth` cannot be admitted. Before the next stage, a human should decide whether deployment configuration must enforce a minimum queue depth derived from endpoint/frame geometry, or whether retry/timeout is the intended product policy.
- The one-second browser terminal-request bound is now explicit policy. Change it only through a deliberate product/operations decision.

## Human gates before next stage

1. Reboot and recheck host identity/trust/DNS, then rerun macOS tracer and Chrome/G7 evidence.
2. Decide the minimum canonical queue-depth policy for worst-case multi-span frames and Stop tails.
3. Decide whether to update/restore the L15 product pin and archived 92-unit L2 corpus baseline.
4. Open any desired post-commit review as a new bounded follow-up; do not reopen AFK3 reconciliation.
