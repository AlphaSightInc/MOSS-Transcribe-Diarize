# Context — Phase 1 ticket #6

Iteration 1. Acceptance criteria captured from live issue #6; no implementation measured yet.

## Where things stand

- Branch: `afk/t6-*`, cut from `dev` at `a05a7f6`. Worktree 6 of 6 (treehouse pool).
- All 12 wayfinder decision tickets are **closed**. Design is settled; this is execution.
- Target repo `frontend/` is empty. `/` currently serves the inline Subtitle Studio.
- Live routes are default-off and enabled via `create_app(live_enabled=True, ...)`.
- Issue #6 is OPEN and remains blocked by OPEN issue #1 (checked 2026-08-13).

## Acceptance checklist — issue #6 (binding)

- [ ] At session end, append one record per speaker containing `session_id`, `speaker_label`,
  `centroid`, `sample_seconds`, `embedder_id`, `embedder_state_sha`, `created_at`, and
  `echo_mode`.
- [ ] Every row contains both `embedder_id` and `embedder_state_sha`.
- [ ] Records are keyed by session, never by device; Phase 1 has no `device_id`.
- [ ] Vector journaling defaults ON while raw-audio retention remains OFF.
- [ ] The journal path is operator-configurable and outside the checkout.
- [ ] A refused or unusable observation is declined by name and never aborts the session.
- [ ] Documentation states that the journal is not a consent decision and that rollout beyond
  the guarded LAN requires an explicit consent and right-to-remove ruling first.

Source: <https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/6>, read live on
2026-08-13. T-12 confirms this is only an append-only, session-keyed journal of live-album
centroids; CRUD, enrollment, naming, matching, UI, and D-7 are out of scope.

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
  native-helper effort. **It is not yours. Ignore it.** Your loop lives in `scripts/afk-t6/`.
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
bash -n scripts/afk-t6/ralph-afk.sh
```

## Ranked candidates

1. Establish and record a working validation command set.
2. Smallest vertical slice toward criterion 1.
