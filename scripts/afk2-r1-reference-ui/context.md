# Context — r1-reference-ui

Iteration 9. The binding acceptance checklist has been reconciled against the
PRD, charter, T-02, T-05, T-07, and T-10. The first visible reference-shell
slice and reduced transcript component now replace the stub; the full port remains open.

## Where things stand

- Branch `afk2/r1-reference-ui`, cut from `dev`. Worktree 1 of 6.
- The first fleet's work is merged into `dev`, with its P0 regressions already repaired by the
  supervisor. You are building on a tree that is green apart from known pre-existing failures.
- All 12 wayfinder decision tickets are **closed**. Design is settled; this is execution.
- `frontend/src/App.tsx` now uses the reference shell's layout and class contract:
  a three-column `.main`, the reference segmented control with only `Live | File`,
  transcript find affordance, browser file selection surface, and a non-interactive
  right `History` rail. It renders `data-right-collapsed="true"`; its `HistoryPanel`
  has no body or click target.
- `frontend/src/components/SegmentedControl.tsx` is ported from the reference with
  only unused disabled-option support removed. The current shell is still 165 lines
  against the reference App's 1773, so this is not a fidelity completion claim.
- The reference transcript model is now ported in `frontend/src/lib/` with its
  Phase-1 `TranscriptItem` contract and a deliberately small transcript signal state.
  It retains stable item ids, committed/provisional ordering, turn merging,
  generic-label normalization, and match highlighting. The state exposes both event
  upsert and full snapshot replacement: T-02 requires the poller to use replacement
  for `/snapshot`, not event upsert.
- `frontend/src/components/TranscriptPane.tsx` now ports the reference transcript surface
  against that signal state: turn grouping, generic-only speaker labels and legend, timestamps,
  provisional-row/caret treatment, and client-side search (including Cmd/Ctrl-F and match
  navigation). It intentionally omits title and speaker editing, speaker count, summary/LLM,
  voiceprints, display mode, clipboard/export, and their removed shortcuts. The adapted
  reference component tests prove real state-derived rows, provisional rendering, generic-label
  enforcement, and search navigation; they would fail if the component no longer used transcript
  state or search results.
- `frontend/src/api/mossPoller.ts` now replaces the reference websocket transport with the
  T-02 two-cursor poller. It fetches snapshot and event cursors together, parses real MOSS
  snapshot/event shapes, emits only the five reachable reference events through
  `dispatchWsEvent()`, fully replaces the transcript for each new snapshot, dedupes replayed
  event sequences, and uses 250 ms active / 2 s finalizing-idle cadence with timeout,
  cancellation, and capped retry backoff. It maps span-relative timestamps, stable
  committed/provisional keys, silent relabels, finalization, and server-authored status lines.
  `mossPoller.test.ts` proves raw payload mapping, stale provisional rows across a generation
  change, and render-before-cursor advancement. There is deliberately no application caller
  yet: r2 owns live session creation/capture and must instantiate this adapter, including the
  ruled sessionStorage reattach contract.
- `frontend/src/App.test.tsx` is now the committed, rerunnable source/rail evidence probe.
  It measured the reference source tree at 67 files / 17,964 lines and the current tree at
  20 files / 5,873 lines, so it records an explicit remaining fidelity gap rather than treating
  the current slice as complete. It also renders the real `App` and proves the rail has
  `data-right-collapsed="true"`, no history body, and no interactive control. Its captured raw
  output is `evidence/phase1/r1-reference-ui/reference-ui-probe-iteration-6.txt`.
- `tests/reference_ui_screenshot_diff.py` is the committed charter §5 probe. It serves the
  reference and candidate source trees locally in the same headless Chromium process, injects
  `tests/fixtures/reference_ui_screenshot_fixture.json` through each real `state/session.ts`,
  waits for fonts and the reference's 0.28 s collapsed-rail transition, then records screenshots,
  masks, selectors, and metrics at 1440x900 and 1280x800. The config still declares only the
  ruled exemptions: the collapsed right rail and the two-versus-reference mode control. Its
  optional `--diagnostic-region ID=SELECTOR` output is non-gating and leaves that mask untouched.
  Two settled runs both rendered the fixture tail in the real transcript components and failed
  honestly: 1440x900 is `11.5220–11.5613%` differing / `3.1278%` largest region; 1280x800 is
  `17.0370–17.1004%` / `7.5531%`, versus the charter's `2%` / `1%`. The settled raw artifacts
  are `evidence/phase1/r1-reference-ui/screenshot-diff-iteration-9-settled-{a,b}/`; superseded
  iteration-7 timing-sensitive output remains historical evidence only.
- **BLOCKED — supervisor fidelity ruling required.** The settled diagnostic attributes current
  unmasked difference inside the shared control-panel box alone to `5.8448–5.8454%` of the
  1440x900 viewport and `6.4544%` at 1280x800; the shared transcript-panel box adds
  `5.5985–5.6370%` and `7.0905–7.1539%`. Those boxes are measurement regions, not proposed
  exemptions, so they do not isolate or excuse individual controls. T-05/C2 still require the
  reference's host-only microphone/source/mute/export surfaces to be dropped, while T-10's
  question calls dropped controls legitimate exemptions and binding charter §5 omits them. Do
  not add an undeclared mask or reintroduce dropped controls. Supervisor must choose one explicit
  canonical rule: (a) amend charter §5 with declared T-05 dropped-control exemption selectors,
  (b) revise T-05/C2 to retain those reference controls, or (c) approve a different canonical
  Phase-1 visual oracle. Evidence and re-runnable probe: `tests/reference_ui_screenshot_diff.py`,
  `tests/fixtures/reference_ui_screenshot_diff.json`, and the two iteration-9 reports.
- Focused validation passed: `npm --prefix frontend run typecheck && npm --prefix frontend test &&
  python3 scripts/afk-guardrails/preflight.py r1-reference-ui && git diff --check`.
  Vitest: 12 passed. The Vite `__dirname` deprecation warning is pre-existing tool output,
  not a failure.

## Read before your first change

| Path | Why |
|---|---|
| `docs/phase1-afk-charter.md` | Binding. Authority, capture spec §4, fidelity §5, gates §6 |
| `scripts/afk-guardrails/ownership.json` | The paths you may touch |
| `.wayfinder/tickets/` | 12 closed decisions with full rationale |
| `docs/research-chrome-capture-mvp-2026-08-03.md` | Gate 1 measured verdict; browser capture is settled here |
| `AGENTS.md` | Measure before implementing |

## Known pre-existing test failures — not yours, do not "fix"

- `l2-stage0/test_legacy_ingest.py` (55 != 92) and four `test_macos_uds_tracer.py` tests fail
  identically at `pre-afk-20260813`.
- `l15/test_l1_baseline.py` fails with `l15_product_tree_drift`. That guard correctly refuses to
  run L1.5 measurements when the product tree moved. **Do not edit its pin** — that would falsify
  a measurement baseline. It needs re-measurement, which is out of scope.

## Validation

```bash
.venv/bin/pytest -q                    # ~1005 pass, 2 skip, 387 subtests
python3 scripts/afk-guardrails/preflight.py r1-reference-ui
```

## Acceptance checklist

- [ ] Faithfully port the reference's components, state, and lib modules from
  `/Users/gao/Desktop/AI_Projects/LiveTranscribe/frontend/src/`; retain the already
  verified build configuration, `styles/index.css`, and four font families verbatim.
- [ ] Preserve the reference three-column `.main` grid. Render the right
  `HistoryPanel` location only as its non-interactive, permanently-collapsed 48 px
  rail with `data-right-collapsed="true"`; do not render its Phase-2 contents.
- [ ] Keep only the ruled Phase-1 controls: `Live | File`, transcript pane and
  search, generic speaker labels, toasts, unchanged segmented control, and local
  mic mute implemented with `track.enabled = false`.
- [ ] Remove the ruled-out host-only and Phase-2 surfaces: mic/device selection,
  output volume, native pickers, export-to-folder, both server-side mute paths,
  history contents, summary, LLM settings, URL/Batch modes, and shortcuts whose
  targets are gone.
- [ ] Replace the reference `api/ws.ts` transport with a MOSS poller that feeds
  the identical `dispatchWsEvent()` seam; retain the T-02 reachable-event and
  cursor rules, and let file mode use the T-07 client-side jobs adapter.
- [ ] Transfer meaningful reference component tests. `npm --prefix frontend test`
  must fail on an empty suite; no `--passWithNoTests`.
- [ ] Commit re-runnable raw artifacts under
  `evidence/phase1/r1-reference-ui/`: reference/current file and line counts,
  proof that the rendered rail has `data-right-collapsed="true"`, and the final
  fidelity evidence required by charter §5.
- [ ] Before completion: pass `npm --prefix frontend run typecheck`,
  `npm --prefix frontend test`, and r1 preflight after merging current `dev`;
  publish a criterion-by-criterion issue comment that also names gaps in coverage.

## Ranked candidates

1. **BLOCKED on the explicit supervisor fidelity ruling above.** Do not change the mask,
   reintroduce excluded controls, or claim the screenshot gate can pass until that rule selects
   the canonical oracle/exemptions.
2. After that ruling, port the remaining retained reference surface (starting with the
   Topbar/ControlPanel layout), preserving excluded controls as excluded and using the committed
   probe to measure only the authorized oracle.
3. Port the generic `ToastLayer` only when a live/file adapter instantiates the poller and gives
   its error/terminal callbacks a real caller; do not add a local substitute toast state or a
   no-op trigger.
4. When r2 provides session creation, wire its live client to `createMossSessionPoller()` and
   retain the T-02 sessionStorage reattach contract; do not invent a second poller or capture
   health state machine here.
