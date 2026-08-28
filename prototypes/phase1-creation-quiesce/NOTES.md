# Phase-1 creation-quiesce prototype

## Structural contract

- **Question:** can one durable host marker plus one counted admission scope stop new work in two
  independent production Phase-1 app instances while already-admitted work remains operable and
  drains visibly?
- **Minimum primitives:** marker existence is the cross-process/reboot fact; each process's entrant
  count spans request entry through work registration or transaction cleanup; content-free
  active/queued counts establish drain, including a closed Live session whose terminal finalizer is
  still running. The marker cannot count an upload already inside a process, and a count alone
  cannot cross processes or reboot, so neither primitive can be removed. Cleanup includes a job
  directory whose transaction constructor fails before returning. It is part of the existing
  admission boundary, not another counter; finalization status is existing Live runtime truth, not
  another lifecycle policy. The same ownership applies to a rerun directory until copy, hash,
  record publication, and queue registration have all succeeded. Live raw creation remains owned
  until authority binding and helper registration succeed; resume/render state remains old until
  its candidate durable state and worker registration can succeed. One short, nonblocking
  per-Job resume claim spans HTTP route entry through response construction; it identifies the one
  overlapping request allowed to attempt registration and releases on success, failure, or
  cancellation. It cannot be replaced by the existing JobManager mutation lock: if the first
  registered execution fails before a waiting request acquires that lock, the waiter is no longer
  distinguishable from a genuine later retry. The separate manager critical section remains the
  durable mutation boundary across failed-state observation, candidate persistence, registry
  publication, and enqueue; the request claim does not make that multi-effect transition atomic.
- **Invariants:** a quiesced marker rejects Live create, job create, rerun, resume, and render; it
  does not reject existing frames, heartbeat, snapshot, events, Stop, abort, reads, or downloads;
  marker uncertainty rejects creation; enable/disable is durable and idempotent.
  One failed job admits at most one execution from overlapping resume requests; a competitor
  receives typed conflict without waiting, cancellation releases the claim exactly once, and a
  genuinely later retry remains allowed. Save/enqueue failure restores the exact prior durable and
  in-memory state before admission closes.
- **Assumptions/unknowns:** the retained probe spawns two independent operating-system processes,
  each with a real `server.create_app` and gate, plus isolated production failure falsifiers. It
  exercises the absorbed marker, admission, route, runtime-status, Live, and job implementations
  with fake inference. Actual 4070 Ti filesystem and deployed unit behavior remain unmeasured until
  the reviewed prerequisite is deliberately deployed.
- **Falsifier:** after both processes report `quiesced`, entrant count zero, and active/queued zero,
  any newly registered work disproves this design. Invisible pre-admitted upload work or a blocked
  existing continuation also disproves it. A closed/running terminal pass reported as zero or a
  cancelled upload releasing its entrant before removing its transaction also disproves it.
  A staging-file constructor failure returning while its new job directory remains also disproves
  it. A pre-admitted rerun failing after a partial copy must likewise leave no new directory,
  registry entry, or queue entry. A Live bind refusal, resume save failure, or render save failure
  must leave no active undisclosed capture and no memory/disk/worker contradiction after entrant
  zero. Separate process PIDs must converge on marker enable/restart/disable while entrant counts
  remain local. Two overlapping resumes returning success even when the first execution has
  already failed, two queue entries, a cancelled claim blocking a later request, or drain zero
  while either accepted execution remains disproves resume ownership.
- **Tool decision:** a two-instance logic probe is necessary because a long upload crossing marker
  enable is the reachable race that distinguishes a marker alone from marker plus entrant count.
  Cancelling the production upload coroutine after transaction creation is necessary because only
  that path distinguishes `Exception` cleanup from `BaseException` cancellation; an orphan rejects
  exception-only cleanup. Holding the real terminal finalizer is necessary because only its
  `closed/running` interval distinguishes terminal HTTP status from completed drain work; a zero
  count there rejects status-only counting.
  Failing the real staging-file open is necessary because it is the only reachable point after
  directory creation but before the server owns an abortable transaction; a leftover directory
  requires strong construction cleanup in `JobManager`, not another server transaction wrapper.
  Failing a real partial rerun copy after marker enable is necessary because it distinguishes
  admission ordering from `create_job_from_file` ownership; any residual directory rejects the
  existing pre-return boundary.
  A concurrent Live revoke and injected resume/render saves are necessary because success tests
  cannot expose pre-registration mutation. Spawned process IPC is necessary because two app
  objects in one interpreter cannot prove cross-process marker visibility; PID-distinct runtime
  reports change the decision by rejecting the former proxy evidence.
  Holding the real worker on a second job while two HTTP resume requests interleave is necessary:
  ordinary success cannot expose duplicate queue registration hidden behind one JobRecord. Two
  successful responses or two later runner calls require the manager-owned transition boundary;
  one success plus one typed conflict preserves it. A second interleaving deliberately lets the
  first accepted execution fail before the competitor can mutate manager state. It is necessary
  because only that state proves the manager lock cannot remember overlapping request identity;
  `200/200` rejects lock-only serialization, while `200/409` followed by a successful sequential
  retry selects the short route claim. Raising `CancelledError` inside the real claim changes the
  decision if it cannot be reacquired, because then the claim has become persistent lockout rather
  than request ownership.
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
- Failing `.uploading` file open after job-directory creation returned typed HTTP `400`; the open
  saw entrant `1`, but no cleanup ran, and the request returned with entrant `0` plus the orphan
  directory. The extended probe exited nonzero with
  `constructor_failure_cleanup_ordered=false` while every prior predicate stayed green.
- A rerun entered while open, marker enable observed `quiesced` with entrant `1`, and a real file
  write copied `real` before raising. HTTP returned `400` with entrant `0`, unchanged registry and
  queue, but an extra partial job directory remained. The probe exited nonzero with
  `preadmitted_rerun_failure_cleanup_ordered=false` while every prior predicate stayed green.
- Concurrent device revoke after raw Live creation made binding return `403`; admission fell to
  zero while the undisclosed raw session remained active. A new device retry then produced two
  active sessions, and aborting the disclosed retry still left one.
- Resume save failure returned `400` with disk still `failed`, but memory already `queued`, queue
  empty, and retry unable to enqueue because it saw the false active status. Render save failure
  returned `400` with disk `waiting_review`, memory `rendering`, no thread, and retry refused `503`.
  The probe exited nonzero on all six failure/retry predicates.
- The former same-process proxy was replaced: distinct child PIDs independently reported open,
  shared quiesced state, local entrant `1/0`, quiescence after process replacement, and reopen after
  disable. These two new predicates passed before product correction.
- With the real worker held, two simultaneous HTTP resumes both observed the same failed job,
  returned `200`, and placed the same ID into the queue twice. The registry exposed only one queued
  JobRecord while the queue contained two executions; after release the runner processed both.
  The two new predicates made the retained command exit nonzero.
- Even after the manager mutation lock fixed that held-worker race, a faster interleaving remained:
  both routes entered admission, the first registered execution failed, and then the waiting second
  route acquired the manager lock. Both returned `200`, attempts advanced `2` to `4`, and the
  runner executed twice. The lock had serialized mutation but had lost the fact that the requests
  overlapped. The added predicates made the retained command exit nonzero.

These states are reachable cutover false-zero/orphan failures. The corrections only deepen the
existing drain/admission meanings: Live drain includes running terminal finalization; undisclosed
raw Live creation is aborted before admission closes; File creation owns every non-returned path;
and resume/render publish a copied candidate only after its durable transition succeeds. Resume
also composes a short per-Job route claim with its manager-local mutation section: the claim rejects
an overlapping waiter, while the manager section preserves exact durable and queue rollback.

## Verdict

**Accepted.** The command derived `PASS` from 46/46 predicates on Python 3.10.19 and 3.12.12 on
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
- A failed staging-file open saw its newly created job directory and entrant `1`; strong
  construction cleanup removed that directory while the entrant was still `1`, then HTTP returned
  `400` with entrant `0` and no filesystem material.
- A rerun pre-admitted at entrant `1`, marker enable changed its state to `quiesced`, then a real
  partial copy wrote `real` and raised. Cleanup removed the new directory while entrant remained
  `1`; HTTP returned `400` with entrant `0`, unchanged registry/queue, and only the source job dir.
- Concurrent revoke at raw Live authority binding returned `403`, but the owned raw session became
  `aborted` while admission remained `1`; after return active Live was `0`, no capture/helper
  registry disclosed it, and a fresh-device retry created and drained exactly one session.
- Injected resume and render saves each returned `400` with entrant `1` at failure, then entrant
  `0` with byte-for-byte old durable and in-memory state, no queued worker/thread, and zero active
  work. Retrying each operation registered exactly one worker and drained to terminal truth.
- Spawned child processes had distinct PIDs and converged on shared marker enable; one process's
  entrant stayed invisible to the other's local count. Replacing a child preserved `quiesced`, and
  disabling the marker reopened both surviving process views.
- Two held concurrent resume requests now produced exactly one `200`, one typed `409`, one durable
  attempt increment, and one queued runner call. Save and enqueue failure falsifiers restored the
  exact prior failed state; after release the sole accepted execution drained to terminal truth.
- In the fast-failure interleaving both routes reached admission `2`, but the route claim produced
  `200/409` even after the first execution became failed. Attempts stopped at `3` with one runner
  execution; after both requests returned, a new sequential retry succeeded as attempt `4` and
  drained. A synthetic cancellation released the same claim and immediate reacquisition succeeded.

The measured minimum is therefore one durable marker composed with one process-local counted
admission scope. A marker alone is rejected because it cannot expose a request already waiting on a
body; a counter alone is rejected because it cannot cross the two processes or survive reboot. The
absorbed production implementation uses this exact composition and the existing durable job state;
it adds no proxy, daemon, database, socket, queue, or retry framework.
