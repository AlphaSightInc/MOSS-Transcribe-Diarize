# PRD - MOSS round 4, ralph run A: trustworthy qualification instruments

## Goal

> Make the two qualification instruments that round 3 proved untrustworthy tell the truth: the headed visible-word
> instrument must credit a reference word only through a displayed occurrence that genuinely covers it, and the formal
> qualification bundle must refuse to start a population its decoder budget cannot fund and must never label budget
> exhaustion as a quality failure. The only product change permitted is publishing the transcript turn's model-state
> span on the rendered row (three `data-` attributes) so the instrument can read custody instead of reconstructing it.

## Acceptance bar

The loop is complete only when every point below holds, with evidence
(commands run, artifacts inspected, before/after deltas) recorded in
progress.txt:

- A test ported from `/Users/gao/Documents/Codex/2026-09-20/moss-current-review/dom-time-repro.py` (earlier displayed
  "alpha" at 0–1 s, later reference "alpha" at 10–11 s never displayed) exists under `tests/`, is shown to FAIL on the
  unpatched base `89f833ac` (record the run), and PASSES on the final tree: the later occurrence is `missing`, the earlier
  occurrence is credited with its own delay, and no reference word is credited by a displayed row whose end was invented
  from a neighbouring row or the playback frontier.
- Additional violating controls exist and pass: repeated words with an omitted later phrase; two reference phrases merged
  into one displayed row; a revision that changes earlier displayed text; unchanged text across a phrase end. Each is
  documented in its docstring with what it falsifies.
- The `.utt` article in `frontend/src/components/TranscriptPane.tsx` publishes `data-turn-start`, `data-turn-end` and
  `data-target-keys` (the turn's own `start`, `end`, `target_segment_keys.join("|")` from `lib/mergeTranscript.ts`);
  a frontend test asserts the attributes equal the turn's model state; vite is rebuilt and the committed
  `moss_transcribe_diarize/app/frontend_assets/*` are byte-identical to a fresh build (asset parity, 17/17); frontend
  typecheck clean.
- `tools/qualify/visible_word_headed.py` no longer derives a displayed row's source span from the next row's start or
  the playback frontier; custody is read from those row attributes; a DOM sample whose rows lack spans produces **no**
  DOM credit and the DOM result is reported `UNMEASURED` with the reason. Phrase-end diagnostics are reported under a
  separate summary key, never as per-word latency. Wrong and missing words keep `null` clocks and stay in the denominator.
- `tools/qualify/run.py` computes `planned_requests` from the actual gate population (live sessions × seconds ×
  `measured_rate`, file windows from `WindowedRunner.window_seconds`/`stride_seconds`, browser cases from their case
  list) with an explicit `headroom`; the summary records `measured_rate`, `source_receipt` (the retained
  `evidence/mvpfix/wp30/…` receipt it was derived from), `headroom` and `planned_requests`; the bundle **refuses to
  start** when `planned_requests > --budget`, printing the shortfall. A test proves refusal happens before any decoder
  request is sent.
- A run whose proxy counter reports `rejected_by_budget > 0` is classified `INCOMPLETE` (budget-censored) in the
  summary, never a quality `FAIL`; accepted, completed and rejected requests are reported separately. A test proves it.
- The default bundle gains a two-live-sessions × 300 s development capacity row (two-meeting population); `--long`
  selects the 2×1800 s confirmation and requires a sufficient `--budget` (preflight applies). Every default summary
  emits `capacity_2x1800: REQUIRED-NOT-RUN` — the long requirement may never silently disappear. The default `--budget`
  is set so the default population is fundable under the preflight, and the summary shows the derivation.
- Full backend suite `python -m pytest -q -p no:cacheprovider tests` ≥ 2,116 passed / 0 failed / 5 skipped and frontend
  `npm --prefix frontend test -- --run` ≥ 311/311 on the final tree, counts recorded in progress.txt.

## Constraints

Non-negotiable, in addition to the rules in prompt.md:

- Python: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`,
  always with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.` and cwd = this repo. Frontend uses the symlinked
  `frontend/node_modules` (never `npm install`).
- No GPU, no remote decoder, no tunnel, no network, no microphone, no audio playback, no headed browser run in this
  loop. Offline controls only; the headed trial belongs to a later measurement pass.
- Product code you may touch: **only** the `.utt` article markup in `frontend/src/components/TranscriptPane.tsx`
  (adding the three data attributes), one frontend test, and the rebuilt `frontend_assets`. Nothing else under
  `moss_transcribe_diarize/` or `frontend/`; never `QUALITY_BOUNDS`, any gate bar, identity constants, or
  `docs/known-limitations-20260918.md`. Otherwise instrument and bundle code only: `tools/qualify/`,
  `tests/test_visible_word_instrument.py`, new tests under `tests/`, `docs/verify/round4-run-a/`.
- Never invent a numeric latency or quality bar; never lower a bar to make a row pass.
- Never `git push`; never merge or rebase; commit only on branch `round4/ralph-a`.
- Never read, copy or print `~/.config/moss/openrouter.env` or any `OPENROUTER_API_KEY`; this run needs no credential.
  Never write files under `tools/qualify/out/`, `playwright-report/`, `test-results/` into git (they are ignored).
- Historical evidence files under `evidence/` are read-only history; never rewrite or reinterpret them.
- If the custody design requires data the UI/API does not expose, record exactly what is missing in progress.txt and
  context.md and stop that candidate — do not fall back to reconstructing spans from clock text.

## Budget and stop

- The launcher argument sets the iteration budget; one logical change per
  iteration.
- Stop early only via the completion contract: acceptance bar met with
  evidence, or every remaining item blocked on input the loop cannot obtain,
  recorded in progress.txt.
- A blocker ends the iteration, not the loop: record it, commit anything
  useful, and let the next iteration attack it or route around it.
