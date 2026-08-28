# ADR-0013: Project operator status through the service-owned control plane

- **Status:** Accepted
- **Date:** 2026-08-28
- **Scope:** Phase-2 host-local observability

## Context

The cooperating host operator needs readiness, capacity, active-work, capture-health, and storage
truth without gaining a second way to read Account content or mutate the product. SQLite owns
durable counts and lifecycle; the Live runtime and File task registry own transient state. Neither
source alone can truthfully answer the question.

## Decision

One deep Operator Status module composes those existing owners behind #18's service-owned,
mode-`0600` Unix socket. Its public operation is `snapshot()`. `mtd-admin status` renders that
allowlisted result for humans; `status --json` returns the same result exactly. The client never
opens SQLite and no TCP, web, metrics, daemon, or second socket surface is added.

The one allowlist serializer is also the only input to structured service-journal emission.
Journal events contain aggregate numeric or enumerated context only—never Account email, Account
identifier, Meeting identifier, content, source, secret, or filesystem path. The reducer emits
only meaningful edges. Its first observation emits readiness and establishes a current-state
baseline; restart does not fabricate historical Account or Meeting events. A private 64-event
recent buffer bounds process memory and is not exposed as status or persisted as an audit log.

SQLite supplies Account, active Meeting, artifact metadata, and logical counts in one protected
read. Live supplies exact queue/capture/backpressure facts. File Meeting tasks supply their
process-local `queued`/`running` phase. Physical SQLite/WAL sizes and filesystem free bytes are
measured from the service's configured roots; paths never cross the projection.

## Evidence

`prototypes/phase2-operator-status/probe.py` is the one-command policy probe. Its recorded PASS in
`NOTES.md` proves no-op deduplication, restart-baseline truth, sentinel exclusion, and a fixed
64-event bound through the absorbed production reducer. The largest measured event was 324 bytes;
the full private buffer remained below 20,736 serialized bytes.

## Consequences

- Status is a current observation, not an audit history.
- Events between observations may coalesce; no periodic status logger or durable audit table is
  introduced.
- A field without an authoritative current owner is omitted or explicitly unavailable; it is not
  inferred from content or a second database reader.
- Issue #20 may add `interrupt(meeting_id)` to this same deep module and socket. It must not create
  another control path.
