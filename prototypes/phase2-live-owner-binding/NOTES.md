# Phase-2 owner-bound Live Meeting prototype

## Contract

- **Question:** can the originating MOSS Sign-in session control capture while every request first
  resolves its enabled Account and then enters an Account-partitioned in-memory Live registry; and
  can that authority/publication adapter share one transport implementation with the legacy adapter?
- **Minimum primitives:**
  - **Current Sign-in-session resolution.** Its boundary is one request: the cookie resolves from
    SQLite to one currently enabled Account and authority generation before any Live lookup. It
    cannot be removed or cached in the Live registry because then revocation and Account isolation
    would no longer govern every request.
  - **Owner-bound Meeting handle.** Its boundary is durable mutation: Account ID, authority
    generation, and Meeting ID are captured together and callers can never rebind one component.
    It cannot be replaced by a bare/global Meeting lookup without restoring caller-selected
    authority.
  - **Account-partitioned transient Live binding.** Its boundary is active-process observation: it
    holds the originating Sign-in-session locator, runtime, public snapshot/events, high-water
    marks, and helper lease in memory, but grants no authority and creates no durable grant. It is
    irreducible because 250 ms observation cannot read durable Meeting/transcript content and still
    needs one place to coordinate the active capture lifecycle.
  - **Shared Live transport.** Its boundary is the invariant protocol: frame decoding, v2 lane
    registries, mixer, tape, heartbeat, Stop, abort, error mapping, and capture-state release. Only
    authorize/create and snapshot/events/publication hooks cross the adapter seam. It cannot be
    split per authority model without duplicating protocol behavior that does not vary.
  - **Per-binding serialized durability bridge.** Its boundary is publication: runtime-thread raw
    revisions enter one event-loop queue, commit through the captured Meeting handle, and only then
    advance public snapshot/events. It cannot be removed or parallelized because a poll could then
    expose undurable or out-of-order text/event state.
  - **Existing store mutation lock shared by external reads.** Its boundary is one SQLite
    connection: request-facing reads take the lock; SELECTs already inside a mutation do not. It
    cannot be omitted because same-connection reads can observe a multi-row transaction before
    commit, and it cannot be broadened to internal reads without lock reentrancy.
  - **Page-local capture controller plus ephemeral history observer.** Its boundary is browser page
    state: only the page that created capture owns mutation controls; history-open attaches a reader
    without writing reattach storage, while reload discards control. It cannot collapse into one
    generic viewer/controller state without either granting observer control or silently resuming
    capture after reload.
- **Invariant:** every request resolves the current session plus enabled Account from SQLite;
  same-Account observers read but do not mutate; another Account gets `404`; the 250 ms poll path may
  read only authentication rows and reads no Meeting/transcript content or writes; revocation returns
  `401` and fences late commits; interruption preserves the last durable prefix and never resumes.
  A cleanly closed runtime remains durably active while terminal finalization is `running`; its
  stop-tail transcript becomes public only after its ordinary commit. Only a terminal finalization
  outcome may atomically publish its last document together with `completed`. Request-facing reads
  on the store's one SQLite connection share its existing mutation lock; internal SELECTs already
  inside a mutation stay unlocked. A reader may wait, but cannot see half a multi-row transaction.
- **Assumption:** one Sign-in session is one Access client; sibling tabs sharing its cookie are not a
  distinct client. This is settled by T-19 and ADR-0007, not introduced here.
- **Hypothesis:** this state is sufficient; no bearer, view token, client Account identity, durable
  grant, or global durable Meeting lookup is needed. The only transport seam needs five operations:
  authorize, create, snapshot, events, and publication. Frame decoding, v2 lane state, mixer, tape,
  heartbeat, Stop, abort, errors, and capture-state release do not vary. In the browser, opening an
  active history item needs only an ephemeral observer attachment: it writes no reattach storage and
  enables no capture mutation. A page that originated capture keeps its existing controller; reload
  removes that controller and may reattach only its stored read view.
- **Falsifier:** any printed path permits observer/foreign mutation or foreign read, performs a
  Meeting/transcript read or write during polling, accepts a late result after revoke, loses the
  committed prefix, resumes after interruption, or exposes closed/final words before their atomic
  terminal commit. The shared-seam hypothesis is also false if legacy and Phase 2 produce different
  frame/Stop/error results, or if Phase 2 exposes a held publication.

## Tool and experiment decisions

Each probe exists because source inspection alone cannot establish the corresponding runtime
ordering. The stated reachable result changes the decision; no result is collected only as a proxy.

- **Browser page-state transition probe:** necessary to expose controller, observer, and storage
  state before and after history-open/reload. Reject the page-state primitive if an observer gains
  mutation authority or writes reattach storage, or if reload retains capture control.
- **Shared-transport two-adapter probe:** necessary to execute the same protocol implementation
  through both real authority/publication shapes. Reject the five-hook seam, or deepen it only with
  the newly varying behavior, if frame acceptance, duplicate-frame error, Stop, event sequence, or
  terminal snapshot differs between adapters; reject durable-before-public if a held Phase-2
  publication becomes visible.
- **Production `Phase2Store` plus SQLite trace callback:** necessary to count the actual SQL on the
  authorization/poll path instead of inferring I/O from code. Reject memory-backed 250 ms polling if
  any repeated poll reads Meeting/transcript content or writes; reject request-time authority if a
  revoked/disabled Account still opens a binding.
- **Held/rolled-back production store mutation:** necessary to make the otherwise brief gap between
  Meeting status update and transcript upsert observable. Reject the existing-lock design and choose
  a different connection/transaction boundary if snapshot, list, or Account reads return before the
  transaction ends or expose a mixed old/new tuple.
- **Real runtime-thread to event-loop handoff with held serialized commits:** necessary to observe
  raw, durable, public, and event high-water state while work is concurrent. Reject the bridge if
  polling advances before commit, commits reorder, a database failure mutates public text, or a late
  callback reaches a closed event loop.
- **Finalizer/revocation/shutdown fault transitions:** necessary because their accepted-prefix and
  callback fences are reachable only while work is pending. Reject the terminal policy if
  closed/`running` completes the Meeting early, final words are non-atomic, revocation accepts a late
  commit, interruption loses the durable prefix or resumes capture, or shutdown publishes late work.
- **Temporary SQLite database and controlled in-memory gates:** necessary to run real store and
  concurrency semantics without retaining prototype authority/data. A result that depends on state
  surviving the temporary directory, wall-clock sleeps, or a production database rejects the
  prototype as non-reproducible evidence.

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --frozen --extra dev python prototypes/phase2-live-owner-binding/probe.py
```

## Verdict

**Accepted.** The one-command run exercised the production `Phase2Store`, Account workspace,
`MeetingHandle`, generation fence, SQLite trace callback, and a real runtime-thread to event-loop
handoff feeding one serialized per-Meeting publication worker.

- A prototype shared transport drove legacy and Phase-2 adapters through create, accepted frame,
  duplicate-frame conflict, snapshot/events, and Stop. Both adapters returned the same frame `200`,
  stable `v2_out_of_order_frame` `409`, and Stop `200`, then converged on closed version 2 with the
  same three public events. With each Phase-2 publication held, raw advanced `0→1→2` while
  durable/public stayed `0→0` then `1→1`; snapshot/events exposed only the prior durable state.
  Releasing each commit advanced durable/public together. The five-method seam is therefore
  sufficient; protocol and five-registry lifecycle belong behind the shared transport module.
- A history-open probe attached a fresh same-Account page as `viewing` with no mutation authority and
  no session-storage write; reload returned that observer page to `idle`. The originating page kept
  its existing controller when its history item opened, while reload removed control and restored
  only the stored read view. No second capture or authority state is needed.
- Holding a terminal transaction after its Meeting-status `UPDATE` but before transcript revision 2
  blocked concurrent snapshot, list, and authentication reads on the existing store lock. Releasing
  with rollback exposed `active`/version 1/`durable prefix`; releasing with commit exposed
  `completed`/version 2/`terminal revision`. Authentication returned the same Account only after
  either transaction ended. No mixed tuple or new persistence primitive was needed.
- With raw revision/event high-water already at `3/12` and its database commit held, four polls saw
  only durable/public revision `1`, event high-water `10`; SQL was 4 auth reads, 0 content reads,
  0 writes.
- Releasing revision 2 advanced durable/public to `2` and event high-water `11`; revision 3 remained
  queued behind it. Eight further alternating snapshot/event polls returned `200` with exactly 8
  authentication reads, 0 Meeting/transcript content reads, and 0 writes.
- Same-Account observer control returned `403`; foreign read/control returned `404` with no mutation.
- Revocation while revision 3 waited made the next request `401`; releasing the queued write hit the
  captured handle's authority-generation fence. Public/durable stayed at revision `2`/event `11`,
  status became `interrupted`, and the durable document contained revision 2 but no revision-3 text.
- A probe-only terminal transaction then injected process loss after writing both the final document
  and `completed`, but before commit. SQLite exposed the prior `active`/version-1/document tuple after
  rollback; the successful run exposed `completed`/version-2/final-document. It never exposed a mixed
  terminal status and transcript. The production handle may therefore absorb exactly this one
  owner-bound transaction; a separate final-document commit followed by `finish` is rejected.
- A simulated asynchronous finalizer advanced raw state through closed/`not_started`,
  closed/`running`, and closed/`final`. The momentary configured-finalizer `not_started` state stayed
  private. The changed stop-tail document committed as version 2, then public memory exposed
  closed/`running` while the Meeting row remained active. Holding the final transaction left that
  durable/public tuple unchanged; release atomically exposed `completed` version 3 with the
  finalizer's replacement words, then and only then advanced public memory.
- Disabling the publication bridge before a late runtime-thread callback left raw/durable/public at
  `3/2/2`; the late revision was ignored. Production therefore unbinds the identity-checked runtime
  observer only after every active binding is durably interrupted, before its event loop closes.

The sufficient binding is therefore the existing Sign-in session plus owner-bound Meeting handle,
an Account-partitioned in-memory Live registry, and one event-driven serialized durability bridge per
active Meeting. Public memory advances only after its structured transcript commit; closed/running
is a durable, nonterminal observation, while `final`, `failed`, or `unavailable` drives the atomic
terminal tuple. No additional page/device/view authority, authentication cache, polling timer, or
durable event table is justified.
