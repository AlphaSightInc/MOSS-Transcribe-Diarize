# Phase-1 creation-quiesce prototype

## Structural contract

- **Question:** can one durable host marker plus one counted admission scope stop new work in two
  independent production Phase-1 app instances while already-admitted work remains operable and
  drains visibly?
- **Minimum primitives:** marker existence is the cross-process/reboot fact; each process's entrant
  count spans request entry through work registration; content-free active/queued counts establish
  drain. The marker cannot count an upload already inside a process, and a count alone cannot cross
  processes or reboot, so neither primitive can be removed.
- **Invariants:** a quiesced marker rejects Live create, job create, rerun, resume, and render; it
  does not reject existing frames, heartbeat, snapshot, events, Stop, abort, reads, or downloads;
  marker uncertainty rejects creation; enable/disable is durable and idempotent.
- **Assumptions/unknowns:** the retained probe uses two real `server.create_app` instances and the
  absorbed production marker, admission, route, runtime-status, and job implementations with fake
  inference. Actual 4070 Ti filesystem and deployed unit behavior remain unmeasured until the
  reviewed prerequisite is deliberately deployed.
- **Falsifier:** after both processes report `quiesced`, entrant count zero, and active/queued zero,
  any newly registered work disproves this design. Invisible pre-admitted upload work or a blocked
  existing continuation also disproves it.
- **Tool decision:** a two-instance logic probe is necessary because a long upload crossing marker
  enable is the reachable race that distinguishes a marker alone from marker plus entrant count.
  Real inference, Chrome, and remote-host tools cannot change that state-ordering decision and are
  intentionally excluded.

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/phase1-creation-quiesce/probe.py
```

The command prints every load-bearing state and exits nonzero if any derived predicate fails.

## Verdict

**Accepted.** The command derived `PASS` from 24/24 predicates on 2026-08-28.

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

The measured minimum is therefore one durable marker composed with one process-local counted
admission scope. A marker alone is rejected because it cannot expose a request already waiting on a
body; a counter alone is rejected because it cannot cross the two processes or survive reboot. The
absorbed production implementation uses this exact composition and the existing durable job state;
it adds no proxy, daemon, database, socket, queue, or retry framework.
