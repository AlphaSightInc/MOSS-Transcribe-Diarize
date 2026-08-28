# ADR-0008: One SQLite owner persists Account-owned state

- **Status:** Accepted
- **Date:** 2026-08-27
- **Scope:** Phase-2 durable state

## Context

The measured deployment is one MOSS process, about 2–10 Accounts, 2–4 concurrent Live Meetings,
and roughly 16 small writes per second worst case. PostgreSQL would add a service and operating
surface without buying needed capacity.

## Decision

Ship SQLite 3.53.4 through aiosqlite 0.22.1: one long-lived connection, WAL, foreign keys on, and
`synchronous=FULL`. The schema starts empty at `user_version=1`; an existing non-v1 database is
refused. There is no migration framework, connection pool, retry layer, generic database interface,
or dormant PostgreSQL adapter.

SQLite owns admission, Accounts, Sign-in sessions, Meetings, current structured transcripts,
Meeting Speakers, audio metadata, Voiceprints and samples, and Final summaries. Large Meeting audio
alone lives as owner-partitioned files. Every user-owned row carries `account_id`; Meeting and
Voiceprint children use composite foreign keys that cannot cross Accounts. Live snapshots, events,
and cursors remain in memory, so the 250 ms poll path never reads SQLite.

## Consequences

- Each Account-workspace mutation is one transaction behind the Account workspace module.
- Crash recovery preserves the last committed transcript and recoverable audio prefix, changes
  active Meetings to `interrupted`, and never resumes capture.
- Cold backup/restore is an operator-run stopped-service bundle, not a MOSS product feature or gate.
- The measured Live binding probe in `prototypes/phase2-live-owner-binding/` fixes the poll boundary:
  eight alternating snapshot/event requests performed exactly eight SQLite reads of
  `sign_in_sessions` plus enabled `accounts`, but zero Meeting/transcript content reads and zero
  writes. Live content and cursors came from memory. This preserves ADR-0007's per-request revocation
  check without moving the 250 ms content path into SQLite.
- The same probe held a real transcript commit while a runtime thread advanced two raw revisions.
  Public memory stayed on the old durable revision/event high-water until commit release, then advanced
  once. Revocation fenced the next serialized write; the last durable document stayed public and the
  Meeting became interrupted. Thus durable transcript commit, not raw inference completion, is the
  publication boundary.
- If the terminal event also changes the transcript, its owner-bound handle writes the final document,
  increments its version, and changes Meeting status in one SQLite transaction. The probe injected
  process loss after both writes but before commit: rollback exposed the prior active/version/document
  tuple, while success exposed the terminal/final tuple; no mixed state was visible.
