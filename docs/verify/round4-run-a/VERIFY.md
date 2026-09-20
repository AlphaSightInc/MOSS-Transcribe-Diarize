# Round 4 run A — offline verification

**PASS:** the visible-word and decoder-budget instruments meet this run's offline acceptance bar. This verifies the
instruments, not product latency or 30-minute capacity: no browser, decoder, GPU, network, microphone, or audio run was
performed.

## Evidence

- **F1 — Display custody is explicit.** On base `89f833ac`, the ported two-`alpha` control failed **1/15**: an earlier
  displayed row was stretched to the playback frontier, the absent later word was credited at 1 s, and the earlier
  word was marked missing. The final control credits the earlier word at its own 11 s observation and leaves the later
  occurrence missing. Four additional documented controls cover an omitted repeated phrase, merged rendered rows,
  earlier-text revision, and unchanged text across a phrase end. Rows without a valid published span produce no DOM
  credit and report `rendered_dom: UNMEASURED`. Phrase-end completion is separate from per-word observations.
- **F2 — Row custody reaches the instrument unchanged.** Each `.utt` article publishes its merged turn's
  `data-turn-start`, `data-turn-end`, and `data-target-keys`; the frontend control asserts the values against model
  state. The iteration-2 rebuild produced 17 committed assets and a second fresh build was byte-identical **17/17**.
  Final frontend validation is **312/312 passed** and TypeScript typecheck is clean.
- **F3 — Budget admission matches the selected population.** Default mode plans 41 live sessions / 1,729 live seconds /
  11 file windows / 16 browser cases, retaining `measured_rate=0.51`, its `source_receipt`, `headroom=1.25`, and
  `planned_requests=1136`. Long mode selects 2×1,800 s and plans 3,068 requests. Bare `--long` with the 1,136 default
  budget refuses before `Bundle` with shortfall 1,932. Any observed `rejected_by_budget > 0` records accepted,
  completed, and rejected counts separately and forces budget-censored `INCOMPLETE`, never quality `FAIL`. Every
  default summary retains `capacity_2x1800: REQUIRED-NOT-RUN`.
- **F4 — Full offline suites are green.** The final backend suite reports **2,123 passed / 0 failed / 5 skipped / 37
  subtests** in 192.01 s, above the 2,116 floor. The final frontend suite reports **312/312 passed** across 28 files,
  above the 311 floor.

## Reproduce

Run from the repository root on branch `round4/ralph-a`:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
  -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
```

Expected: at least 2,116 backend passes with 0 failures and 5 skips; at least 311 frontend passes with 0 failures; clean
typecheck. Current-tree results are F4 above.

## Falsifiers

The PASS is false if any of these is reachable:

1. A reference occurrence receives DOM credit without a valid displayed row span that overlaps that occurrence, or a
   row end is reconstructed from another row or the playback frontier.
2. A wrong or missing word gains a non-null observation clock, drops from the denominator, or phrase-end timing is
   presented as per-word latency.
3. An underfunded selected population constructs `Bundle` or sends a decoder request; a budget rejection becomes a
   quality `FAIL`; accepted/completed/rejected populations are conflated; or default output omits the unrun long row.
4. The suite floors, typecheck, or 17-file generated-asset parity fail.

## Evidence boundary

The retained round-3 S9 result is history: its raw DOM observations were not retained, so it cannot be unbiasedly
rescored. Real headed word latency and the 2×1,800 s confirmation remain **UNMEASURED / REQUIRED-NOT-RUN** here.
