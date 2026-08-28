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
2. The **existing owned-work controls**: shared Live normal Stop, its synchronous
   result/publication fence and phase-aware worker shutdown, the process-owned File task
   registry, and fixed owner/mode recovery. They own inference/audio settlement only. A
   lifecycle coordinator cannot reproduce their mixer, tape, archive, or cleanup policies;
   a generic worker cancel cannot distinguish rollback-safe SQLite from live filesystem I/O.
3. One **final SQLite authority transaction**. It owns Account disable, generation
   increment, and session deletion after asserting zero active rows. Splitting this
   transaction would expose partial authority truth; terminalizing residual rows inside it
   would bypass their audio/cleanup owners and make uncertainty unreachable.
4. One **service-owned revoke settlement task**, from the first Account fence through final
   durable authority mutation. The lifecycle holds it strongly and product lifespan joins it.
   A cancellable socket handler cannot own filesystem threads, File cleanup, or terminal truth.
5. One **Unix control transport**. It transports host intent into the
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
- A queued or in-flight Live publication is synchronously fenced before the first settlement await.
- Terminal audio publication is joined, never cancelled, before durable authority changes.
- Only an in-flight SQLite transcript commit is cancelled because its transaction rollback is
  the atomic boundary; idle and terminal workers receive a queued exit and are joined.
- Client, handler, and control-server cancellation cannot cancel accepted Account settlement;
  product lifespan joins it before Live, File, or Store shutdown.
- Account-revoke interruption persists the last durable transcript document. A raw snapshot may
  choose the maximal audio prefix, but fenced raw text never becomes durable.
- Interruption changes verified complete audio to `partial` by state only before terminal status.
- Cleanup uncertainty leaves the Meeting active and durable Account authority unchanged.
- Reallow creates fresh authority; stale handles and late work cannot commit.
- Another Account's sessions and Meetings never change.

## Assumptions and unknowns

- Issues 13, 16, and 17 settle Live/File transcript and audio algorithms; this probe must
  compose them, not re-litigate them.
- Socket framing and browser presentation are implementation surfaces, not evidence for
  lifecycle ordering.
- Cancellation, shutdown, real shared Stop, socket errors, and browser teardown are measured by
  focused production integration tests; they are not unknowns remaining in this probe verdict.

## Falsifier

Reject the design if a pre-admitted create escapes enumeration; a create failure leaks the
count; concurrent logout/revoke pass a closing gate; logout failure revokes authority; Account
revoke leaves owned work active after verified cleanup; late/stale work commits; an interrupted
artifact stays `available`; cleanup uncertainty becomes terminal or disables authority; a queued
publication commits after the synchronous fence; reallow retains the generation; or another
Account changes. Also reject it if held terminal audio is cancelled/orphaned or Account authority
changes before its publication worker joins; handler cancellation abandons Live/File cleanup; or
raw text from a cancelled transcript transaction appears in the interrupted document.

## Tool decisions

- The asyncio interleaving probe is necessary because admission-versus-drain and phase-aware
  publication shutdown are the new policies. A missed registration, leaked count, cancelled
  terminal-audio operation, cancelled service settlement, fenced transcript, or authority mutation
  before worker join rejects the composition.
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
  session and Meeting remained valid/active; the derived verdict checks both exact Meeting IDs
  and durable `completed` states, so a no-op Stop exits nonzero;
- injected durable Stop refusal retained the origin session;
- verified File metadata changed only `available → partial` before `interrupted`, preserving path,
  byte count, duration, format, sample rate, channels, and bit rate;
- persistent cleanup uncertainty left an unregistered Live row active and authority valid; the
  measured retry settled it before authority changed;
- both Live bindings were synchronously result-fenced before a held first settlement failed, and
  the second queued publication committed no durable revision;
- an idle worker exited by queue without cancellation; a held SQLite transcript commit was
  cancelled and rolled back with no durable version, and Account interruption retained the exact
  prior durable document rather than the fenced raw words;
- cancelling the control handler left service-owned revoke settlement alive; lifespan join waited
  while held terminal audio remained running, then observed exactly one publication, raw-stage
  removal, Meeting completion, worker join, and authority disable
  (`fence → audio → raw removal → Meeting → join → authority`);
- the same handler cancellation with a held File runner retained its registry entry and `input.wav`
  until runner return, then removed both, interrupted the Meeting, and disabled authority before
  lifespan join returned;
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
- the Live fence cancels only an in-flight SQLite transcript commit, whose transaction rollback is
  atomic; idle and terminal-settlement workers receive a queued exit and are joined, so terminal
  filesystem publication cannot be orphaned while queued/in-flight revisions remain fenced;
- accepted Account revoke is a lifecycle-owned task shielded from the Unix handler and held until
  completion; lifespan joins it before Live/File shutdown or SQLite close, covering held terminal
  audio and held synchronous File runners without a second scheduler or retry framework;
- Account revoke supplies the last durable transcript document to interrupted settlement; the raw
  runtime snapshot remains available only for maximal accepted audio-prefix recovery;
- File interruption and fixed File/Live recovery share one guarded state-only audio downgrade;
  metadata and canonical MP3 bytes remain identical while completeness becomes `partial`;
- transient unregistered Live-create cleanup is recovered by the same revoke command; persistent
  uncertainty fails the command with Meeting active, Account/session generation unchanged, and the
  in-process gate closed; startup recovery plus a fresh command then succeeds;
- the final authority transaction has no residual terminalization path and refuses any active row;
- a held late File result cannot commit, while a failed first Live settlement leaves every later
  binding fenced and the Account durably enabled for explicit startup recovery;
- a cancelled logout reopens its session gate; a failed revoke keeps its Account-generation gate
  closed, and restart plus a fresh command completes the durable generation fence;
- the Unix socket is single-owner, `0600`, content-free, and removed on shutdown; it may cancel a
  held handler, but cannot cancel the lifecycle-owned settlement that lifespan then joins;
- an Account `401` stops browser polling and closes local capture tracks/helper state without retry.

The one-command probe itself now owns `Phase2Store` with exception-safe close. A stale earlier run
was observed stuck in Python finalization with its SQLite worker and WAL descriptors alive; the
current command exits after printing PASS and also closes the worker on a falsifier/exception path.
