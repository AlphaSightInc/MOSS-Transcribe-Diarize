# Context — Phase 1 ticket #3

Iteration 1. The live issue acceptance contract is captured below. Nothing has been measured yet
by this loop.

## Where things stand

- Branch: `afk/t3-*`, cut from `dev` at `a05a7f6`. Worktree 3 of 6 (treehouse pool).
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
  native-helper effort. **It is not yours. Ignore it.** Your loop lives in `scripts/afk-t3/`.
- Frame geometry is deploy-manifest data, never a code constant.
- 429 on the v2 lane path is non-terminal; on the legacy mono path it is terminal. Only ever send
  v2 lane frames.
- `setInterval` in a backgrounded tab collapses to ~1/min. Worklet port messages do not.
- `source_revision` comes from the provider manifest and must be re-finalized per host.

## Issue #3 acceptance checklist

Authoritative source: <https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/3>, read live
on 2026-08-13. These seven items are the ticket gate; do not add or substitute criteria.

- [ ] State numeric latency and memory gates before measuring; do not choose them afterward.
- [ ] Measure dispatcher concurrency 1, 2, and 4 with real 0.5 s ingress and real speech spans,
  not synthetic frames.
- [ ] At 1, 2, 4, and 8 simultaneous meetings, record real-time factor, p95 transcript lag,
  fairness across sessions, per-session queue depth, GPU OOM/errors, and vLLM active/queued
  request counts.
- [ ] Choose the largest concurrency under both gates and implement it as a bounded dispatcher.
- [ ] Regression-test cross-session markers under overload and across reconnect; no session may
  receive another session's text.
- [ ] Confirm the 16-item queue bound is per session and decode lag yields 429 backpressure
  independently per client.
- [ ] Introduce no additional Uvicorn workers; process-local state makes them unsafe here.

Charter G4 additionally defines how the measured criterion is accepted: sustain the chosen bound
for at least 10 minutes, keep p95 transcript lag under the predeclared gate, provide fair
round-robin service, avoid OOM, and observe 429 per session rather than globally. G5 defines the
cross-session criterion: text never crosses under overload or reconnect. Stub evidence cannot
satisfy any real gate. The remote 4070 host remains read-only; qualifying runs must use a locally
started service.

## Validation commands

Establish these in iteration 1 and record what each actually covers:

```bash
.venv/bin/pytest -q                      # full suite; baseline ~418 passed / 2 skipped
.venv/bin/pytest -q tests/test_live_api.py tests/test_live_auth.py tests/test_live_mixer.py
bash -n scripts/afk-t3/ralph-afk.sh
```

## Ranked candidates

1. Establish and record a working validation command set.
2. Predeclare numeric latency and memory gates, then extend the standing bench with the smallest
   production-path probe needed to measure them.
3. Smallest evidence-backed vertical slice toward the bounded dispatcher.
