# PRD — y2-transcript-export

## Goal

**Ship live transcript export to file (md, txt, json) — internal roadmap issue 9, currently
unimplemented — and pay down the transcript pane's measured fidelity debt, which is now 95% of
everything failing gate G8.**

Two related jobs in one pane. Do them in this order.

### 1. Export (the capability gap)

`frontend/src/lib/transcriptExport.ts` exports exactly two functions —
`formatTranscriptClockTime` and `buildTranscriptExportText` — and its only consumer is the
**Copy** button at `TranscriptPane.tsx:258`. There is no download path and no md/txt/json
serializer.

**Bar:** the user can export the current transcript as **markdown, plain text, and json**, each
downloading as a file. Speaker ids, timestamps and provisional-tail handling must match what is
rendered. The json form must round-trip: re-reading it reproduces the same rendered turns.

Reuse `buildTranscriptExportText` where it already does the right thing rather than writing a
third formatter. One serializer with a format parameter beats three near-copies.

### 2. Transcript-pane fidelity (gate G8)

Measured 2026-08-16 against current `dev` with all four charter-ruled exemptions applied
(`evidence/phase1/r1-reference-ui/screenshot-diff-postruling-regions/report.json`):

| viewport | total diff | bar | transcript panel's share |
|---|---|---|---|
| 1440×900 | 4.47 % | 2.0 % | **95.2 %** (legend alone 23.9 %) |
| 1280×800 | 9.27 % | 2.0 % | 59.9 % (legend 13.3 %) |

Largest 4-connected region is 1.76 % / 3.74 % against a 1.0 % bar. The control panel is down to
3.1 % and is no longer the problem — **the pane is**.

The captured fixture text shows concrete divergences to start from: the reference legend renders
`A` where the candidate renders `2`, and the reference has a `Formatted` control the candidate
lacks. Note that at 1280×800 the named regions account for only ~78 % of the difference, so some
debt is layout shift between panels — find it, do not assume.

**Bar:** both viewports under 2.0 % differing pixels with no 4-connected region above 1.0 %, using
the charter's exemption set **unchanged**. If you conclude a bar is unreachable without a new
exemption, stop and escalate on the issue with the measurement — do not add an exemption yourself.

**The reference's own vitest component tests transfer with the components and must pass.** They
prove behaviour, not pixels; both are required (charter §5).

## Evidence

Commit raw artifacts under `evidence/phase1/y2-transcript-export/`: exported md/txt/json files
from a real session, and the screenshot-diff `report.json` plus difference masks for each
iteration that moved the number. Record the before/after percentages.

Re-run the diff with:

```bash
PATH="/opt/homebrew/bin:$PATH" PYENV_VERSION=3.12.12 pyenv exec python \
  tests/reference_ui_screenshot_diff.py --output evidence/phase1/y2-transcript-export/diff-<n> \
  --diagnostic-region 'transcript-panel=#transcript-panel' \
  --diagnostic-region 'transcript-legend=.tr-legend'
```

Playwright lives in the pyenv 3.12.12 environment, **not** in `.venv`.

State plainly in your evidence what the run does **not** cover.

## Guardrails (enforced — the loop stops on violation)

`RALPH_PREFLIGHT_REQUIRED=1` runs `scripts/afk-guardrails/preflight.py y2-transcript-export` before
every iteration. You own `frontend/src/lib/transcriptExport.ts` and
`frontend/src/components/TranscriptPane.tsx`, plus your own loop dir, `evidence/phase1/`, `docs/`,
`tests/`. **`frontend/src/App.tsx` belongs to y1 and `frontend/src/state/session.ts` to y3** — read
them, do not edit them.

`tests/fixtures/reference_ui_screenshot_diff.json` is **not yours**. The exemption set is a charter
ruling, not a tuning knob.

## Hard constraints

- Push **your own branch only**, to remote `private`. Never push `dev` or `main`. Never force-push.
- You may not close GitHub issues. Comment evidence; the orchestrator closes.
- **Do not weaken a test to make a gate pass** — charter §8. Adding an exemption to reach the bar
  is exactly that.
- Binding authority: `docs/phase1-afk-charter.md` (§5 fidelity method),
  `.wayfinder/map-001-phase1-chrome-client.md` (C2, C10), `docs/phase1-gate-status.md`, `AGENTS.md`.
