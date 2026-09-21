# R4-10 S17 identity rerun receipt

## Verdict

**UNMEASURED.** `--plan-only` prepares this rerun without a decoder client, stack, GPU,
tunnel, or network call. The historical terminal row remains unmeasured until the
budgeted capture runs.

## Structural contract

- **Question.** Did S17's terminal-only span share its native terminal-local partition
  with eligible Adam evidence, or was it a distinct partition with no eligible match?
- **Minimum primitives.** The existing `single`, `gap`, and `alternating` population;
  the merged lane-second rate; product-emitted terminal partition records; and raw JSONL.
  The product creates partition ID and decision once. The receipt only groups those IDs.
- **Invariant.** Capture is opt-in and observation-only. `--plan-only` sends no request.
  During `--run`, only the stack gets `MOSS_TERMINAL_LABEL_CAPTURE`; clients explicitly
  do not inherit it. Capture may not alter a label, score, threshold, decision, or output.
- **Assumptions / unknowns.** A later run must supply an owned decoder, manifest, model,
  and at least the printed request budget. This receipt cannot know S17's old partition.
- **Falsifier.** Missing capture fields, an empty stream, a sample-floor mismatch, or
  disagreement within a product partition falsifies the receipt.
- **Tool decision.** `identity-stress/run.py` owns the audio population; the merged
  qualification planner owns the measured `0.51 requests_per_lane_second` arithmetic.

## Command

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python prototypes/s17-identity-rerun/run.py \
  --plan-only --out evidence/round4/labels2/s17-identity-plan.json
```

The budgeted command substitutes `--run --decoder-base-url <owned endpoint> --budget 184`.
It refuses before stack startup if capture, endpoint, or budget is absent, or the result
directory exists.

## Settlement boundary

The budgeted rerun settles whether the historical offending span shared a terminal-local
partition with eligible Adam evidence and what the unchanged partition decision published.
It cannot establish a repair policy. If captured partitions show the offending span was
isolated, `S00` is the correct outcome and the historical S17 row is **EXPLAINED, not
repaired**.
