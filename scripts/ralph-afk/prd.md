# PRD - MOSS round 4, ralph run A2: close the acceptance review's blocking gaps

Run A (iterations 1–9, HEAD `3a56ce7b`) removed the invented-span path and built the budget preflight. An adversarial
acceptance review then found that the custody repair is **half done** and that the request rate has the wrong unit.
This run closes exactly those gaps. Everything run A already achieved must stay achieved.

## Goal

> Make DOM word custody as fine-grained as the model state actually is — a rendered row is a *merged turn* that can
> cover many segments and many minutes, so crediting a reference word anywhere inside the row's outer span still lets
> an earlier occurrence pay for a later one that was never displayed. Custody must be per constituent segment. And make
> the decoder request rate reproduce from the receipt it cites, in the unit the planner multiplies.

## Acceptance bar

The loop is complete only when every point below holds, with evidence (commands, exact counts, before/after) recorded in
progress.txt:

- **B1 — segment-granular custody.** A violating control exists, is shown to FAIL on the current HEAD `3a56ce7b`
  (record the failing run), and passes at the end: **one** rendered `.utt` row whose published outer span is 0–11 s and
  whose constituent model segments are 0–1 s ("alpha") and 10–11 s (a different, later phrase that was never emitted),
  with references "alpha"@0–1 and "alpha"@10–11 — the later reference must be `missing` and the earlier one credited at
  its own observation time. Equivalent controls for: a single-speaker clip whose whole transcript merges into one turn
  (custody must still be per segment); and a turn whose segments are separated by a long gap.
- **B2 — the row publishes its constituent segments' model state.** `frontend/src/components/TranscriptPane.tsx`
  publishes, for each `.utt` article, the per-segment spans and texts that the turn was merged from (the merge site is
  `frontend/src/lib/mergeTranscript.ts:183-199`, which already pushes `target_segment_keys`; carry the same per-segment
  `start`/`end`/`text` through the turn and render them in one additional data attribute). A frontend test asserts the
  published value equals the model state for a two-segment merged turn. `npm --prefix frontend run typecheck` clean,
  `npm --prefix frontend run build` run and the committed `frontend_assets` byte-identical to a fresh build (17/17).
- **B3 — the instrument consumes it.** `tools/qualify/visible_word_headed.py::_dom_segments` emits one
  `TranscriptSegment` per **constituent segment** (span + that segment's text), never one per row; a row that publishes
  no usable per-segment state produces no DOM credit and the DOM result stays `UNMEASURED` with a reason. No credit path
  may use the row's outer span alone.
- **B4 — request rate reproduces.** `tools/qualify/run.py`'s `measured_rate` is stated **in the unit the planner
  multiplies** and is reproducible from its `source_receipt` by an arithmetic the summary prints. Verified facts:
  `evidence/mvpfix/wp30/20260918-055122-1r-4x600/requests.jsonl` has **2,440 lines = 2,440 unique request ids** over
  **4 sessions × 2 lanes × 600 s** ⇒ **0.508 requests per lane-second** (= 1.017 per session-second);
  `…/20260918-064644-1r-8x300/` has **2,448** over **8 × 2 × 300 s** ⇒ **0.510 per lane-second**. The current code
  multiplies session-seconds by 0.51, which under-counts any two-lane family by 2×. Fix by planning in **lane-seconds**:
  every live family in the population declares its lanes per session, and `planned_requests` uses
  `sessions × lanes × seconds × rate × headroom`. A test recomputes the rate from the receipt file and asserts the
  constant matches it. The summary records the unit explicitly (e.g. `"measured_rate_unit": "requests_per_lane_second"`).
- **B5 — the plan is not silently wrong for the default bundle.** After the unit fix, print and record the new
  `planned_requests` for default and `--long`, set the default `--budget` to the value the preflight derives (show the
  derivation), and keep `--long` refusing when unfunded. A control asserts that a family whose probe drives two lanes
  (e.g. the level ladder, `tools/qualify/run.py:30` `CASES` fed at `:452`) is planned with lanes=2.
- **B6 — headroom provenance.** `REQUEST_HEADROOM` carries the same treatment as the rate: a named source and the
  arithmetic that justifies it, recorded in the summary; if no receipt justifies a value, say so in the summary rather
  than presenting it as measured.
- **B7 — file scope.** `prototypes/capacity-campaign/NOTES.md` was edited by run A outside the permitted set; either
  move that content under `docs/verify/round4-run-a/` or state in progress.txt why it belongs there. No other file
  outside the permitted set is touched by this run.
- Everything run A achieved still holds: the frontier/neighbour-row invention stays deleted; wrong/missing words keep
  `null` clocks and stay in the denominator; phrase-end diagnostics stay under their own key and are never presented as
  per-word latency; the preflight still refuses before any request; `rejected_by_budget > 0` ⇒ `INCOMPLETE`;
  `capacity_2x1800: REQUIRED-NOT-RUN` still appears in every default summary.
- Full backend suite ≥ 2,123 passed / 0 failed / 5 skipped and frontend ≥ 312/312; typecheck clean;
  `docs/verify/round4-run-a/VERIFY.md` updated so its falsifier list states the **segment-granular** claim (the current
  wording only claims the frontier path is gone, which is why the review's counterexample slipped through).

## Constraints

Non-negotiable, in addition to the rules in prompt.md:

- Python `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`,
  always `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.`, cwd = this repo; frontend via the symlinked `frontend/node_modules`.
- No GPU, no decoder, no tunnel, no network, no microphone, no audio, no headed browser in this loop. Offline only.
- Product code you may touch: **only** `frontend/src/components/TranscriptPane.tsx`, `frontend/src/lib/mergeTranscript.ts`
  (and the types it needs), their tests, and the rebuilt `frontend_assets`. Nothing under `moss_transcribe_diarize/`
  except the regenerated assets. Never `QUALITY_BOUNDS`, any gate bar, identity constants, or
  `docs/known-limitations-20260918.md`. Otherwise: `tools/qualify/`, `tests/`, `docs/verify/round4-run-a/`.
- Do not weaken or delete any control run A added. Do not invent a numeric latency or quality bar.
- Never read or print `~/.config/moss/openrouter.env` or any `OPENROUTER_API_KEY`.
- Never `git push`; never merge or rebase; commit only on branch `round4/ralph-a`.
- If publishing per-segment state honestly is impossible without a larger product change, record exactly what is missing
  in progress.txt and context.md and stop that candidate — do not narrow the falsifier to fit what the markup allows.

## Budget and stop

- The launcher argument sets the iteration budget; one logical change per iteration.
- Stop early only via the completion contract: acceptance bar met with evidence, or every remaining item blocked on
  input the loop cannot obtain, recorded in progress.txt.
- A blocker ends the iteration, not the loop: record it, commit anything useful, and let the next iteration attack it.
