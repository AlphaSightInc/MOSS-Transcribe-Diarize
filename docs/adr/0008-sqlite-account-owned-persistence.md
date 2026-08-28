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
- Account revoke is one final mutation after the in-process lifecycle has drained creation and
  settled owned Live/File work. That transaction disables every bound allowlist row and the Account,
  increments its generation, and deletes every Sign-in session only after asserting there are zero
  active rows. Residual File/Live rows must first pass their fixed recovery and cleanup paths; the
  authority transaction never terminalizes them blindly.
  Therefore no process-owned worker loses its captured handle between cleanup and durable terminal
  truth, while every late old-generation mutation fails after the transaction.
- An accepted Account revoke is strongly owned by the lifecycle, shielded from its control handler,
  and joined by product lifespan before Live/File owners and this connection close. Handler
  cancellation may lose its response but cannot abandon a fenced Meeting, synchronous runner, or
  terminal filesystem operation.
- The same mutation lock also bounds every request-facing read on the one connection. SQLite exposes
  a connection's own uncommitted writes, so an unlocked read could otherwise observe terminal status
  before the transcript upsert in the same transaction. Internal SELECTs already inside a mutation
  remain direct and never reacquire the lock. The Live probe held exactly that between-write state:
  snapshot, list, and authentication reads all waited; rollback exposed only
  `active`/version 1/prefix, while commit exposed only `completed`/version 2/final document.
- Account-revoke interruption joins the publication worker before reading its durable document.
  A mutation admitted before the fence may already have committed even when its coroutine has not
  resumed; it therefore finishes and synchronizes binding version/document. Still-queued work is
  skipped. The atomic terminal mutation uses that exact converged document, while the raw snapshot
  only bounds the maximal accepted audio prefix.
- Crash recovery preserves the last committed transcript and recoverable audio prefix, changes
  active Meetings to `interrupted`, and never resumes capture.
- Account-scoped recovery reuses those same File/Live owner paths before revoke. Verified complete
  File audio interrupted at the finish boundary changes only its state to `partial`; fixed path,
  bytes, and metadata remain unchanged. Persistent raw-stage uncertainty leaves the Meeting active
  and Account/session rows enabled so startup can retry; the in-process generation gate stays closed.
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
- A configured terminal finalizer makes closed/`running` a nonterminal persistence state: any changed
  stop-tail document commits normally and becomes public while the Meeting row remains active. Only
  `final`, `failed`, or `unavailable` writes `completed`; a changed final document and that status use
  the same transaction. The momentary closed/`not_started` event before a configured pass starts is
  not published. A deployment with no finalizer retains the legacy closed/`not_started` completion.
- Shutdown durably interrupts active bindings, then identity-unbinds the runtime publication sink
  before closing workers and the event loop. A later terminal listener may still release its tape,
  but cannot advance memory or SQLite.
- A host Meeting interrupt is owned beyond its Unix handler exactly like accepted Account revoke,
  but claims only one process-owned Meeting. Concurrent callers share that settlement; lifecycle
  shutdown joins it before Live/File owners and SQLite close. A terminal or unknown locator is one
  no-change result. An active SQLite row with no process owner fails visibly rather than reporting
  no change or bypassing its cleanup owner. For Live work, the runtime removes that session's queued
  canonical, refinement, and provisional items under its existing arbiter lock inside the
  no-await process-owner claim, before an admitted SQLite publication can delay async settlement.
  Operator aggregate depth therefore reflects the fence immediately while in-flight work remains
  counted until its late result is rejected. Discarded canonical and refinement admissions close
  through typed terminal events rather than disappearing from private timing maps.
- Meeting title carries `automatic` or `manual` provenance in the existing Meeting row. Creation
  starts automatic; an owner-bound rename transaction trims and requires a non-empty title, writes
  the title and `manual` together, and is permitted for active or terminal Meetings. This is the
  durable owner-precedence fact later automatic-title work must respect; no title-history table or
  rename event stream is introduced.
