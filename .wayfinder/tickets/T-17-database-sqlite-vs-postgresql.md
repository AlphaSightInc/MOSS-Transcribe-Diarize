---
id: T-17
map: map-002-phase2-multiuser
title: Database for multi-user MOSS — SQLite vs PostgreSQL under this deployment
type: research
status: closed
assignee: charting-research-20260826
blocked_by: []
---

## Question

Which database engine fits this MVP's measured shape — not familiarity? Premises: single
Windows server host (`ga0-alienware-rtx4070ti`), one FastAPI process (process-local runtime
state stands), 2–4 concurrent live sessions (C4), ~2–10 accounts (C2), pollers reading
snapshots/events at 250 ms–2 s cadence, plus durable rows for accounts, allowlist, sessions,
transcripts, voiceprints, audio metadata, and LLM artifacts.

Surface, from primary sources plus repo facts:

- **Write/read shape** — from the MOSS current-state audit's storage findings, estimate rows
  and write frequency per live meeting (transcript commits, journal appends, heartbeats if
  persisted) — order-of-magnitude, stated as estimates.
- **SQLite under this shape** — WAL mode single-writer semantics vs FastAPI async handlers;
  `busy_timeout`; whether 2–4 writers + pollers fit one writer queue; current official guidance
  on appropriate uses; backup story (`sqlite3 .backup`, VACUUM INTO, Litestream — versions,
  licenses, Windows fit).
- **PostgreSQL under this shape** — operational cost on a single Windows host (service install,
  upgrades, backups via pg_dump/pgBackRest, memory footprint) for a ~10-user product; exact
  current versions.
- **Failure recovery** — crash-mid-write behavior for both; restore drill shape for an operator
  who is not a DBA.
- **Migration escape hatch** — cost of starting SQLite and moving to PostgreSQL later if the
  trust boundary widens (schema portability, e.g. staying inside SQLAlchemy-core-compatible
  types; exact version of any ORM/driver named).
- **What only a measurement can settle** — name the specific load question a prototype would
  answer (e.g. p95 poll latency with N writers on this host) so the decision ticket can demand
  it if the paper case is close.

Record findings in `.wayfinder/research/T-17-database.md` with source URLs, retrieval dates,
versions, and an explicit "unmeasured" list. This ticket informs the decision ticket
*Persistence decision*; it decides nothing itself.

## Resolution

Resolved 2026-08-26 by a charting-session research subagent (repo facts from two real
2026-08-25 campaign event logs + primary sources with URL/date). Full findings:
[`../research/T-17-database.md`](../research/T-17-database.md).

Load-bearing facts for *Persistence decision* (T-21):

- **Green-field**: no database exists in the code today — all state is process-local dicts,
  `job.json`, JSONL vector journal, tape files; pyproject has no DB dependency.
- **Measured shape (from real session logs, 60 s and 300 s cross-validated)**: events ~4/s per
  session; durable transcript commits ~0.5/s per session; vector journal one append per
  session end; heartbeats latest-only in-memory. Host-wide worst case ~16 inserts/s of tiny
  rows; ~2M durable rows/year. Poll reads only hit the DB (~30–60 point reads/s) **if**
  snapshots are re-served from it — today's process-local serving keeps the DB off the poll
  path entirely (~10^0/s reads), which is itself an architecture lever for T-21.
- **SQLite 3.53.4** (public domain, stdlib): the paper case fits with ≥10× margin on writes
  in WAL mode. **Litestream v0.5.16 is explicitly NOT officially supported on Windows** — the
  streaming-backup story is the weak flank; `VACUUM INTO`/backup API are the native paths.
- **PostgreSQL 18.x**: fits trivially but adds a Windows service, upgrades, and backup
  tooling for a ~10-user product run by a non-DBA operator.
- **Migration escape hatch**: mechanical if constrained to SQLAlchemy Core-portable types and
  no engine-specific SQL (exact library versions in findings).
- **Named prototype** if the paper case is judged close: **`sqlite-wal-poll-latency`** — fully
  specified in findings §6 (4 writer tasks at empirical rates + 8 pollers at 250 ms on the
  real host under real GPU load, 30 min; pass gates p99 read <50 ms, p99 commit <100 ms, zero
  unhandled SQLITE_BUSY, WAL <16 MB; Variant B serves reads from a process dict to price
  keeping the DB off the poll path).

Unmeasured (explicit in findings): every latency number on this host's NTFS/NVMe; WAL
checkpoint behavior under continuous polling on Windows; PostgreSQL resident memory beside
the inference stack.
