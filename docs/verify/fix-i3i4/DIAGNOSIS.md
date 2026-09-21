# I3/I4 diagnosis

**Verdict: all three signals reproduced.** S1 and S2 are release-blocking; S3 is a
bounded one-boot cleanup delay and is minor. This branch changes no production code.

## Contract

- **Structural question:** can retained File owners and qualification rows always reach
  an owner-specific, truthful outcome when one operation stalls or fails?
- **Minimum primitives:** a retained owner reservation, its independent validation,
  one proxy attempt with row/request identity, durable Meeting status, and guarded
  retained-directory removal. Removing any one loses ownership or terminal truth.
- **Invariants:** one owner cannot starve another; transport failure is infrastructure
  `INCOMPLETE`, never product `PASS`/`FAIL`; fallback-terminalized retained work is
  reclaimed in the same boot; validation makes zero decoder calls.
- **Assumptions/unknowns:** the production frequency of a permanently stalled
  filesystem read is unmeasured. The correct validation concurrency bound is also
  unmeasured and must be selected in a prototype, not guessed here.
- **Falsifier:** the three strict controls XPASS after the later implementation, while
  focused and full backend suites remain green.
- **Tool decision:** prescribed-runtime pytest reaches the real coordinator, proxy,
  and FastAPI lifespan. S2 uses only a loopback fake upstream. No decoder, provider,
  external network, GPU, or tunnel is needed.

## S1 — stalled validation starves later owners

- **Reproduced: YES. Severity: BLOCKING.** Owner 1 blocked inside validation. After a
  0.2 s validation bound plus a 0.2 s resume bound, owner 2 was
  `(validated=False, resumed=False)`. Both owners were already reserved and therefore
  excluded from generic fallback. An operator sees owner 2 remain `active` with no
  progress for the life of this process even though owner 2 is healthy.
- **Trace:** `moss_transcribe_diarize/app/phase2_file.py:226-258` performs validation
  and waits for start; `:284-306` awaits claims serially. Violating control:
  `tests/phase2/test_fix_i3i4_diagnosis.py:25-96`.
- **Smallest fix:** start one task per claim behind a measured small semaphore; each
  task retains the existing `_interrupt_refused_reservation` /
  `_fail_retained_reservation` outcomes. Do not use an invented timeout: cancelling
  `asyncio.to_thread` does not stop the filesystem thread and could release/remove its
  owner while that thread still reads it. Validation remains decoder-free, so decoder
  in-flight `<=2` is unchanged.
- **Risk:** the semaphore bound is a new policy and needs an offline owner-count/stall
  prototype. Cancellation must retain each reservation lock until its validation task
  has actually settled.

## S2 — proxy upstream error is counted complete

- **Reproduced: YES. Severity: BLOCKING.** Loopback attempts returned
  `503, 502(timeout), 200(retry), 200(duplicate request id)`. The proxy reported
  `accepted=4, completed=4`; every event omitted both row owner and request id. The
  summaries accounting therefore projected `PASS`, and a default bundle with green
  product gates also ended `PASS`, not infrastructure `INCOMPLETE`.
- **Trace:** `tools/qualify/decoder.py:31-66` increments `completed` in `finally` for
  every accepted attempt; `:84-88` logs no owner/outcome/id.
  `prototypes/feature-rows/run.py:38-50,105-126` treats every `end` as complete;
  `tools/qualify/run.py:620-651` considers only budget rejection before the gate
  verdict. Violating control: `tests/phase2/test_fix_i3i4_diagnosis.py:99-227`.
- **Smallest fix:** have the proxy record content-free `row`, request id, upstream HTTP
  class/transport-error outcome, successful completions, and duplicate/retry attempt
  counts. The summaries row and `Bundle.cleanup` must force `INCOMPLETE` when their
  owned attempts contain transport/upstream errors or accounting ambiguity. Preserve
  both attempt counts and distinct request-id counts rather than conflating them.
- **Risk:** callers may omit request ids, and retries legitimately reuse logical
  identity. Missing identity must become explicit unowned/ambiguous infrastructure
  evidence, not be guessed or treated as product failure.

## S3 — fallback reclaim occurs one boot late (L-1)

- **Reproduced: YES. Severity: MINOR.** A real `create_phase2_app` lifespan started
  with an active File Meeting and an owner directory missing `owner.json`. Boot 1
  durably made the Meeting `interrupted` but left the directory. Boot 2 reclaimed it.
  The visible Meeting truth is correct; only stale retained disk state survives one
  boot.
- **Trace:** `moss_transcribe_diarize/app/phase2.py:2077-2090` reclaims before resume
  and fallback, then calls the startup-empty refused-owner path. The missing manifest
  is refused at `phase2_file.py:211-220`; reclaim paths are `:339-355`. Real-lifespan
  control: `tests/phase2/test_fix_i3i4_diagnosis.py:230-278`.
- **Why the call moved:** I3 backgrounded validation, so the generic terminal sweep was
  moved ahead of reservation as a precaution against touching a newly resumed owner.
  No additional race was found: the sweep selects durable terminal Meetings, while a
  reserved resumable owner remains active; terminal task cleanup is already guarded
  and existence-idempotent. Therefore no unsupported fourth race test was added.
- **Smallest fix:** keep the early sweep, then after generic fallback perform a second
  sweep of `terminal ∩ on-disk − reserved` through the existing
  `_remove_retained_work_dir` primitive.
- **Risk:** omitting `− reserved` could touch a background claim that terminalized
  concurrently. Compute the set in the single startup event-loop turn and retain the
  existing guarded removal.

## Reproduction

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 \
  /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python \
  -m pytest -q -p no:cacheprovider \
  tests/phase2/test_fix_i3i4_diagnosis.py -rxX
```

Observed: `3 xfailed in 4.35s`. With `--runxfail`: `3 failed`, each at its named
assertion. Calls: decoder `0`, provider `0`, external network `0`, tunnel `0`.

Focused gate: `47 passed, 3 xfailed, 0 failed in 9.28s`. Full prescribed backend:
`2,199 passed, 5 skipped, 5 xfailed, 0 failed, 37 subtests in 248.33s`; the other
two xfails are the existing Jamie controls. The first full attempt had 10 Node-reader
failures because this fresh clone lacked the COMMON-prescribed shared
`frontend/node_modules` symlink. After adding that ignored clone-local link, the 20
affected controls passed and the final full run above was green.
