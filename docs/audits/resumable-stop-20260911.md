# Stop wait expiry must not destroy a Meeting

## Diagnosis and contract

Reproduced without vLLM using the real runtime and a held decoder. Existing tests
explicitly expected TimeoutError to call `_fail`, discard late results and keep
accounted samples at zero. The three new retry/automatic-completion/abort regressions
first failed on that exact terminal_failure assertion.

Ranked hypotheses: caller wait and session lifetime were conflated; zero wait could
expire before scheduling newly frozen tail work; HTTP/UI could independently mistake
pending completion for failure. Code and local tests confirmed all three boundaries.

Primitives: one server-owned Stop operation, independent bounded request waiters,
existing work/publication locks, and existing terminal failure/abort fences. Caller
wait expiry cannot cancel the operation or release its evidence. Stop is idempotent
while draining. No new frames enter after Stop starts. Identity/canonical ordering,
preview span identity, and causal evidence remain unchanged. Falsifiers: a timed-out
caller terminalizes, a later Stop duplicates work, or abort permits late publication.
Controlled worker tests distinguish these without provider latency or host operations.

## Fix

Runtime retains one shielded Stop task per session. It flushes and schedules the tail,
waits for canonical and rolling drain, and follows the original identity/terminal path.
A request timeout raises `LiveServiceStopPending` without calling `_fail`; real worker
exceptions still follow the original failure path. Explicit abort keeps its existing
fence and wakes the drain. A cancelled request likewise cannot cancel server work.

HTTP returns 202 with `code=stop_in_progress` and `retryable=true` for wait expiry.
The durable-finalization wait uses the same request budget. A subsequent Stop can join
the drain; polling observes eventual terminal publication without another Stop.
Already-terminal authorization rules remain unchanged; a completed Meeting is observed
through its snapshot/history rather than requiring another successful Stop request.

A concurrency test also exposed `sync_and_flush` waiting for a raw event after terminal
publication had already fenced further events. The existing `terminal_persisted` flag
now satisfies that wait, only after durable completion.

The account client accepts only that explicit 202 shape and keeps its existing poller
running in stopping state. Its Stop network timeout now covers the requested wait plus
one second transport grace, instead of expiring after one second while requesting five.
Five seconds remains a bounded client wait/local delivery allowance; no manifest-based
increase is required to keep server drain alive. The existing terminal poll continues
through finalization_status=running. Genuine HTTP failures still surface as errors.

## Validation

Local runtime: expired wait then re-Stop; expired wait then autonomous completion;
abort during stopping with no late canonical commit; genuine provider failure after
expiry; one preview per span; new-frame refusal without terminalization.
Real account HTTP tests: default zero deadline returns explicit 202, retry or polling
reaches durable completion, and a held terminal finalizer returns 202 then publishes.
Frontend: explicit 202 handling, stopping UI/poller continuation, and final callback.
Full application Python suite: **1,293 passed, 2 skipped, 37 subtests passed**
(21 warnings, 92.11 seconds). Frontend: **184 passed** across 23 files. Typecheck
and production build passed. No host operations, identity policy or quality
bounds changes. The local reproduction uses a controlled decoder, not a new vLLM run.

Prevention: the old timeout tests encoded permanent loss as expected behavior. The
replacement contract tests distinguish a caller ceasing to wait from an explicit
abort, and test later completion rather than only the immediate exception.

After the required pre-push rebase onto f038bd57 (including the concurrent LLM relay),
only generated assets conflicted and were rebuilt. Final combined validation:
**1,333 Python tests passed, 2 skipped, 37 subtests passed** (21 warnings, 87.77 seconds);
**195 frontend tests passed**. Typecheck/build passed. The count increase includes the
concurrent relay tests; no host qualification is claimed.
