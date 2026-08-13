# Handoff: wayfinder map-001 — zero-install Chrome client (Phase 1)

Written 2026-08-12 by the charting session. Another agent is working ticket planning on this
same map **in parallel** — read "Parallel work" before touching anything.

## Launch contract

Start the next session with:

```text
/wayfinder .wayfinder/map-001-phase1-chrome-client.md
```

Then read `docs/handoffs/handoff-wayfinder-map001-20260812.md` in full as the controlling
brief for context the map does not carry.

## Objective

Advance map-001 toward its destination: a **decision-complete Phase 1 spec** that the AFK
builder loop can execute with zero remaining design questions. The map states the destination,
the ten charting decisions (C1–C10), the fog, and the scope boundary — **read it rather than
re-deriving any of it**: `.wayfinder/map-001-phase1-chrome-client.md`.

**This map plans; it does not build product code.** The pull to start implementing is the
signal you have reached the edge of the map, not permission to proceed.

Resolve **one ticket per session** (research tickets excepted).

## State as of this handoff

- Map + **12 tickets** committed on branch `dev`, as its single commit on top of `main`.
  T-12 was filed against the map by the night-ops supervisor while the charting session ran
  and is now tracked alongside the rest.
- Tracker is local-markdown (no issue tracker configured). Conventions: `.wayfinder/README.md`.
  Frontier query: `python3 .wayfinder/frontier.py` (`--all` for every ticket with state).
- Frontier at handoff time: **T-01, T-02, T-03, T-04, T-09, T-12**.
  T-02 blocks the most (T-05, T-07, T-08, and transitively T-06, T-10, T-11).
- No product code has been written. `frontend/` in this repo is still empty.

### T-12 changes the map slightly

T-12 verified against the tree that Phase 2's voice bank is **not** CRUD over an existing
store — no embedding is written to disk anywhere in the product, and the one banking mechanism
built (`0983339` on `ralph/dl2-postreview-rails`) is absent from `main` and from production RC
`fb83ba5`. Its ask is narrow and legitimate: Phase 1 should *record* whether it knowingly
discards vectors, even though building the bank stays Phase 2.

**Applied 2026-08-12** in the same commit as this handoff: the map's *Out of scope* voice-bank
entry now carries the carve-out — the Phase 2 deferral covers *building* the bank, not the
*decision to discard*. T-12 is on the frontier. Nothing pending here.

## Parallel work — coordination hazards

Several agents are live in this repo. Two concrete hazards:

1. **Claim before working.** Set a ticket's `assignee:` frontmatter **first**, before any
   research or writing, so the parallel session skips it. An open, unassigned ticket is
   unclaimed and another agent may take it out from under you.
2. **`dev` was re-cut from `main` on 2026-08-12** — see below. Another agent (codex, tmux
   `Iter-Research:3.1` / `%111`) was sitting on `dev` at the time, so if its working tree looks
   unexpected, that is why. Re-check `git log --oneline -3 dev` rather than assuming.

### The branch plan — EXECUTED 2026-08-12

`dev` now sits **1 commit ahead of `main@2f5a83a`**, 24 files, zero conflicts, working tree
clean. `dev-preplan-backup` still points at the superseded pre-rebase commit `94ed03e` as a
safety net; it can be deleted once the operator is satisfied. The rationale is retained below.

`dev` was cut from `fix/stop-route-bounded-drain`, which is an **ancestor of `main`** — 61
commits behind, zero unique commits. `main@2f5a83a` (2026-08-09) is the current line.

An independent analyst merge simulation (aborted, non-destructive) measured exactly **2
conflicts**: `docs/design-streaming-diarization.md` and
`prototypes/streaming-diarization/NOTES.md`. Both were then proved **redundant** — `main`
already contains all 32 lines of that delta plus ~2508 more, and
`prototypes/streaming-diarization/proto_tape_differential.py` is already tracked on `main`.

So the resolution is a discard, not a merge. Classification of `94ed03e`'s 24 files:
**21 new to `main` (clean add, zero conflict)**, 3 superseded on `main` (drop).

Steps that were run:

1. `git branch dev-preplan-backup dev` (reversible)
2. re-cut `dev` from `main`
3. re-commit only the 21 new files
4. also commit T-12
5. add `.DS_Store` to `.gitignore`
6. verify `git diff main..dev`, then drop the backup (**step 6's deletion is still pending** —
   `dev-preplan-backup` is intentionally kept until the operator confirms)

Verified after the run: `git rev-list --left-right --count main...dev` = `0 1`, 24 files,
+5210 lines, zero conflict markers, clean working tree.

## Ground truth — read, do not re-derive

- **`docs/research-chrome-capture-mvp-2026-08-03.md`** — the single most important document.
  Chrome two-lane browser capture, **Gate 1 PASSED**, attended and measured. It settles frame
  geometry, worklet clock anchoring, activation ordering, the error taxonomy (400/409/429),
  the echo policy, and the lane design. Gates 2 (real audio→GPU e2e), 3 (concurrency), and 4
  (Windows Chrome) remain open. Its kept harness is
  `prototypes/browser-capture-feasibility/` (note: it posts prototype extras to a local stub
  and hardcodes 8000/16000 instead of reading the descriptor).
- **Reference UI source of truth:** `/Users/gao/Desktop/AI_Projects/LiveTranscribe` — Preact +
  Vite + `@preact/signals`, Swift/Vapor backend. A full product, **not a mockup**. Its
  `frontend/src/api/ws.ts` and `api/types.ts` define the event/type contract Phase 1 adapts;
  `dispatchWsEvent()` is the seam that makes the polling swap a one-file change.
- **Control plane** (AFK loop state, ledgers, review decisions, POLICY):
  `/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize`. Holds no product code.
- ADR-0001/0002/0003 under `docs/adr/`; `docs/design-streaming-diarization.md`;
  repo `AGENTS.md` (measure-before-implement is mandatory for any threshold or policy choice).
- Deployed live service is TLS port **7861** — `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861`.
  Omitting the port silently targets unconfigured 443; that mistake has already been made once.

## Suggested skills

- `/wayfinder` — to load the map and work its frontier (the launch contract above).
- `/grilling` + `/domain-modeling` — the default for every `grilling`-type ticket, and the
  map's Notes name them as standing. One question at a time; do not answer for the human.
- `/prototype` — required for T-04, T-06, T-10. The repo's `AGENTS.md` mandates measuring on
  the production code path before writing production code, and
  `prototypes/streaming-diarization/` is the standing bench to **extend**, not rebuild.
- `/research` subagent — only if a ticket needs knowledge outside this working directory. Note
  the charting session created **no** research tickets: the research this map needed already
  exists in-repo.

## Do not

- Do not build product code. Do not create `frontend/` contents. This is a planning map.
- Do not re-litigate C1–C10 on the map or the settled evidence in `AGENTS.md` — bring numbers
  and update the doc in the same change if you have contradicting evidence.
- Do not push, deploy, or open PRs. The control plane's POLICY blocks all three; this handoff
  does not relax that.
- Do not add Uvicorn workers to solve concurrency — device state, session ownership, runtime
  objects, mixers, event queues, and view grants are process-local.
- Do not accept a claimed gate pass at face value. Re-run it from raw artifacts and check its
  **scope**; a rail satisfiable by stub evidence has shipped in this project before.
