# Phase-2 Account lifecycle ordering

## Question

How can admitted Meeting creation and terminal settlement finish while their captured
authority is valid, before logout or host Account revoke removes that authority?

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --frozen --extra dev python prototypes/phase2-account-lifecycle/probe.py
```

The probe prints the complete contract, every interleaving result, durable SQLite state,
and a verdict derived from the load-bearing values. It exits nonzero on rejection.

## Minimum primitives and boundaries

1. A **counted async drain gate**, scoped separately to one Sign-in session and one
   Account authority generation. It owns admission only. A boolean cannot prove the
   count reached zero, so both count and condition are irreducible.
2. The **existing owned-work controls**: shared Live normal Stop and the process-owned
   File task registry. They own inference/audio settlement only. A lifecycle coordinator
   cannot reproduce their mixer, tape, archive, or cleanup policies.
3. One **final SQLite authority transaction**. It owns Account disable, generation
   increment, session deletion, and residual active-row interruption. Splitting this
   transaction would expose partial authority truth; moving it earlier invalidates the
   captured handles required for settlement.
4. One **service-owned Unix control command**. It transports host intent into the
   process but owns no policy. A direct-DB client cannot observe or drain in-process work;
   TCP, a daemon, or an admin webpage adds no required behavior.

Composition, not a fifth primitive, supplies the ordering: admit through binding/task
registration; close and drain; settle through existing owners; mutate durable authority last.

## Invariants

- Admission begins before authority resolution and ends after registration or failure.
- Logout affects only Live Meetings originated by one Sign-in session; other sessions and
  File tasks continue.
- Any logout settlement failure retains the cookie/session and reopens its session gate.
- Account revoke never reopens the old generation and returns only after durable terminal truth.
- Reallow creates fresh authority; stale handles and late work cannot commit.
- Another Account's sessions and Meetings never change.

## Assumptions and unknowns

- Issues 13, 16, and 17 settle Live/File transcript and audio algorithms; this probe must
  compose them, not re-litigate them.
- Socket framing and browser presentation are implementation surfaces, not evidence for
  lifecycle ordering.
- Cancellation, shutdown, real shared Stop, and socket errors remain unmeasured here and
  require focused production integration tests after this prototype accepts the policy.

## Falsifier

Reject the design if a pre-admitted create escapes enumeration; a create failure leaks the
count; concurrent logout/revoke pass a closing gate; logout failure revokes authority; Account
revoke leaves owned work active; late/stale work commits; reallow retains the generation; or
another Account changes.

## Tool decisions

- The asyncio interleaving probe is necessary because admission-versus-drain is the new
  policy. A missed registration or leaked count rejects the gate.
- Production `Phase2Store` and `MeetingHandle` are necessary because session, generation,
  transcript, audio, and cross-Account truth are SQLite behavior. Any stale commit or wrong
  Account mutation rejects the ordering.
- Focused production integration tests are necessary after PASS because shared Stop,
  background cancellation, socket lifecycle, and browser 401 handling are outside this
  prototype. A mismatch rejects or deepens the production seam.
- No browser, inference model, network, or benchmark corpus is necessary to decide this
  ordering; those results cannot change the gate design.

## Measured verdict

**PASS (2026-08-28).** The one-command run measured:

- a pre-admitted create registered before drain returned; a later create was rejected;
- an injected create failure released the count to zero and left the gate open;
- Account revoke waited for an admitted logout, then rejected another logout;
- successful logout settled two origin Live Meetings while its same-Account observer
  session and Meeting remained valid/active;
- injected durable Stop refusal retained the origin session;
- Account revoke rejected late and stale-handle commits, incremented generation `0 → 1`,
  permitted one fresh Meeting, and left the other Account active.

Verdict: implement one deep Account lifecycle module. Its opaque creation admission spans
authorization through binding/task registration; its logout and revoke operations compose the
existing Live/File owners before the final store authority mutation. The Unix socket remains a
thin host-control adapter to that module.

## Production absorption

The accepted primitive is absorbed in `app/phase2_lifecycle.py`; HTTP logout and the mode-`0600`
Unix control adapter call that one interface. Production creation resolves the exact Sign-in
session inside the admission context, so a caller cannot substitute another Account between the
session count and Account-generation count. A race either enters the Account count before close and
is drained through registration, or sees the closed generation and creates nothing.

Focused production tests measured the prototype's unmodeled boundaries:

- shared two-lane Live Stop is identical for HTTP and logout, including the existing route-entry
  Stop intent, v2 mixer/tape drain, terminal audio cleanup, and durable publication;
- every target Live binding and File task is synchronously fenced before the first settlement await;
- a held late File result cannot commit, while a failed first Live settlement leaves every later
  binding fenced and the Account durably enabled for explicit startup recovery;
- a cancelled logout reopens its session gate; a failed revoke keeps its Account-generation gate
  closed, and restart plus a fresh command completes the durable generation fence;
- the Unix socket is single-owner, `0600`, content-free, removed on shutdown, and cancels held
  handlers without leaking a lifecycle task;
- an Account `401` stops browser polling and closes local capture tracks/helper state without retry.

The one-command probe itself now owns `Phase2Store` with exception-safe close. A stale earlier run
was observed stuck in Python finalization with its SQLite worker and WAL descriptors alive; the
current command exits after printing PASS and also closes the worker on a falsifier/exception path.
