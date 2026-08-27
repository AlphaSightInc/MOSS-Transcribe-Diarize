---
ticket: T-17
map: map-002-phase2-multiuser
title: Database for multi-user MOSS — SQLite vs PostgreSQL under this deployment
status: findings
researched: 2026-08-26
informs: T-21 persistence decision (this file decides nothing)
---

# T-17 findings — SQLite vs PostgreSQL under the measured MOSS shape

Premises taken as given (map-002 C2/C4, not re-derived here): single Windows host
`ga0-alienware-rtx4070ti`, ONE FastAPI process (process-local runtime state is load-bearing,
multi-process out of scope — map-002 line 106), 2–4 concurrent live sessions (C4, line 74),
~2–10 accounts on the tailnet (C2, line 72), operator is not a DBA.

**No SQLite (or any database) exists in the code today.** `rg -l -i sqlite` matches only docs
and wayfinder tickets; `pyproject.toml` dependencies contain no sqlalchemy / psycopg / asyncpg /
aiosqlite / alembic (`pyproject.toml:13-27`). All state is process-local dicts plus JSON files
(`job.json`, JSONL vector journal, tape files). Whatever engine is chosen is a green-field add.

---

## 1. Write/read shape per live meeting (repo facts, order-of-magnitude)

Empirical basis: two real session event logs from the 2026-08-25 campaign, cross-validated at
two durations. `evidence/live-surface-optimization-20260825/stability-04-lex_bill_ackman/events.jsonl`
(960,000 samples @ 16 kHz = 60 s → 243 events, snapshot version 154) and
`pass-A-lex_keyu_jin_5m/events.jsonl` (4,800,000 samples = 300 s → 1,207 events, snapshot
version 764). Sample rate: `LIVE_SAMPLE_RATE = 16000` (`moss_transcribe_diarize/app/live_span_bounds.py:34`).

Event-kind census of the 60 s session (counted from events.jsonl):

| Kind | n / 60 s | Rate | Driver |
|---|---|---|---|
| frame_accepted | 120 | 2/s | client posts 0.5 s PCM frames (max 1.0 s: `max_frame_samples: 16000`, `evidence/phase1/w0-local-live/live-provider-manifest.json:15`) |
| span_frozen | 24 | 0.4/s | endpoint hard cap 40,000 samples = 2.5 s (`live-provider-manifest.json:33-35`: hard_cap 40000, min_silence 8000 = 0.5 s, min_speech 1600) |
| canonical_queued / _started / _processed | 24 each | 0.4/s each | one decode triplet per frozen span |
| text_revision_applied | 7 | ~0.1/s | rolling 10 s window revisions (`live_coordinator.py:83-84` — "fixed ten-second cut") |
| rolling_decode_queued / _completed | 6 each | ~0.1/s | one per 10 s window |
| lifecycle (session_created, identity_finalized, vector_journal_appended, session_closed, terminal_finalization_*, session_tape_released, decode_salvaged) | 8 | one-off | session start/end |

Estimates (stated as estimates, ~1 significant figure):

| Flow | Order of magnitude | Code basis |
|---|---|---|
| **Events appended** | ~4/s per session (243/60 s; 1,207/300 s) → ~14K rows per meeting-hour; 4 sessions ⇒ **~16 inserts/s host-wide worst case** if the full event log were persisted | events.jsonl census above; emit site `app/live_service_runtime.py:1513-1520` (`_record_event`), 20+ call sites lines 624–1703 |
| **Durable transcript commits** (the subset worth persisting: canonical_processed + text_revision_applied) | ~0.5/s per session ≈ 31/min ≈ **~2K rows per meeting-hour**; 4 sessions ⇒ ~2/s host-wide | same census; commit path `app/live_transcript_convergence.py:309-324` (committed_samples advance) |
| **Snapshot version bumps** | ~2.5/s per session (154/60 s; 764/300 s) — today an in-memory counter, not a write | events.jsonl `snapshot_version` field |
| **Vector journal** | **1 append per session end**, one JSONL row per speaker (~2–10 rows); event census shows exactly one `vector_journal_appended` | `app/live_vector_journal.py:67` (`append_session`, whole-batch single write with lock, torn-tail repair `:241-255`) |
| **Heartbeats** | latest-only, in-memory, never appended — "Observation-only helper health store for strict latest-heartbeat facts" | `app/live_helper_presence.py:182`; if ever persisted it is 1 UPDATE/s/session, not inserts |
| **File-mode `/api/jobs`** | 1 `job.json` atomic rewrite per state change, live-progress saves throttled to ≥0.5 s apart ⇒ **≤2 writes/s per active job** | `app/jobs.py:735-747` (`_save_job` → `_atomic_write_json`; `_should_save_live_progress` 0.5 s gate) |
| **Poller reads** | 2 GETs per cycle (snapshot + events). Portal today: 500 ms fixed (`pollDelayMs = 500`, `app/live_portal.py:158`). Phase-1 Chrome-client contract: **adaptive 250 ms capturing / 2 s idle** (`.wayfinder/map-001-phase1-chrome-client.md:66`, C3). At 250 ms: 8 reads/s per viewer; 4 sessions × 1–2 viewers ⇒ **~30–60 point reads/s host-wide** | routes `app/live_transport.py:364,387-399`; runtime reads `app/live_service_runtime.py:746-766` (in-memory list scans today) |
| **Phase-2 durable inventory** (accounts, allowlist, sessions, voiceprints, audio metadata, LLM artifacts) | accounts ~10 rows total; allowlist ~10; sessions ~10/day; voiceprints ~10–100 total; audio metadata 1 row/session; LLM artifacts per-request, low tens/day | map-002 lines 15-25, 72-75; no code yet |

**Net shape: writes ~10^0–10^1/s host-wide (tiny rows, one process); reads ~10^1–10^2/s point
queries against a hot set of a few thousand rows; total data ~10^6–10^7 rows/year** (~2M/yr
durable-subset, ~20M/yr if the full event log is kept at 4 meetings/day). Blob-heavy payloads
(audio tapes, PCM) already live as files and stay there.

**Architectural note that caps DB read load:** the 250 ms poll path is served from
process-local memory today (`live_service_runtime.py:746-766`) and process-local state is a
stated premise. If that stays true, the DB is a durability/write-behind layer and pollers
never touch it — DB reads drop to session-list/history queries (~10^0/s). Only if snapshots
are re-served *from* the DB does the ~30–60 reads/s figure land on the engine. Both engines
below are assessed against the worse case.

---

## 2. SQLite under this shape

Version: **SQLite 3.53.4, released 2026-07-24** (sqlite.org front page, retrieved 2026-08-26,
https://www.sqlite.org/index.html). Public domain. In Python's stdlib (`sqlite3`); async via
aiosqlite (§5).

**WAL vs FastAPI async handlers.** WAL mode: "Readers do not block writers and a writer does
not block readers. Reading and writing can proceed concurrently … since there is only one WAL
file, there can only be one writer at a time." (https://www.sqlite.org/wal.html, retrieved
2026-08-26). The single-writer rule is per-*database*, but all 2–4 "writer sessions" here live
in ONE FastAPI process — writes can be funneled through one connection (or a serialized
writer task), which makes the single-writer constraint an implementation detail, not a
contention source. Arithmetic, not benchmark: worst-case ~16 inserts/s; even at a very
conservative 10 ms per commit that is 16% writer-queue utilization; batching each session's
~4 events/s into one transaction per poll tick cuts it further. Long-running read transactions
can starve checkpoints and grow the WAL without bound (wal.html) — pollers must use
autocommit point reads, never held read transactions; WAL does not work on network
filesystems (wal.html) — local NVMe only, which matches this host.

**busy_timeout.** `PRAGMA busy_timeout = N` retries a locked operation up to N ms before
surfacing SQLITE_BUSY; one busy handler per connection (https://www.sqlite.org/pragma.html#pragma_busy_timeout,
retrieved 2026-08-26). Standard setup for this shape: `journal_mode=WAL`,
`synchronous=NORMAL`, `busy_timeout=5000`. SQLITE_BUSY can still appear in obscure cases
(exclusive-mode open, last-connection cleanup, crash recovery — wal.html), so handlers should
treat it as retryable.

**Do 2–4 writers + pollers fit one writer queue?** On paper, comfortably: ~16 small inserts/s
against a queue that is idle >84% even under pessimistic per-commit cost, with readers never
blocked by the writer in WAL. This is 1–2 orders of magnitude inside the envelope. What paper
cannot settle is this *host* (NTFS + consumer NVMe fsync while the GPU stack loads the
machine) — §6.

**Official appropriate-uses guidance.** "Any site that gets fewer than 100K hits/day should
work fine with SQLite" and it has been demonstrated at 10× that; avoid when many computers
access the database over a network, for write-heavy multi-server sites, >~281 TB, or when
more than one concurrent writer is required (https://www.sqlite.org/whentouse.html, retrieved
2026-08-26). This deployment is the textbook fit: one host, one process, low write
concurrency. Honest caveat: at the 250 ms poll cadence, ~30–60 reads/s ≈ 3–5M requests/day
— above even the 10× website figure — *if* every poll hits the DB. These are single-row
point reads, not dynamic-page workloads, but this is exactly the number the prototype (§6)
must measure rather than argue; the process-local-serving architecture (§1 note) makes it moot.

**Backup story (three tiers, all Windows-fine except the last):**
- `VACUUM INTO 'file'` — "an alternative to the backup API for generating backup copies of a
  live database"; output is a consistent snapshot, minimal size, synced to disk when
  `synchronous` is NORMAL/FULL (https://www.sqlite.org/lang_vacuum.html, retrieved
  2026-08-26). One SQL statement an operator can put in Task Scheduler. Target file must not
  already exist.
- Online Backup API / CLI `.backup` — incremental copy of a live DB, source locked only
  during brief reads (https://www.sqlite.org/backup.html, retrieved 2026-08-26). Caveat:
  writes from a *different* connection than the one backing up restart the backup — prefer
  VACUUM INTO here.
- Never plain-copy a live WAL database: state lives across `.db` + `-wal`; copy only via the
  two mechanisms above or with the app stopped.
- **Litestream** (streaming replication to S3/local): **v0.5.16, 2026-08-05, Apache-2.0**
  (github.com/benbjohnson/litestream, /releases, retrieved 2026-08-26). Release notes state:
  "Windows binaries are provided for convenience but Windows is NOT an officially supported
  platform. Use at your own risk." (officially supported: Linux, macOS; install docs list
  no Windows package — https://litestream.io/install/, retrieved 2026-08-26). On this
  Windows host Litestream is a nice-to-have experiment, not a plannable backup tier.
  Scheduled `VACUUM INTO` + existing file-sync is the dependable story.

---

## 3. PostgreSQL under this shape

Version: **PostgreSQL 18 is the newest major (18.6 current minor as of 2026-08-13; 17.11,
16.15 also supported); majors get 5 years of support** (https://www.postgresql.org/support/versioning/,
retrieved 2026-08-26).

Capacity is a non-issue: ~16 inserts/s + ~60 point reads/s is negligible for PostgreSQL. The
question is purely operational cost on a single Windows host for a ~10-user product:

- **Install/service.** Certified path is the EDB interactive installer (PG 18 supports
  Windows Server 2025/2022; graphical or silent), bundling pgAdmin + StackBuilder
  (https://www.postgresql.org/download/windows/, retrieved 2026-08-26). Service registration
  is first-class: `pg_ctl register -N PostgreSQL -S auto` / `unregister`
  (https://www.postgresql.org/docs/current/app-pg-ctl.html, retrieved 2026-08-26) — the EDB
  installer does this for you. So: one extra always-on Windows service, a postgres superuser
  password, `pg_hba.conf` auth surface, and a listening port to keep tailnet-only.
- **Upgrades.** Minor releases: replace binaries, restart — "minor upgrades are that simple."
  Major releases change the storage format and require `pg_dumpall` dump/restore, `pg_upgrade`,
  or logical replication (https://www.postgresql.org/docs/current/upgrading.html, retrieved
  2026-08-26). For a non-DBA operator, a major upgrade is a real half-day choreography that
  SQLite simply does not have (its file format is stable; upgrading the library is a pip/app
  update).
- **Backups.** `pg_dump dbname > dumpfile` runs against a live DB without blocking,
  producing an internally consistent snapshot; restore via `psql`/`pg_restore`; roles need
  `pg_dumpall` (https://www.postgresql.org/docs/current/backup-dump.html, retrieved
  2026-08-26). Fine on Windows and schedulable. **pgBackRest is effectively off the table
  on Windows**: pgbackrest.org's user-guide index offers Debian/Ubuntu and RHEL guides only,
  no Windows guide or package (https://pgbackrest.org/user-guide-index.html, retrieved
  2026-08-26; current pgBackRest v2.59.1, 2026-08-17, MIT). So the Windows story is pg_dump
  on a scheduled task — adequate at this data size, but a second backup system for the
  operator to own next to the file-tree backups the app already needs.
- **Memory.** `shared_buffers` defaults to 128 MB; the 25%-of-RAM guidance is for dedicated
  DB servers and does not apply — this host's RAM/VRAM budget belongs to the GPU inference
  stack (https://www.postgresql.org/docs/current/runtime-config-resource.html, retrieved
  2026-08-26). Expect a few hundred MB resident for PG kept at defaults; unmeasured on this
  host (§7).

Net: PostgreSQL is operationally *heavier everywhere* (install, service, auth, port, major
upgrades, separate backup discipline) and buys capacity headroom this shape does not use,
plus two things SQLite genuinely lacks: true multi-writer concurrency across *processes*
(explicitly out of scope by premise) and network client access (out of scope by C2 tailnet +
single host). Its rewards activate exactly when the premises break.

---

## 4. Failure recovery — crash mid-write

- **SQLite:** transactions are ACID "even if the act of writing the change out to the disk
  is interrupted by a program crash, an operating system crash, or a power failure"
  (https://www.sqlite.org/transactional.html, retrieved 2026-08-26). In WAL mode, the first
  connection after a crash runs recovery automatically (briefly holding an exclusive lock —
  wal.html). **Operator drill: none — restart the app.** Restore drill: stop app → copy the
  latest `VACUUM INTO` snapshot over the DB file → start app. One file, no tooling.
  (Contrast with today's non-DB JSONL journal, which hand-rolls exactly this: torn-tail
  termination at `live_vector_journal.py:241-255` — a DB makes that code deletable.)
- **PostgreSQL:** WAL REDO — committed changes are re-applied from the log at service start;
  data-page writes are ordered after WAL flush, so committed transactions survive
  (https://www.postgresql.org/docs/current/wal-intro.html, retrieved 2026-08-26). **Operator
  drill: none — the service restarts and recovers.** Restore drill is where the asymmetry
  lives: reinstall/verify service → `createdb` → `psql -X dbname < dumpfile` (+ roles via
  `pg_dumpall` output) — several psql-literate steps versus one file copy.

Both engines are equally safe mid-write. The non-DBA difference is entirely in the *restore*
drill and in who owns the service when it fails to start.

---

## 5. Migration escape hatch — start SQLite, move to PostgreSQL if the trust boundary widens

Toolchain (PyPI, retrieved 2026-08-26): **SQLAlchemy 2.0.52 (MIT)**; **aiosqlite 0.22.1
(MIT)** for `sqlite+aiosqlite://`; **asyncpg 0.31.0 (Apache-2.0)** or **psycopg 3.3.4
(LGPL-3.0-only, released 2026-05-01)** for the PostgreSQL side. Note repo floor is Python
≥3.10 (`pyproject.toml:12`) — all four fit.

Concrete constraints that keep the later move mechanical (adopt on day one, enforceable by
review/CI):

1. **All DDL via SQLAlchemy Core `MetaData`** (Alembic optional) — no hand-written CREATE
   TABLE, no SQLite `STRICT` tables, no PG-only DDL.
2. **Portable column types only**: `Integer`/`BigInteger`, `Text`, `LargeBinary`, `Boolean`,
   `Float`, `Numeric`, generic `JSON`. No PG `ARRAY`/`JSONB`-operator queries, no SQLite
   type-affinity tricks.
3. **App-generated UUIDs as TEXT primary keys** — sidesteps autoincrement/sequence semantics
   differences entirely.
4. **Timestamps as INTEGER epoch-millis UTC (or TEXT ISO-8601)** — SQLite has no native
   datetime; picking the encoding explicitly means both engines store identical values.
5. **PRAGMAs only in an engine-setup hook behind a dialect check** (the WAL/busy_timeout
   setup is connection config, not schema).
6. **Upserts through one helper**: both dialects support `ON CONFLICT` but via separate
   SQLAlchemy dialect modules (`sqlalchemy.dialects.sqlite.insert` vs `.postgresql.insert`) —
   one wrapper function is the only allowed call site.
7. **No raw SQL strings in app code** except through that helper layer.

With these held, migration = install PG (§3) + one copy script (SELECT via
`sqlite+aiosqlite://`, INSERT via `postgresql+asyncpg://`; 10^6–10^7 tiny rows ⇒ minutes) +
change one `DATABASE_URL`. **Estimated cost: hours to one day.** Without them (drifted
engine-specific SQL), it becomes a schema-and-query audit: days to weeks. The constraints are
the escape hatch; the engine choice is then reversible.

---

## 6. What only a measurement can settle — the named prototype

The paper case says SQLite fits with ≥10× margin on writes; the one number paper cannot
produce is read/commit latency on *this host's* filesystem under *this* poll cadence while
the GPU stack loads the machine. If T-21 finds the paper case close, demand:

> **Prototype `sqlite-wal-poll-latency`** — on `ga0-alienware-rtx4070ti` (Windows, the real
> data drive), one SQLite 3.5x database, `journal_mode=WAL`, `synchronous=NORMAL`,
> `busy_timeout=5000`, running inside one Python process with asyncio + aiosqlite 0.22.x:
> - **Writers:** 4 tasks (one per simulated session), each inserting one ~300-byte event row
>   at 4/s and upserting one transcript-segment row at 24/min (the §1 empirical rates), each
>   write its own transaction (worst case — no batching).
> - **Readers:** 8 tasks (2 viewers × 4 sessions), each on a 250 ms loop issuing the two poll
>   queries: `SELECT * FROM events WHERE session_id=? AND seq>=?` (indexed, returns the tail)
>   and a single-row snapshot SELECT. Autocommit; no held read transactions.
> - **Background:** run while the live stack transcribes one real session (or replay
>   `evidence/live-surface-optimization-20260825` audio) so disk/CPU contention is real; plus
>   one `VACUUM INTO` fired mid-run to price the backup.
> - **Duration:** 30 min. **Report:** p50/p95/p99/max for (a) poll-read latency, (b) write
>   commit latency; count of SQLITE_BUSY reaching handlers; WAL file high-water mark.
> - **Pass gates:** p99 read < 50 ms and p99 commit < 100 ms (both far under the 250 ms poll
>   budget); zero unhandled SQLITE_BUSY; WAL bounded < 16 MB (checkpoints progressing under
>   continuous polling).
> - **Variant B (decides architecture, same harness):** identical load but reads served from
>   a process-local dict — quantifies what serving polls from memory (today's design) saves,
>   i.e. whether the DB needs to be on the poll path at all.

If Variant A misses a gate on this host, that is the concrete, non-vibes trigger for
PostgreSQL (or for keeping polls off the DB) — recorded numbers either way.

---

## 7. Unmeasured (explicit)

- Any latency number on `ga0-alienware-rtx4070ti`: NTFS/NVMe fsync cost, SQLite commit
  latency, poll-read p95 under GPU load — §6 exists to produce these.
- WAL checkpoint behavior under continuous 250 ms polling on Windows (starvation risk is
  documented in wal.html; whether it manifests here is not).
- PostgreSQL resident memory next to the inference stack on this host (default-config PG is
  "a few hundred MB" by reputation; not measured, and the 25%-RAM guidance explicitly does
  not apply).
- Litestream reliability on Windows (upstream disclaims support; untested here).
- Concurrent file-mode job writes + 4 live sessions on one database (the §6 harness covers
  live only; add a job writer if file mode lands on the same DB).
- Phase-2 row sizes for LLM artifacts and voiceprint payloads (map names them; no code
  exists — §1 inventory numbers for those are pure estimates).
- Event-rate sensitivity to endpoint policy: the 4 events/s figure is under the current
  manifest (2.5 s hard cap); a policy sweep changing span cadence moves it proportionally.

## Source register

| Claim | Source | Retrieved |
|---|---|---|
| SQLite 3.53.4 (2026-07-24) | https://www.sqlite.org/index.html | 2026-08-26 |
| WAL semantics, single writer, checkpoint starvation, no network FS, crash recovery lock | https://www.sqlite.org/wal.html | 2026-08-26 |
| Appropriate uses, 100K hits/day, one-writer guidance | https://www.sqlite.org/whentouse.html | 2026-08-26 |
| busy_timeout semantics | https://www.sqlite.org/pragma.html#pragma_busy_timeout | 2026-08-26 |
| Online Backup API live-copy | https://www.sqlite.org/backup.html | 2026-08-26 |
| VACUUM INTO as live backup, sync guarantee | https://www.sqlite.org/lang_vacuum.html | 2026-08-26 |
| ACID across program/OS crash and power failure | https://www.sqlite.org/transactional.html | 2026-08-26 |
| PostgreSQL 18 newest; 18.6 minor; 5-yr support | https://www.postgresql.org/support/versioning/ | 2026-08-26 |
| EDB Windows installer, PG18 on Server 2025/2022 | https://www.postgresql.org/download/windows/ | 2026-08-26 |
| pg_ctl register/unregister Windows service | https://www.postgresql.org/docs/current/app-pg-ctl.html | 2026-08-26 |
| Minor vs major upgrade paths | https://www.postgresql.org/docs/current/upgrading.html | 2026-08-26 |
| pg_dump live consistent dump; psql/pg_restore | https://www.postgresql.org/docs/current/backup-dump.html | 2026-08-26 |
| shared_buffers default 128MB; 25% guidance | https://www.postgresql.org/docs/current/runtime-config-resource.html | 2026-08-26 |
| WAL REDO crash recovery | https://www.postgresql.org/docs/current/wal-intro.html | 2026-08-26 |
| pgBackRest v2.59.1, MIT; guides Debian/Ubuntu+RHEL only | https://pgbackrest.org/ ; https://pgbackrest.org/user-guide-index.html | 2026-08-26 |
| Litestream v0.5.16 (2026-08-05), Apache-2.0, "Windows … NOT an officially supported platform" | https://github.com/benbjohnson/litestream/releases ; https://litestream.io/install/ | 2026-08-26 |
| SQLAlchemy 2.0.52 MIT | https://pypi.org/pypi/SQLAlchemy/json | 2026-08-26 |
| aiosqlite 0.22.1 MIT | https://pypi.org/pypi/aiosqlite/json | 2026-08-26 |
| asyncpg 0.31.0 Apache-2.0 | https://pypi.org/pypi/asyncpg/json | 2026-08-26 |
| psycopg 3.3.4 LGPL-3.0-only | https://pypi.org/pypi/psycopg/json | 2026-08-26 |

Repo citations are working-tree paths at branch `ralph/live-convergence-0824` (dirty,
read-only), 2026-08-26.
