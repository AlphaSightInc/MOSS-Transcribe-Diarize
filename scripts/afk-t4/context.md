# Context — Phase 1 ticket #4

Iteration 0. Nothing measured yet by this loop.

## Where things stand

- Branch: `afk/t4-*`, cut from `dev` at `a05a7f6`. Worktree 4 of 6 (treehouse pool).
- All 12 wayfinder decision tickets are **closed**. Design is settled; this is execution.
- Target repo `frontend/` is empty. `/` currently serves the inline Subtitle Studio.
- Live routes are default-off and enabled via `create_app(live_enabled=True, ...)`.

## Read these first (do not re-derive)

| Path | Why |
|---|---|
| `docs/phase1-afk-charter.md` | **Binding.** Authority, limits, capture spec §4, fidelity method §5, gates §6, attended checklist §7 |
| `.wayfinder/map-001-phase1-chrome-client.md` | Premises C1–C11 and the decision index |
| `.wayfinder/tickets/` | The 12 closed decision tickets with full rationale |
| `docs/research-chrome-capture-mvp-2026-08-03.md` | Gate 1 measured verdict. Frame geometry, worklet clock anchoring, activation ordering, error taxonomy — all settled |
| `AGENTS.md` | Measure-before-implement is mandatory |
| `CONTEXT.md` | Domain glossary. Use its vocabulary |

## Known traps, already paid for once

- `scripts/ralph-afk/` holds a **stale 285 KB `context.md` and an old PRD** from the earlier
  native-helper effort. **It is not yours. Ignore it.** Your loop lives in `scripts/afk-t4/`.
- Frame geometry is deploy-manifest data, never a code constant.
- 429 on the v2 lane path is non-terminal; on the legacy mono path it is terminal. Only ever send
  v2 lane frames.
- `setInterval` in a backgrounded tab collapses to ~1/min. Worklet port messages do not.
- `source_revision` comes from the provider manifest and must be re-finalized per host.

## Validation commands

Establish these in iteration 1 and record what each actually covers:

```bash
.venv/bin/pytest -q                      # full suite; baseline ~418 passed / 2 skipped
.venv/bin/pytest -q tests/test_live_api.py tests/test_live_auth.py tests/test_live_mixer.py
bash -n scripts/afk-t4/ralph-afk.sh
```

## Ranked candidates

1. Read the charter and the issue. Record the acceptance criteria as a checklist here.
2. Establish and record a working validation command set.
3. Smallest vertical slice toward criterion 1.
