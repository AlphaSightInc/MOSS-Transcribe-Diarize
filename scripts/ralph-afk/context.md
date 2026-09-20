# Context - MOSS round 4, ralph run A

## Ground

- Repo: `/Users/gao/Documents/Codex/2026-09-20/moss-round4/candidate` — branch `round4/ralph-a` (base `89f833ac`; the
  lead merges this branch into `round4/integration` after the run)
- Read before editing: `AGENTS.md` (structural-primitive contract), `docs/adr/0014-documented-quality-exception-band.md`,
  `evidence/round3/fix-3.1/s9-result.md` (what the instrument reported last round and why it is not citable),
  `/Users/gao/Documents/Codex/2026-09-20/moss-current-review/assessment-and-plan.md` findings F4, F5, F6 (read-only).
- Key code paths and why they matter:
  - `tools/qualify/visible_word_headed.py` `_dom_segments` now accepts only each row's published start/end; it returns
    no segments plus a reason when a row lacks a finite positive model-state span. The collector reads all three
    `data-` custody attributes and no longer reads `.utt-time`, the next row, or the playback frontier.
  - `frontend/src/components/TranscriptPane.tsx:649-661` — the `.utt` `<article>` now publishes
    `data-turn-start`, `data-turn-end`, and `data-target-keys` directly from the merged React turn. Live segment ids are
    positional (`frontend/src/api/mossPoller.ts:598,714` `effective:${index}`) and a row is a merged, overlap-trimmed
    turn (`mergeTranscript.ts:183-199`) — the honest custody primitive is therefore the turn's own published span, not
    a per-segment id join.
  - `tools/qualify/visible_words.py:103-107` `_overlaps`, `:135` match rule, `:174-200` `evaluate_visible_word_stream`
    (interval-end gate at `:196-199` — keep). The v2 receipt retains source-interval identity and reports interval-end
    completion once per phrase under `phrase_end_diagnostics`; word rows contain observation clocks, not inferred
    per-word latency.
  - `tests/test_visible_word_instrument.py` — 20 focused controls include repeated/omitted phrases, merged rendered
    rows, revisions, unchanged content across a phrase end, and API/DOM clock separation; launch args remain exactly
    `["--mute-audio"]`.
  - `tools/qualify/run.py` `request_plan()` selects 2×300 by default or 2×1800 under `--long`, derives 1,136 / 3,068
    request budgets from the declared population, and refuses short budgets before `Bundle`. `Bundle.capacity()` runs
    exactly the selected row and retains `capacity_2x1800: REQUIRED-NOT-RUN` in every default summary.
  - `tools/qualify/test_bundle.py` — focused controls cover population arithmetic, derived default admission, long-mode
    refusal, exact runner arguments, unavailable-stack reporting, and counted proxy enforcement.
  - `moss_transcribe_diarize/app/windowed_transcription.py:164-165` — `window_seconds = 150`, `stride_seconds = 120`
    (file-window request arithmetic).

## Current state

- 2026-09-20 iteration 9: candidate 8 is complete. Final offline validation is **2,123 backend passed / 0 failed / 5
  skipped / 37 subtests**, **312/312 frontend passed**, and clean frontend typecheck. The self-contained verification
  record at `docs/verify/round4-run-a/VERIFY.md` ties the base RED, final custody controls, asset parity, budget
  admission/censorship semantics, full-suite counts, falsifiers, and evidence boundaries together. This completes the
  run's offline acceptance bar without claiming a headed latency measurement or 2×1,800 capacity qualification.
- 2026-09-20 iteration 8: candidate 7 is complete. The default population now includes the established 2×300 s
  development capacity row: **41 sessions / 1,729 live seconds / 11 file windows / 16 browser cases = 1,136 planned
  requests**. The default `--budget` is that derived value. `--long` replaces (not adds to) the capacity row with
  2×1,800 s and remains **3,068 planned requests**; bare `--long` refuses before `Bundle` with shortfall 1,932. Default
  summaries emit `capacity_2x1800: REQUIRED-NOT-RUN`, including when the stack is unavailable or execution is
  interrupted. Focused controls were RED **4/4**, then the qualification helper set was GREEN **50/50 passed**.
- 2026-09-20 iteration 7: candidate 6 is complete. The owned decoder proxy now counts accepted, completed and
  budget-rejected requests independently. Bundle cleanup records those three populations and, when any request was
  rejected by the budget, sets `budget_censored: true`, `verdict_reason: budget_censored`, and the overall verdict to
  `INCOMPLETE` even when downstream gates reported `FAIL`; censored evidence therefore cannot become a quality failure.
  The focused control was RED **2 failed / 36 passed**, then the qualification helper set was GREEN **46/46 passed**.
- 2026-09-20 iteration 6: candidate 5 established the non-capacity population. `request_plan(long)` enumerated every selected decoder-producing
  live bench as session durations: workspace, demo lanes, lifecycle, reshare, identity stress, level ladder and browser
  stress. Workspace File/URL inputs are also included in production `WindowedRunner` arithmetic. The plan now covers
  **39 sessions / 1,129 live seconds / 11 file windows / 16 browser cases = 754 default requests**; long adds
  2×1,800 s and one 1,800 s file for **41 sessions / 4,729 live seconds / 26 file windows = 3,068 requests**. Headroom
  is 1.25: the prior 1.18 still underfunded the retained default path (727 actual requests versus 602.79 unadjusted;
  observed ratio 1.206). Iteration 8 supersedes the 754 default total by adding the required 2×300 capacity row.
- 2026-09-20 iteration 5: established the pure plan and pre-`Bundle` refusal seam, but counted only capacity, extended
  files and browser case ids (**30 default / 2,214 long**). Iteration 6 superseded those incomplete totals.
- 2026-09-20 iteration 4: all four remaining custody controls are GREEN and documented by falsifier: repeated token
  with an omitted later phrase, two phrases merged into one row, earlier-text revision, and unchanged text crossing a
  phrase end. Source interval identity now survives word expansion, so the v2 receipt emits one
  `phrase_end_diagnostics` row per phrase instead of duplicating phrase-end delay as per-word latency. The headed
  collector records unchanged API/DOM content at the first poll crossing each phrase end. Focused module: **20/20
  passed**. The external historical `dom-time-repro.py` still calls the retired two-argument `_dom_segments` and now
  raises `TypeError`; the ported in-repo falsifier is the maintained control and remains GREEN.
- 2026-09-20 iteration 3: DOM custody now comes only from `data-turn-start` / `data-turn-end`; `data-target-keys` is
  read with the row but no id join is invented. A sample containing a row without a valid published span clears DOM
  observations and reports `rendered_dom` as `UNMEASURED` with the reason and denominator, with no word credit. The
  original earlier/later `alpha` falsifier is GREEN and the focused module is **16/16 passed**. Ordered one-to-one
  occurrence matching was already enforced by `_ordered_statuses`, so it was preserved rather than replaced.
- 2026-09-20 iteration 2: `.utt` rows publish the turn's model-state start/end/target keys. The dedicated frontend
  control went RED on missing attributes, then GREEN **18/18** after the three-attribute change; frontend typecheck is
  clean. Vite rebuilt the 17-file committed asset tree (only `app.js` and `app.js.map` changed), and a second fresh
  build was byte-identical to the staged assets. The Python instrument does not consume these attributes yet.
- 2026-09-20 iteration 1: ported the F4 earlier/later `alpha` counterexample to
  `tests/test_visible_word_instrument.py`. Before the test edit, `89f833ac..51d35ef1` changed only loop/orchestration
  files, so the instrument was still the unpatched base. The module now reports the expected RED: **1 failed, 14
  passed**. `_dom_segments` expands the displayed 0-1 s row to 0-12 s, leaving the earlier word `missing` and falsely
  crediting the later word at 1 s latency. Keep this test failing until row-span custody is implemented.
- 2026-09-20: Codex's offline falsifier reproduced by the lead on `89f833ac`: `dom-time-repro.py` → earlier "alpha"
  0–1 s `missing`, later "alpha" 10–11 s `correct` at 1.0 s. Retained S9 (`evidence/round3/fix-3.1/s9-headed.json`)
  cannot be recomputed unbiased (raw observations not retained) — leave it as history.
- 2026-09-20: S17 bundle on `89f833ac` exhausted `--budget 2000` at t≈1,165 s of the 2×1800 gate after earlier gates
  used 733 requests (13 rejected, 0 active at teardown, peak_in_flight 1) — third budget/population mismatch of the
  campaign. The S17 receipt is budget-censored with no per-gate attribution, so it cannot supply a rate. **Retained clean
  receipts in this repo:** `evidence/mvpfix/wp30/20260918-055122-1r-4x600/requests.jsonl` = 1,220 requests over
  4×600 s = **0.508 req/s**; `evidence/mvpfix/wp30/20260918-064644-1r-8x300/` = 1,224 over 8×300 s = **0.510** (both
  with a 0.15 s stub decoder, `evidence/mvpfix/wp30/NOTES.md:36`). Use 0.51 as `measured_rate` with that provenance and
  an explicit `headroom` (0.6/0.51 ≈ 1.18 is what past estimates implicitly used); record all three in the summary.
- 2026-09-20: `capacity_2x1800` already runs only under `--long` (`run.py:315`, `:338-342`) — the default bundle has
  **no** capacity row today. Adding a 2×300 s development row (D12 ladder) adds coverage; the 2×1800 requirement must
  stay visible as `REQUIRED-NOT-RUN`.
- 2026-09-20: `launchctl managername` in this shell is `Background`; no headed browser is run in this loop anyway.
- Baseline suites on `89f833ac`: backend 2,116 passed / 0 failed / 5 skipped / 37 subtests (~209 s); frontend 311/311.
- Established (lead + reviewer, 2026-09-20): the rendered `.utt` markup carries **no** span or id; the design is to
  publish `data-turn-start` / `data-turn-end` / `data-target-keys` on the article from the turn's own model state and
  read those in the instrument. Frontend tests live under `frontend/src/**/__tests__` or `*.test.tsx` (vitest); look at
  how `TranscriptPane` is already tested before adding one.

## Validation

```bash
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
# narrowest: the falsifier (must fail on unpatched base, pass after)
$PY -m pytest -q -p no:cacheprovider tests/test_visible_word_instrument.py
$PY -m pytest -q -p no:cacheprovider tools/qualify/test_bundle.py tools/qualify/test_speaker_quality.py
# widest checkpoint (required before claiming completion)
$PY -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run && npm --prefix frontend run typecheck
```

## Candidates

1. **DONE (iteration 1) — Port the falsifier as a failing test** (`tests/test_visible_word_instrument.py`): RED is
   recorded on the base-equivalent instrument; expected final behavior remains asserted.
2. **DONE (iteration 2) — Publish the turn span on the row** (`TranscriptPane.tsx:649-661`): the three attributes,
   model-state frontend control, clean typecheck, and deterministic 17-file Vite asset rebuild are recorded.
3. **DONE (iteration 3) — Replace `_dom_segments` custody** with row-published spans; next-start/frontier invention is
   removed, existing ordered one-to-one matching is preserved, and spanless rows make DOM `UNMEASURED` with no credit.
4. **DONE (iteration 4) — Add the remaining violating controls**: repeated word + omitted later phrase, merged rows,
   revision of earlier text, and unchanged text across phrase end are GREEN. Phrase-end completion is separately
   reported once per source interval; word rows no longer claim inferred per-word latency.
5. **DONE (iterations 5-6) — Budget preflight** in `tools/qualify/run.py`: the pure planner, summary fields, production
   file windows, browser case ids, every selected live-bench session duration, and refusal-before-`Bundle` control are
   implemented. The plan derives 754 default / 3,068 long requests; no historical request count is added as population.
6. **DONE (iteration 7) — Censored classification**: `rejected_by_budget > 0` now forces a budget-censored
   `INCOMPLETE`, never quality `FAIL`; accepted/completed/rejected counts are separate and the proxy control proves the
   completed count.
7. **DONE (iteration 8) — Capacity rows**: default runs 2×300 s with derived budget 1,136; `--long` selects 2×1800 and
   requires at least 3,068; every default summary retains `capacity_2x1800: REQUIRED-NOT-RUN` and the derivation.
8. **DONE (iteration 9) — Full suites + `docs/verify/round4-run-a/VERIFY.md`**: backend **2,123/0/5** plus 37
   subtests, frontend **312/312**, typecheck clean; the record states reproduction commands, falsifiers, and offline
   evidence boundaries.

## Non-candidates

- Any change under `moss_transcribe_diarize/` or `frontend/` beyond the three `.utt` data attributes, their test and
  the rebuilt assets — product code is owned by the parallel Codex panes and a later run; touching it here would
  collide with their merges.
- Any numeric visible-word latency bar or any change to `QUALITY_BOUNDS`, gate bars, identity constants — user
  decisions / invariants (D10, COMMON §3).
- Re-running or re-scoring the retained S9 300 s session — its raw observations were not retained; it is history.
- The 1–3 minute headed trial with a manually aligned reference — needs a browser + decoder; belongs to the round-4
  measurement pass, not this loop.
- Rewriting `docs/known-limitations-20260918.md` — lead-owned.
