---
id: T-21
map: map-002-phase2-multiuser
title: Persistence decision — database choice and schema ownership boundaries
type: grilling
status: closed
assignee: codex-20260826
blocked_by: [T-17, T-19]
---

## Question

Which database does the MVP ship, and where do the schema ownership boundaries sit?

Decide, with the operator, on the evidence of *Database for multi-user MOSS* and the identity
model from *Identity and isolation architecture*:

- **Engine** — SQLite vs PostgreSQL for this measured shape (single Windows host, one process,
  2–4 live sessions, ~10 accounts). If T-17's paper case is close, demand its named prototype
  measurement first (`/prototype`, per `AGENTS.md`) rather than deciding from taste.
- **What is relational vs file** — accounts, allowlist, sign-in sessions, meeting/session
  records, transcript text, voiceprints (vector blobs vs sidecar files), audio (files on disk
  with DB metadata, presumably — decide), LLM artifacts.
- **Ownership columns as the isolation substrate** — every owned table carries the owning
  account id; how that composes with T-19's enforcement seam (e.g. repository layer that always
  binds `account_id`).
- **Lifecycle** — migrations story (tool + version), backup/restore drill the operator will
  actually run, crash-mid-meeting durability expectations.
- **The escape hatch** — if SQLite: the concrete constraints kept so a later PostgreSQL move
  stays mechanical; if PostgreSQL: the operational runbook the operator accepts.

Resolution records the engine (+exact version), the table inventory at MVP depth, the
ownership-column rule, and the backup drill — decision-complete for the AFK builder.

## Resolution

Resolved with the operator on 2026-08-26.

### Engine and runtime

- Ship **SQLite 3.53.4** on the single Windows server. The runtime library, not merely an
  installed CLI, is 3.53.4. The measured worst case is about 16 tiny writes/s from one MOSS
  process, at least 10x inside the paper envelope; the case is not close enough to require the
  named latency prototype. PostgreSQL's multi-process and network-writer capacity is outside
  this MVP and does not justify another Windows service, credential/port surface, upgrade path,
  or backup system.
- Use **aiosqlite 0.22.1** directly. One long-lived connection owned by the persistence
  implementation serializes access; there is no pool or multiple-writer design. Configure
  `journal_mode=WAL`, `foreign_keys=ON`, and `synchronous=FULL`. Each Account-workspace
  mutation is one transaction. There is no retry framework or custom lock timeout.
- Live snapshots and events remain process-memory delivery state. The 250 ms poll path never
  reads SQLite.

### Relational/file split and table inventory

SQLite is authoritative for all identity, metadata, text, JSON, and voice vectors. The
filesystem is authoritative only for the large canonical Meeting-audio file; SQLite stores its
metadata and path. There are no JSON projection sidecars and no audio BLOBs. Exports are
generated on demand rather than persisted.

The MVP has these ten application tables:

1. `account_allowlist` — operator-owned global admission policy; normalized email and enabled
   state. It is not user-owned and has no `account_id`.
2. `accounts` — one row keyed by the verified Google `sub` (`account_id`), with current email,
   display facts, enabled state, and timestamps.
3. `sign_in_sessions` — revocable authentication records owned by `account_id`; credential
   representation and expiry mechanics are supplied by *Authentication decision*.
4. `meetings` — durable ownership/lifecycle root with `account_id`, mode, title, status, and
   timestamps. Live and file capture share this record; there is no separate durable jobs table.
5. `meeting_transcripts` — exactly one current structured transcript JSON document and version
   per Meeting. The current live surface has no durable segment identifiers, so the schema
   persists the aggregate directly instead of inventing a translation layer.
6. `meeting_speakers` — Meeting-local speaker identity/name state and any Voiceprint link.
7. `meeting_audio` — Meeting-audio lifecycle, relative file path, media facts, size, duration,
   and timestamps; bytes stay on disk. This canonical name follows the later, more specific
   *Audio retention design* ruling.
8. `voiceprints` — Account-owned durable acoustic references with private display labels.
9. `voiceprint_samples` — Account-owned Voiceprint samples with vector BLOB and provenance required by
   *Voice bank design*.
10. `llm_artifacts` — Account- and Meeting-owned text/JSON result, kind, state, model/provenance,
    and timestamps required by *Client-configured LLM — functions, browser ownership, artifact access, and UI contract*.

There are deliberately no tables for live events, cursors, devices, pairing/view grants,
generated exports, or separate file-mode jobs.

### Ownership and module seam

- Every user-owned table carries `account_id`. Meeting artifacts carry both `account_id` and
  `meeting_id`; their composite foreign key targets the same Account's Meeting. Voice samples
  likewise carry `account_id` plus `voiceprint_id` and can target only that Account's
  Voiceprint. An optional Meeting-speaker/Voiceprint link has the same composite constraint.
- Routes never accept or forward a caller-supplied `account_id`. Authentication opens the deep
  Account workspace module decided by *Identity and isolation architecture*; its hidden
  persistence implementation binds the Account. Meeting handles returned by that module remain
  owner-bound. Background work carries the owner internally.
- Resource identifiers remain locators. Another Account's identifier cannot form a valid
  owner-constrained lookup or relationship and resolves as `404`.

### Schema lifecycle, crash behavior, and backup drill

- This green-field MVP has **no migration system**, Alembic dependency, downgrade scripts, or
  compatibility layer. A missing database is initialized once as schema v1 and records
  `PRAGMA user_version = 1`; an existing non-v1 database is refused explicitly. A future schema
  change gets its own concrete upgrade decision when it exists.
- Persist the current transcript after every accepted transcript commit. Meeting audio streams
  to a recoverable partial file. Live events and cursors are not durable. After a crash, startup
  retains the last committed transcript and recoverable audio prefix, changes any `active`
  Meeting to `interrupted`, and exposes it in Account history; capture never resumes
  automatically. Normal Stop commits `active -> completed` only after transcript and audio are
  durable.
- The deployment supplies one cold-backup command: stop MOSS, create one timestamped bundle
  containing a `VACUUM INTO` SQLite snapshot plus the Meeting-audio tree, restart MOSS, and pass
  its health check. Restore stops MOSS, replaces both database and audio tree from the same
  bundle, restarts, and verifies Account/Meeting counts plus one selected transcript/audio
  artifact. Backup cadence and retention counts remain with the map's existing storage-growth
  fog after *Audio retention design* measures the retained size.

### PostgreSQL escape hatch

Do not build a generic database interface or dormant PostgreSQL adapter. Keep all SQL inside the
Account-workspace persistence implementation; use application-generated UUID text keys, UTC
epoch-millisecond integers, ordinary text/JSON/BLOB values, explicit foreign keys, and no
triggers, full-text search, SQLite-specific JSON queries, or hidden type coercion. If the
single-process premise later breaks, replace this one hidden implementation and run a one-off
copy utility. That bounded future rewrite is accepted in exchange for no present compatibility
scaffolding.
