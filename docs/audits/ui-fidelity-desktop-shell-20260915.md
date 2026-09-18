# Desktop shell fidelity — the region no gate covered

2026-09-15, executing `docs/handoffs/handoff-k6LY6i.md`. The operator's verdict was "still crappy, not
production ready". They were right, and the reason is structural: **the existing pixel gate
(`tests/reference_ui_screenshot_diff.py`) measures only `#transcript-panel`**, and its own docstring says
the Account product shell "is neither compared nor masked here". Every appearance check ever run therefore
excluded the exact region the operator was looking at.

Reference oracle: `~/Desktop/AI_Projects/LiveTranscribe`, served populated by
`tools/uifidelity/reference_oracle.py` (new). Serving the built bundle statically is **not** enough — the app
stays in its booting state when `/api` calls fail and renders a blank page.

## What was actually wrong

The stylesheet is a near-verbatim copy of the reference (205 of 208 top-level selectors shared, identical
design tokens). The desktop layout was dismantled by three deliberate overrides plus the server-rendered
wrapper:

| # | Override (`frontend/src/styles/index.css`) | Effect |
|---|---|---|
| 1 | `body.phase2-workspace { overflow: auto }` | fixed app became a document scroller |
| 2 | `.phase2-workspace [data-live-capture="account"] .app { height: auto; min-height: 100vh }` | lost the fixed viewport |
| 3 | `.phase2-workspace [data-authority="account"] .main { grid-template-columns: var(--side-col) minmax(0,1fr) }` | **deleted the reference's third column** |

With no third column, `MeetingHistory` — which already renders the reference's exact
`<section class="panel history-panel account-history-panel">` markup — was exiled to a full-width section
below the fold, and `_workspace_html` added a raw `<header>`, an anchor `<nav class="workspace-nav">`,
`<h1>Your meetings</h1>` and four `<h2 class="phase2-workspace-heading">` that the reference has no
equivalent for.

## Measured result (both charter-gated viewports)

| metric | reference | MOSS before | MOSS after |
|---|---|---|---|
| scrollHeight @1440×900 | 900 | **2362** | **900** |
| scrollHeight @1280×800 | 800 | **2187** | **800** |
| body overflow | hidden | auto | hidden |
| `.history-panel` @1440 | x=1142 y=70 w=280 | x=18 **y=951** w=1404 | **x=1142 y=98 w=280** |
| `.history-panel` @1280 | x=1022 w=240 | x=18 y=851 w=1244 | **x=1022 w=240** |
| `.control-panel` @1280 | w=240 | w=280 | **w=240** |
| `.transcript-shell` @1440 | x=310 w=820 | x=310 w=1112 | **x=310 w=820** |

x-positions and widths now match the reference exactly at both viewports. The residual difference is
vertical: MOSS's panes start at y=98 rather than y=70, because the File/URL strip (72px) occupies grid row 1.
The reference has no such strip — it puts File and URL inside the Controls panel behind a Mode segmented
control. Moving them there is blocked by the DOM-order contract (below), so the strip was compacted from
**293px to 72px** instead.

## Contracts preserved (verified in the real app flow, not by inspection)

`tests/phase2/test_workspace_reachability_browser.py` asserts `[data-workspace-section]` **DOM order**
`file, live, history, voiceprints` on desktop *and* mobile, plus history visibility and the exact viewport
meta. The restructure is CSS-only (grid placement), so DOM order is untouched. Probe result:

- section order `["file","live","history","voiceprints"]`; viewport meta `width=device-width, initial-scale=1`
- `.workspace-nav`, `<h1>`, `.phase2-workspace-heading`, raw `<header>` → **visually hidden but present in the
  DOM** (screen readers and tests still see them), not deleted
- intact: `data-file-upload`, `data-open-meeting`, `data-meeting-card`, `data-audio-download`,
  `data-history-root`, `data-history-boot`, `.account-history-panel`, `#app`, `#transcript-panel`, `.topbar`

**Below 1025px nothing changed.** The reference itself stacks below `max-width: 1024px` (its own 400px
rendering clips badly), and the charter gates only 1440×900 and 1280×800.

## The two named defects

- **Disabled speaker chips looked identical to live ones.** `.legend-chip` had no disabled styling at all, so
  a dead chip still painted a hover border. Now `button.legend-chip:disabled { opacity: .58; cursor: default }`
  and hover is suppressed via `:hover:not(:disabled)`. Verified in the real flow: chips on a history meeting
  report `disabled: true, opacity: "0.58", cursor: "default"`.
- **Rename dialog's huge checkmark.** The bare `<input type="checkbox">` in `.history-dialog` matched neither
  existing checkbox rule and fell back to the browser default. It now reuses the reference's
  `.sp-voiceprint` treatment (16px box, tinted row, single-line label).

## The missing capability, now built

`tools/uifidelity/reference_oracle.py` serves the reference populated. A shell fidelity gate (session
scratchpad) renders the real `_workspace_html` with the built bundle and stubbed APIs — no models, no TLS —
and asserts, at both gated viewports: no page scroll, `overflow: hidden`, history is a right rail, history
above the fold, rail width within 8px of the reference, DOM section order, topbar near the top, and
transcript/history heights ≥85% of the reference. **18/18 checks pass.**

## Findings that are NOT this change

1. **URL mode fails on the internal instance for environmental reasons.** `POST /api/meetings/url` returns
   201 then `status=failed` for every URL — a valid speech MP3, a valid music MP3, and a deliberately bogus
   404 all fail identically. The same `sample-9s.mp3` **acquires successfully on MacStudio (154,062 bytes)**
   through the product's own `UrlMediaAcquirer`, and `archive.org` separately returned a real 503 that the
   code correctly translated to `UrlAcquisitionRejected`. The acquirer is sound; the Alienware host appears to
   have no outbound egress. **Operator action required before any demo that shows URL mode.**
2. **The transcript-pane gate was already failing before tonight.** Controlled A/B (edits reverted, rebuilt,
   re-run; then restored, rebuilt, re-run):

   | viewport | before | after | bar |
   |---|---|---|---|
   | 1052×869 | 3.119% | 3.252% | 2.0% |
   | 932×769 | 3.804% | 3.911% | 2.0% |

   Largest contiguous region stays under its 1.0% bar throughout and *improved* at 932×769 (0.921% → 0.838%).
   The +0.13pp is the disabled-chip opacity — unavoidable, because the reference's chips in that state are
   *enabled*, so any correct disabled affordance must diverge. The bulk is pre-existing product divergence
   inside the gated pane that is not exempt: `.tr-speakers-label` ("Speakers 2" vs "# Speakers A"),
   `.transcript-export-trigger` ("Export transcript" vs "Formatted"), `.transcript-view-placeholder`, and
   MOSS-only `.utt[data-continuation]` rules. Only `.tr-legend-right` is exempt. Left for an operator ruling —
   closing it means either changing the product or widening the exemption set, and widening a gate is not a
   decision to take unattended.
3. `tests/reference_ui_screenshot_diff.py` cannot run on MacStudio unpatched: it refuses any SQLite other than
   3.53.4 (MacStudio has 3.50.4). Runs above relaxed that guard the same way
   `tests/phase2/_installed_frontend_probe.py` already does. The pixel comparison does not exercise the
   pinned-SQLite deployment contract.

## Verification run

- shell fidelity gate **18/18** at 1440×900 and 1280×800
- `npm run build`, `npm run typecheck`, `npm test` — **206 frontend tests pass**
- local browser/surface regression — **27 passed** (`test_workspace_demo_geometry`,
  `test_workspace_reachability_browser`, `test_browser_workspace`, `test_account_deployment_surface`,
  `test_legacy_surface_absence`, `test_multi_file_url_browser`)
- e2e vs the internal instance (`:7862`): rows **1,2,4,6,7,11 → 6/6 PASS** (file WER 0.087, all five export
  formats, 50s audio decodable), rows **13,14 → 2/2 PASS** (3s and 20s origin outages recover with frame
  resumption in 0.14s/0.23s and both lanes sequence-continuous; three consecutive captures all finalize)
- `stress_lifecycle` **7/7**, `stress_reshare` **6/6** (transcribes across reshare and mic-switch boundaries)
- `verify_summaries` via the keyless macstudio relay — **2/2 current** (50s in 8.4s, 180s in 12.9s; the 180s
  case the file's own docstring says fails about a third of the time)

Nothing was committed or pushed; changes sit in the `auto-mvp-0911` worktree.

---

## Adversarial review round (2026-09-16)

`/codex:adversarial-review` returned **needs-attention** with two findings. Both were real; both are fixed.

### Finding 1 (high) — unbounded voice bank could consume the workspace

The desktop grid is `grid-template-rows: auto minmax(0,1fr)`. The voiceprints section sat in row 1 with
`height: auto` and no cap, and `VoiceprintBank` expands *in place* (a `<ul>` with Rename/Delete per row).
Because row 2 is `minmax(0,1fr)` it may shrink to zero, and desktop sets `body { overflow: hidden }`, so an
ordinary voice bank could squeeze the whole workspace with no way to scroll.

Reproduced empirically with 14 saved voiceprints — worse than the review described. The workspace did not
merely shrink, it **collapsed**:

| measurement | 1440×900 before | 1280×800 before | after |
|---|---|---|---|
| `scrollHeight` | **1338** (bar ≤900) | **1355** (bar ≤800) | 900 / 800 |
| voiceprints section height | **1324** | **1341** | 450 / 400 |
| `.control-panel` | y=938 **h=2** | y=838 **h=2** | h=350 / h=300 |
| `.transcript-shell` | y=882 **h=58** | y=782 **h=58** | h=406 / h=356 |
| `.history-panel` | y=882 **h=2** | y=782 **h=2** | h=406 / h=356 |

Fix: `max-height: 50dvh` + `overflow: auto` on the section, so the bank scrolls inside a bounded box
(chosen over an overlay to preserve existing layout and focus behaviour).

### Finding 2 (medium) — URL entry became an unexplained blank field

The desktop rule visually hid *every* `.field-label` in the upload strip, including "Media URLs, one per
line". The server template gives `textarea[name="urls"]` no placeholder, and the section heading and nav are
also hidden, so sighted desktop users lost both the field's purpose and the one-per-line instruction.

Fix (CSS only): the URL caption is rendered inline and visible — measured **147×17px** — while the file
caption stays hidden (1×1), since the native "Choose Files" control is self-describing.

### Gate strengthened

The gate could not have caught finding 1: it only ever measured the bank collapsed. It now populates 14
voiceprints, clicks the toggle, and asserts on the expanded state — no page scroll, bank ≤50% of viewport,
and each of controls/transcript/history ≥240px tall and above the fold. Verified red (10 failures) before the
fix and green after, so the assertions are not vacuous.

**Result: 30/30 gate checks pass** at 1440×900 and 1280×800; collapsed-state geometry unchanged
(transcript h=784, topbar y=98, rails 280/240). Local regression **29 passed** (was 27; codex added a
parametrized `test_expanded_voiceprint_bank_cannot_consume_desktop_workspace` to
`tests/phase2/test_workspace_demo_geometry.py` — additive, with independent assertions; the pre-existing
test is unchanged). Frontend 206/206.

### Known cosmetic consequence, not fixed

With the bank expanded, grid row 1 grows to the bank's height (450px at 1440×900) while the file strip is
capped at 72px, leaving roughly 380px of empty background to its left. The panes stay usable and the gate
passes, but it looks unfinished. Making the expanded bank an overlay (or moving Voiceprints into the History
rail as a Sessions|Voiceprints tab, which is what the reference actually does) would remove both the gap and
the height contention. Not done — it is a design change beyond the two findings.

---

## Voiceprints moved into the History rail as a tab (2026-09-16)

The bounded-scroll fix closed the collapse defect but left a cosmetic wart: an expanded bank grew grid row 1
to 450px while the file strip stayed 72px, leaving ~380px of empty background. The reference does not have a
voiceprints strip at all — `HistoryPanel.tsx` renders a `SegmentedControl` (`className="history-tabs"`,
options `Sessions` / `Voiceprints`) as the first child of the history panel body, with **one shared
toolbar** (search + Refresh + Clear all) serving both views. MOSS now does the same, and the empty gap is
gone because row 1 is once again just the 72px file strip.

**Implementation.** `historyView` signal in `state/ui.ts` (reset by `resetUiState`); `MeetingHistory`
renders `.seg.history-tabs` with `role="tablist"`/`role="tab"`; `VoiceprintBank` lost its own toggle and
renders only when `historyView === "voiceprints"`, keeping `aria-label="Private voiceprints"`; `phase2.py`
nests the voiceprints section inside the history section; `main.tsx` relocates it into
`.history-panel .panel-body` at boot. No new CSS was needed — MOSS already shipped `.seg`, `.seg-btn` and
both `.history-tabs` rules identical to the reference.

| | reference | MOSS @1440×900 | MOSS @1280×800 |
|---|---|---|---|
| `.history-panel` | x=1142 y=70 w=280 h=812 | x=1142 y=14 w=280 **h=868** | x=1022 y=14 w=240 h=768 |
| `.transcript-shell` | x=310 w=820 | x=310 y=97.5 w=820 h=784.5 | x=270 y=97.5 w=740 h=684.5 |
| scrollHeight | 900 / 800 | 900 | 800 |

The rail is now full height (rows 1–2), which is closer to the reference than the previous split. Switching
tabs causes **zero layout shift** — `.control-panel` and `.transcript-shell` keep identical `top` and
`height` to within 0px.

**One risk, proven not to bite.** `main.tsx` appends a server-rendered node into a container Preact owns and
re-renders, so it could be clobbered. Verified to survive Voiceprints → Sessions → history Refresh →
Voiceprints with all rows intact, and that exact cycle is now locked by a regression test.

**A sentinel I refused to weaken.** `tests/phase2/test_acceptance_locator_sentinels.py:69` asserts exactly
two Refresh buttons — a locator-uniqueness guard. My first instruction had hidden the shared toolbar in the
Voiceprints view, which broke it, and the proposal was to relax the assertion to 1. That was rejected: the
correct fix was restoring the shared toolbar (which is what the reference does anyway), so the assertion
passes **unchanged**. Only locators moved, and the history Refresh locator got *tighter* (scoped to
`.history-panel-actions`). Consequence: two Refresh buttons are visible in the Voiceprints view — the shared
one and the bank's own. Mildly redundant, kept deliberately so the sentinel keeps its strength.

`test_expanded_voiceprint_bank_cannot_consume_desktop_workspace` encoded the superseded strip design. It was
replaced, not deleted, by `test_voiceprint_tab_does_not_disturb_desktop_workspace`, which asserts strictly
more: zero shift in both `top` and `height`, `documentHeight <= viewportHeight`,
`history.contains(voiceprints)`, panels ≥240px and above the fold, and the URL caption visible by
`display`/`visibility` as well as size.

**Verification:** shell fidelity gate **24/24** at both viewports (including `vp-survives-rerender`);
local regression **43 passed** across eight files; frontend **206/206**; build and typecheck pass; no CSS
changed at or below 1024px.
