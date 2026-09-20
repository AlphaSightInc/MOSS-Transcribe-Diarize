# Round 4 run A2 — offline verification

**PASS:** the visible-word and decoder-budget instruments meet this run's offline acceptance bar. This verifies the
instruments, not product latency or 30-minute capacity: no browser, decoder, GPU, network, microphone, or audio run was
performed.

## Evidence

- **F1 — Display custody is constituent-segment granular.** On reviewed HEAD `3a56ce7b`, the required violating
  control failed **1 failed / 20 passed**. One rendered row published an outer 0–11 s span but represented two model
  segments: 0–1 s containing `alpha`, then 10–11 s containing a different phrase. Against references `alpha` at both
  spans, the old collector marked the earlier occurrence `missing/null` and falsely credited the absent later one at
  12 s. The final control credits only the earlier occurrence at its 12 s observation and leaves the later occurrence
  `missing/null`. Final focused validation is **23/23 passed**, including added whole-transcript and 120-second-gap
  shapes. Four inherited controls — omitted repeated phrase, two phrases in one row, earlier-text revision, and
  unchanged text crossing a phrase end — document preserved behavior; they are not claimed as base-RED falsifiers.
- **F2 — Exact model state reaches the instrument.** Each `.utt` article publishes its merged turn's ordered
  constituent `start` / `end` / `text` state as `data-segments`. The frontend control asserts the exact two-segment
  JSON copied from model state. `_dom_segments` emits one `TranscriptSegment` per valid constituent and never uses the
  row's outer span or merged text for credit. Missing, malformed, empty, or unusable constituent state produces no DOM
  credit and reports `rendered_dom: UNMEASURED`. The rebuild produced 17 committed assets and a second fresh build was
  byte-identical **17/17**.
- **F3 — Budget admission uses receipt-reproducible lane-seconds.** The retained receipts independently yield
  2,440 / (4 sessions × 2 lanes × 600 s) = **0.5083** and 2,448 / (8 × 2 × 300) = **0.5100** requests per lane-second;
  the planner uses the two-decimal rate `0.51 requests_per_lane_second`. Default mode has 3,457 lane-seconds, 11 file
  windows, and 16 browser cases, so `ceil((3457 × 0.51 + 11 + 16) × 1.25) = 2,238` requests. Long mode has 9,457
  lane-seconds and plans 6,082. `REQUEST_HEADROOM=1.25` is explicitly `UNMEASURED` planner policy with no claimed
  receipt-derived arithmetic. Bare `--long` with the 2,238 default budget refuses before `Bundle` with shortfall
  3,844. Any observed `rejected_by_budget > 0` records accepted, completed, and rejected counts separately and forces
  budget-censored `INCOMPLETE`, never quality `FAIL`. Every default summary retains
  `capacity_2x1800: REQUIRED-NOT-RUN`.
- **F4 — Full offline suites are green.** The final backend suite reports **2,126 passed / 0 failed / 5 skipped / 37
  subtests** in 182.75 s, above the 2,123 floor. The final frontend suite reports **312/312 passed** across 28 files;
  TypeScript typecheck is clean.

## Reproduce

Run from the repository root on branch `round4/ralph-a`:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
  -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
```

Expected: at least 2,123 backend passes with 0 failures and 5 skips; 312/312 frontend passes; clean typecheck.
Current-tree results are F4 above.

## Falsifiers

The PASS is false if any of these is reachable:

1. A reference occurrence receives DOM credit from a rendered row's outer span rather than a constituent segment's
   published span and text; unusable constituent state earns credit; or ordered constituent state changes in transit.
2. A wrong or missing word gains a non-null observation clock, drops from the denominator, or phrase-end timing is
   presented as per-word latency.
3. The retained request receipts do not reproduce `0.51 requests_per_lane_second`; a live family loses its lane
   multiplier; unmeasured headroom is presented as receipt-measured; an underfunded population constructs `Bundle` or
   sends a request; a budget rejection becomes quality `FAIL`; or default output omits the unrun long row.
4. The suite floors, typecheck, or 17-file generated-asset parity fail.

## Evidence boundary

The retained round-3 S9 result is history: its raw DOM observations were not retained, so it cannot be unbiasedly
rescored. Real headed word latency and the 2×1,800 s confirmation remain **UNMEASURED / REQUIRED-NOT-RUN** here.
