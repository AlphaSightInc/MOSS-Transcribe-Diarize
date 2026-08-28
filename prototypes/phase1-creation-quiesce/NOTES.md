# Phase-1 creation-quiesce prototype

## Structural contract

- **Question:** can one durable host marker plus one counted admission scope stop new work in two
  independent production Phase-1 app instances while already-admitted work remains operable and
  drains visibly?
- **Minimum primitives:** marker existence is the cross-process/reboot fact; each process's entrant
  count spans request entry through work registration or transaction cleanup; content-free
  active/queued counts establish drain, including a closed Live session whose terminal finalizer is
  still running. The marker cannot count an upload already inside a process, and a count alone
  cannot cross processes or reboot, so neither primitive can be removed. Cleanup is part of the
  existing admission boundary, not another counter; finalization status is existing Live runtime
  truth, not another lifecycle policy.
- **Invariants:** a quiesced marker rejects Live create, job create, rerun, resume, and render; it
  does not reject existing frames, heartbeat, snapshot, events, Stop, abort, reads, or downloads;
  marker uncertainty rejects creation; enable/disable is durable and idempotent.
- **Assumptions/unknowns:** the retained probe uses two concurrent real `server.create_app` process
  views plus isolated production upload-cancellation and terminal-runtime falsifiers. It exercises
  the absorbed marker, admission, route, runtime-status, and job implementations with fake
  inference. Actual 4070 Ti filesystem and deployed unit behavior remain unmeasured until the
  reviewed prerequisite is deliberately deployed.
- **Falsifier:** after both processes report `quiesced`, entrant count zero, and active/queued zero,
  any newly registered work disproves this design. Invisible pre-admitted upload work or a blocked
  existing continuation also disproves it. A closed/running terminal pass reported as zero or a
  cancelled upload releasing its entrant before removing its transaction also disproves it.
- **Tool decision:** a two-instance logic probe is necessary because a long upload crossing marker
  enable is the reachable race that distinguishes a marker alone from marker plus entrant count.
  Cancelling the production upload coroutine after transaction creation is necessary because only
  that path distinguishes `Exception` cleanup from `BaseException` cancellation; an orphan rejects
  exception-only cleanup. Holding the real terminal finalizer is necessary because only its
  `closed/running` interval distinguishes terminal HTTP status from completed drain work; a zero
  count there rejects status-only counting.
  Real inference, Chrome, and remote-host tools cannot change that state-ordering decision and are
  intentionally excluded.

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/phase1-creation-quiesce/probe.py
```

The command prints every load-bearing state and exits nonzero if any derived predicate fails.

## Review falsification before correction

The extended command exited `FAIL` before production was changed:

- A real `TerminalTranscriptFinalizer` was held in the production manual scheduler. Its session
  was `closed` with `finalization_status=running` and one pending pass, while `/api/runtime`
  incorrectly reported `active_live_sessions=0`. Releasing the pass produced `final` and zero.
- Cancelling the production upload coroutine after transaction creation showed entrant `1` and one
  staging job directory while held. Cancellation then produced no `UploadTransaction.abort` call,
  released the entrant to `0`, and left that directory behind.

Both states are reachable cutover false-zero/orphan failures. The correction may therefore only
deepen the two existing meanings: Live drain includes running terminal finalization, and upload
admission ends after every non-committed transaction has been aborted.

## Verdict

**Accepted.** The command derived `PASS` from 28/28 predicates on Python 3.10.19 and 3.12.12 on
2026-08-28.

- Before enable, two Live sessions were active and a held upload was visible as one entrant.
- After durable enable, both gates reported `quiesced`; the held upload remained one entrant.
- Both production `/api/runtime` responses exposed the exact per-process entrant, queued/active
  job, and active-Live counts before and after drain; a restarted process retained `quiesced`.
- The first production-path render falsifier exited `FAIL`: `Thread.start()` returned while the
  durable job still said `waiting_review`, so marker `quiesced` plus entrants `0` could falsely
  report no work. Moving the existing `rendering` transition before thread start made the held
  render visible as active, and its later execution drained the same job to terminal truth.
- Live create, job create, rerun, resume, and render each returned typed retryable `503`.
- Existing frame, heartbeat, snapshot, events, Stop, abort, and transcript download remained
  successful. Stop and abort used separate pre-quiesce Live sessions.
- Releasing the held upload changed the state from entrant `1` to entrant `0` plus queued job `1`;
  after worker release, queued/active jobs and active Live sessions were all exactly `0`.
- Marker/parent modes were `0600`/`0700`; a new app/gate instance remained quiesced; double disable
  reopened creation; an unreadable marker location reported `error` and failed closed.
- A held real terminal pass reported `closed/running`, pending `1`, and active Live `1`; after its
  release it reported `final`, pending `0`, and active Live `0`.
- A cancelled upload called `abort` while its admission entrant was still `1` and its staging path
  still existed; only after cleanup did the entrant become `0`, with no job directory remaining.

The measured minimum is therefore one durable marker composed with one process-local counted
admission scope. A marker alone is rejected because it cannot expose a request already waiting on a
body; a counter alone is rejected because it cannot cross the two processes or survive reboot. The
absorbed production implementation uses this exact composition and the existing durable job state;
it adds no proxy, daemon, database, socket, queue, or retry framework.
