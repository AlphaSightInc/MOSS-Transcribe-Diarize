# Context — r1-reference-ui

Iteration 2. The binding acceptance checklist has been reconciled against the
PRD, charter, T-02, T-05, T-07, and T-10. The first visible reference-shell
slice now replaces the stub; the full port remains open.

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
- Focused validation passed: `npm --prefix frontend run typecheck && npm --prefix frontend test &&
  python3 scripts/afk-guardrails/preflight.py r1-reference-ui && git diff --check`.
  Vitest: 6 passed. The Vite `__dirname` deprecation warning is pre-existing tool output,
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

1. Port the reference `TranscriptPane` and its meaningful component tests, removing LLM,
   summary, voiceprint, title/speaker rename, and display-mode controls rather than leaving
   dead controls. Bind it to the ported transcript signal state while preserving generic labels,
   search, and provisional-row rendering.
2. Replace reference `api/ws.ts` with the T-02 poller through the unchanged
   `dispatchWsEvent()` seam, then bind the transcript shell to that state. Do not invent server
   routes or a client-side capture-health policy.
3. Add committed, re-runnable counts and rendered-rail artifacts after the concrete component
   port; then implement the charter's screenshot-diff probe against the reference bundle.
