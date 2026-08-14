# Context — r1-reference-ui

Iteration 1. The binding acceptance checklist has been reconciled against the
PRD, charter, T-02, T-05, T-07, and T-10. No product source has changed yet.

## Where things stand

- Branch `afk2/r1-reference-ui`, cut from `dev`. Worktree 1 of 6.
- The first fleet's work is merged into `dev`, with its P0 regressions already repaired by the
  supervisor. You are building on a tree that is green apart from known pre-existing failures.
- All 12 wayfinder decision tickets are **closed**. Design is settled; this is execution.

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

1. Confirm preflight remains green and inspect the current/reference frontend trees to choose
   the smallest faithful shell port; if a prerequisite is missing, **stop and escalate**.
2. Port the smallest vertical slice toward the deliverable — the real reference shell, not an
   evidence-only substitute — within `frontend/src/` ownership.
3. Add committed, re-runnable comparison probes and raw artifacts only once the port has a
   concrete surface to measure.
