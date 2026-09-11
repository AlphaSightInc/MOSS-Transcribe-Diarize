# Pre-Stop terminal refusal and proposed automatic restart

Code and local-test investigation complete; actual host cause remains unidentified.
No production changes or host operations.

F1 VERIFIED: the supplied 409 is emitted by Phase2Live binding authorization when
mutation is attempted against authority_closing, capture_fenced, terminal_persisted,
or a published capture status other than active. It does not name the reason or prove
that termination was spontaneous: an earlier Stop, abort, revoke, restart or lease
expiry also reaches this boundary.

F2 VERIFIED: terminal finalization is scheduled only after runtime Stop closes capture.
The previously enumerated finalizer runner/no-transcript/defect/proposal failures
therefore cannot initiate a pre-Stop terminal transition. Canonical decoder errors
are a different path, despite also involving a runner.

F3 CODE TRACE: the shipped ControlPanel handles terminal observation by stopping its
poller, closing/discarding the capture client, clearing captureMeetingId, and showing
terminal UI. createSession is called by startCapture after explicit readiness/start;
no automatic create is present in handleTerminal. Testing this boundary next.

F4 CODE TRACE: meeting_modes_history_restart reuses _live_id('a'), then waits for a
file/URL batch before Stop. Its predecessor predicates create/use the same cached ID.
The collector does not maintain continuous heartbeat on that cached session while
waiting. A lease-expired or previously terminal cached ID is a reachable explanation;
the particular host session's lifecycle events remain necessary to distinguish it.

## Measured findings

F5 VERIFIED: local Account HTTP tests reproduce exactly
`409 {"detail":"live Meeting is terminal."}` after either helper lease expiry
WITHOUT Stop or an earlier explicit abort. Both snapshots still say
finalization_status=not_started. Thus the new body establishes a terminal/fenced
binding, not which transition caused it. The lease test uses an explicit 0.1-second
local lease to exercise the production expiry path; it does not assert the host lease.

F6 VERIFIED: audio_durability_download invokes meeting_modes_history_restart if the
seeded file/live lists are missing. That method populates those lists only after a
successful Stop. Consequently an earlier meeting_modes failure can leave its cached
A ID in place, and the later audio predicate calls Stop against it again. An earlier
Stop timeout itself terminalizes the runtime; lease expiry, crash/restart or other
fencing are alternative explanations. We need the FIRST meeting_modes Stop refusal
and that ID's lifecycle, not only the subsequent audio predicate's refusal.

F7 VERIFIED: terminal callbacks in the actual ControlPanel stop polling, close local
capture, clear the active capture ID and show Reset capture. Expanded tests cover
revoked authority, helper_lease_expired and canonical decode failure; createSession
remains called exactly once. CaptureClient's terminal 409 handler clears delivery
state so a CALLER MAY recreate, but does not call createSession itself. Only the
explicit startCapture path calls it in the shipped frontend. The automatic-restart
hypothesis is rejected for this client; an external helper or manual operator reset
was not observed and is not inferred.

## What can terminate capture before Stop?

| Path | Pre-Stop effect / relevant evidence |
| --- | --- |
| Helper heartbeat lease expires | Account create arms the lease, even before first heartbeat. Expiry aborts/fences capture with helper_lease_expired; demonstrated locally. The collector sends heartbeats with audio frames, but not continuously while waiting for unrelated file/URL work. |
| Canonical provider outage or fatal error | LiveCoordinator tries each span twice for transient errors. Third consecutive unanswered span raises LiveProviderError; runtime records terminal_failure and exposes status=failed. Successful decode resets the count. Three capped spans represent at most roughly 7.5 seconds of audio, not a wall-clock deadline. |
| Canonical identity/commit invariant failure | Failed atomic submission, stale/invalid preparation, unresolved frozen spans without queued work, or other fatal canonical pipeline exception can fence the session. Inspect failure.kind/code/detail; this differs from ordinary speaker abstention. |
| Durable publication or capture/mixer failure | Failed persistence, lost authority, missing source/mix integrity, terminal helper/lane health, operator interruption and service shutdown/recovery can interrupt a live binding. Inspect persistence_failure, terminal_failure and v2 terminal_reason. |
| Earlier explicit Stop/abort/revoke/restart | Also makes a later mutation return the supplied 409. A failed Stop deadline is itself a terminal failure, so a second Stop's refusal cannot diagnose the first attempt. |

Applicable at any supported corpus duration; elapsed duration alone does not select
one. Quality has active frame/heartbeat delivery during replay, unlike the cached-ID
waiting pattern in meeting_modes. Its strict settle loop does not refresh heartbeats,
so a drain longer than the remaining configured lease is another conditional exposure,
not a measured explanation of this host's failure.

Important exclusions: typed empty canonical output is handled as an empty/salvaged
span, not automatically a fatal outage. An ordinary failed rolling window retains the
surface and stalls rolling planning; it does not by itself abort capture. Failed final
decode/no usable final transcript/finalizer defect occur only after Stop schedules the
terminal pass. A concurrent session failure can suppress an already-running final
proposal, but then that failure occurred AFTER Stop began the pass. Do not collapse
these into one generic "decoder failed" state.

## Identity hypothesis

Runtime.create constructs a new LiveSession and a fresh identity preparer per meeting.
That resets session-local speaker tracking, while the account's enrolled voiceprint
bank remains durable and can recognize a speaker again. Local speaker identifiers
may reuse the same strings in different meetings; they are not globally increasing
IDs. On explicit Start the UI calls resetSessionState, which clears the previous
transcript display. There is no demonstrated automatic session recreation or
cross-session transcript concatenation to turn one continuous meeting into three
speaker labels. The operator symptom remains unexplained; compare meeting IDs,
terminal events and any explicit reset actions before asserting this cause.

## Relationship to quality

The audio predicate's late 409 and quality's finalization_status=failed remain separate
observations. The latter indicates a scheduled terminal pass ended unsuccessfully
(or was suppressed after a concurrent failure), which is downstream of runtime Stop.
It does not prove an early self-termination. Existing HTTP tests from f5d17270 show
Stop 200 followed by failed finalization and preserved rolling text. The new lease
and abort tests show the opposite distinction: pre-Stop termination with not_started.
One infrastructure problem could affect both, but no common cause is established.

Needed existing-run evidence: the original meeting_modes refusal; its meeting ID and
first terminal/persistence/helper event; the quality case ID and
terminal_finalization_failed outcome/reason/refusal plus terminal_failure. No fresh
host run or decoder is needed to read those records. No production fix is justified
until the failing path is identified.

Validation so far: 15 Python tests (new pre-Stop HTTP cases plus helper failure suite),
3 runtime failure tests, and 64 frontend capture/poller/ControlPanel tests passed.
The initial frontend parameterization retained a hard-coded display-message assertion;
corrected that test expectation to the parameter, then all three reasons passed.
Only tests and this report changed. No host operations or identity-policy changes.

Additional production-pipeline outage tests: 3 passed (outage threshold, recovery
reset, structured outage diagnostics). Total focused validation: 21 Python + 64
frontend tests passed.
