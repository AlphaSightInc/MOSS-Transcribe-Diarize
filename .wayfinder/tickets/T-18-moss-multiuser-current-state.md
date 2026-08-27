---
id: T-18
map: map-002-phase2-multiuser
title: MOSS multi-user-relevant current state — auth, sessions, grants, journal, storage
type: research
status: closed
assignee: charting-research-20260826
blocked_by: []
---

## Question

What does MOSS actually ship today on branch `dev` that Phase-2 identity/isolation must build
on or replace? The isolation architecture decision needs the real seams, not the planning-era
descriptions. Inspect `dev` via `git show dev:<path>` / `git ls-tree` (never check it out — the
working tree is user-owned and dirty) plus the current worktree read-only where live internals
are newer.

Surface, with file:line evidence:

- **Auth today** — the Phase-1 shared bearer token: where configured, which routes enforce it,
  what a "client" is (any `device_id` remnants, `sessionStorage` reattach), and the older
  pairing/capture-authority/view-authority code (`Live access registry`) — present, wired, or
  dormant?
- **Session identity and grants** — how live session ids are minted, who may read
  `/snapshot`/`/events`, how the Chrome client reattaches, and every place a session id in a
  request selects server state (the future isolation choke points).
- **Event/snapshot delivery** — the exact route inventory for live and for `/api/jobs` (file
  mode), and any cross-session surface (operator `/live` diagnostic, logs).
- **Vector journal** — what the Phase-1 session-end album-centroid journal actually writes
  (schema, path, embedder identity stamp), per closed ticket
  *Voice-bank persistence* (T-12) — the voice bank's raw material.
- **Audio retention today** — ADR-0003 posture as implemented: retained mixed tape, lane
  buffers, what survives Stop on disk today (paths, formats), and the export routes.
- **Persistence today** — every durable store the server writes (files, SQLite if any),
  their layouts and owners.
- **Frontend seams** — where the Chrome client would carry an account (poller headers,
  `dispatchWsEvent()` seam, `TranscriptStreamParser`), and the `speaker_renamed` event declared
  unreachable in Phase 1 (*Poll contract* ticket) — the future rename hook.
- **Concurrency/backpressure** — the bounded dispatcher shipped for G4 and per-session 429
  semantics, as implemented.

Record findings in `.wayfinder/research/T-18-moss-current-state.md` with paths and an explicit
"absent/dormant/unknown" list. This ticket informs *Identity and isolation architecture*; it
decides nothing itself.

## Resolution

Resolved 2026-08-26 by a charting-session research subagent (read-only audit of branch `dev`
via `git show`, current worktree read-only for newer live internals). Full findings incl. the
choke-point table and journal schema:
[`../research/T-18-moss-current-state.md`](../research/T-18-moss-current-state.md).

Load-bearing facts for *Identity and isolation architecture* (T-19):

- **Auth today**: one in-memory `LiveAccessRegistry` (`dev:moss_transcribe_diarize/app/live_auth.py`)
  resolves (peer, bearer, action, session_id) per request. The deployed path is a single
  shared-token file mapped to synthetic device `"shared-token"` — **all shared-token clients are
  one principal with full capture authority over each other's sessions; cross-user isolation is
  zero by construction.**
- **Pairing-era code is fully wired but Chrome never pairs**: loopback-minted
  `mtd1.<secret>.<cert-sha>` payloads, per-device tokens, cert pinning — consumed only by the
  macOS Keychain client. View tokens are session-scoped, 12 h cap, authority derived live from
  session status. A "client" is just a bearer + tab-scoped `sessionStorage {sessionId, viewToken}`
  (ADR-0004); no device_id, no accounts, no job ownership.
- **Choke points**: 12 authenticated routes where a session/job id selects keyed server state
  (~9 in-memory session-keyed dicts + JobManager) — tabulated in findings §5. Plus **8 job
  routes with NO auth even in live mode** (media download, segments read/**write**, rerun,
  resume, render, download), and the batch service (port 7860, plaintext, `0.0.0.0`) has no
  auth on anything — a LAN peer with a 12-hex job id can read uploaded audio and rewrite
  transcripts today.
- **Vector journal is default-ON with `--live`**: clean stop appends per-speaker rows
  (`session_id, speaker_label, centroid, sample_seconds, exemplar_count, provisional,
  embedder_id, embedder_state_sha, created_at, echo_mode`) to one 0600 JSONL spanning all
  sessions; abort writes nothing; **no read route exists**. Audio retention (ADR-0003) is
  opt-in and **deployed OFF** — the durable biometric derivative outlives the meeting even in
  the "no audio persisted" posture (inverted privacy asymmetry; consent boundary open).
- **No SQLite anywhere; sessions/view grants are memory-only** — restart orphans everything
  (`live-auth.json` persists devices only). **Loopback = root**: pairing mint and revocation
  need no credential beyond being a local process.
- **Canonical inference is globally single-threaded** (one pump thread); G4 concurrency =
  fairness + bounded per-session queues + typed 429s — and the Phase-1 G4 gate was BLOCKED for
  lack of a measurement host, not code.

Unknowns and the full absent/dormant inventory are in the findings file.
