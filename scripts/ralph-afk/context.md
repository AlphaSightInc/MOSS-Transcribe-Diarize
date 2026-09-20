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
    (interval-end gate at `:196-199` — keep).
  - `tests/test_visible_word_instrument.py` — existing controls `:233` repeated-word, `:253` not-before-interval-end,
    `:272` API/DOM clocks separate; `:189` launch args must be exactly `["--mute-audio"]`.
  - `tools/qualify/run.py:574` `--budget` default 2000; `:315` gate spec table (`capacity_2x1800`, 2); `:341-342` the
    2×1800 s invocation; `:117-118`, `:496-500` reactive budget accounting; `tools/qualify/decoder.py:9-82` counting
    proxy (`sent/active/peak/rejected`, `BoundedSemaphore(2)`, 429 at `:26-29`). No estimate/preflight exists.
  - `tools/qualify/test_bundle.py` — 9 tests, none about budget; `:35` proxy cap test is the closest.
  - `moss_transcribe_diarize/app/windowed_transcription.py:164-165` — `window_seconds = 150`, `stride_seconds = 120`
    (file-window request arithmetic).

## Current state

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
$PY /Users/gao/Documents/Codex/2026-09-20/moss-current-review/dom-time-repro.py | tail -40
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
4. **Add the remaining violating controls** (repeated word + omitted later phrase; merged rows; revision of earlier
   text; unchanged text across phrase end) and the separate phrase-end diagnostic key.
5. **Budget preflight** in `tools/qualify/run.py`: `planned_requests` from the gate population × `measured_rate`
   (0.51 from the wp30 receipts, provenance recorded) × `headroom`; refuse before any request when `planned > budget`;
   summary keys `measured_rate`, `source_receipt`, `headroom`, `planned_requests`; tests in `tools/qualify/test_bundle.py`.
6. **Censored classification**: `rejected_by_budget > 0` ⇒ `INCOMPLETE`, never quality `FAIL`; accepted/completed/
   rejected reported separately; test.
7. **Capacity rows**: add a default 2×300 s development row (two-meeting population); `--long` = 2×1800 with preflight
   and a required sufficient budget; every default summary emits `capacity_2x1800: REQUIRED-NOT-RUN`; raise the default
   `--budget` to what the preflight derives for the default population and show the derivation; test.
8. **Full suites + `docs/verify/round4-run-a/VERIFY.md`** (what to run, expected counts, what would falsify).

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
