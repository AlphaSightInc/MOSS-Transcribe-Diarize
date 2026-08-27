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
