# R4 summary-only feature row

**Verdict: implemented.** The duplicate all-feature campaign is removed. The
launcher now composes the existing qualification proxy and isolated stack around
the distinct summaries measurement: one 50-second File
Meeting (one 150-second window), one 180-second File Meeting (two windows), then
reuse of those two transcripts for three provider trials each.

## Structural contract

- **Question:** can the distinct summary evidence be measured once without paying
  again for surfaces already covered by the merged qualification bundle?
- **Minimum primitives:** production window geometry, two reusable Meetings, six
  provider attempts, and decoder-proxy snapshots immediately around the row.
- **Invariants:** planned decoder `3`; provider `6`; cumulative provider `8/10`;
  accepted/completed/rejected delta `3/3/0`; peak in flight at most `2`.
- **Assumption:** the caller owns the upstream decoder tunnel and exports the
  provider key; the launcher opens neither.
- **Falsifier:** any counter mismatch, peak above two, missing provider attempt, or
  provider allocation above ten makes the row `INCOMPLETE`.
- **Tool decision:** `tools.qualify.run.request_plan(False)` supplies the merged
  planner's window/stride geometry; the proxy JSONL supplies row-owned numeric
  counters. No copied request estimate or delegated prose is accepted.

Plan only, with no decoder/provider call:

```sh
python prototypes/feature-rows/launch.py --plan-only \
  --frozen-sha "$FROZEN_SHA" --out /tmp/summary-plan.json
```

Execution uses `launch.py --run` with both `--allow-*` gates and an already-exported
`OPENROUTER_API_KEY`. It reuses `tools.qualify.run` for the counted proxy, stack
command, bootstrap-before-descriptor readiness, and process-group teardown. It never
sources a credential file or puts the key in argv or receipts. Its verifier uploads
each clip once, then runs `2 × 3` provider attempts against the resulting Meetings.
The main bundle remains separate and keeps
`capacity_2x1800: REQUIRED-NOT-RUN`.
