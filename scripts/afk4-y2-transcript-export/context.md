# context — y2-transcript-export

Living working memory. Update it every iteration so it matches reality. History goes in progress.txt.

## Known state (verified 2026-08-16, `dev` @ 5b20a95)

- `lib/transcriptExport.ts` exports only `formatTranscriptClockTime`, `buildTranscriptExportText`.
  Sole consumer: the Copy button at `TranscriptPane.tsx:258`. No download path, no md/txt/json.
- G8 measured against current `dev` with all four ruled exemptions
  (`evidence/phase1/r1-reference-ui/screenshot-diff-postruling-regions/report.json`):
  1440x900 = 4.47% diff / 1.76% largest region; 1280x800 = 9.27% / 3.74%. Bars: 2.0% / 1.0%. FAIL.
- Transcript panel is **95.2%** of the remaining difference at 1440x900; legend alone 23.9%.
  Control panel is down to 3.1% — it is no longer the problem.
- At 1280x800 the named regions sum to only ~78%, so some debt is layout shift between panels.
- Fixture text divergences already visible: reference legend renders `A`, candidate renders `2`;
  reference has a `Formatted` control the candidate lacks.
- Playwright is in **pyenv 3.12.12**, not `.venv`.

## Candidates (ranked; re-rank as you learn)

1. Export: one serializer with a format parameter (md/txt/json) + download affordance + tests.
   Do this first — it is a capability gap, the pixels are debt.
2. Re-run the diff with region diagnostics to get your own baseline before changing pixels.
3. Legend divergence (`A` vs `2`, chip layout) — 23.9% of the difference in one small region.
4. Whatever the 1280x800 layout shift turns out to be. Measure, do not guess.
5. Confirm the reference's transferred vitest component tests still pass.

## Hard line

The exemption set in `tests/fixtures/reference_ui_screenshot_diff.json` is a charter ruling and is
**not yours**. If a bar looks unreachable without a new exemption, escalate with the measurement.

## Not yours

`App.tsx`, `api/jobs.ts` (y1) · `state/session.ts`, `persistence.ts`, `ControlPanel.tsx` (y3)
