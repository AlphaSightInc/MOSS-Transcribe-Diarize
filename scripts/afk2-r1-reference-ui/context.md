# Context — r1-reference-ui

Iteration 0. Nothing measured yet by this loop.

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

## Ranked candidates

1. Read the charter and this PRD's gate. Record the acceptance criteria as a checklist here.
2. Confirm preflight passes; if a prerequisite is missing, **stop and escalate**.
3. Smallest vertical slice toward the deliverable — the thing itself, not its evidence.
