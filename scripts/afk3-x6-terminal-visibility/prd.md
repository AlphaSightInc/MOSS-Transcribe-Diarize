# PRD — x6-terminal-visibility

## Goal

**A terminally-failed live session renders to the user as healthy, and is polled forever.**

`live_service_runtime.py:979-989` `_fail()` sets `state.terminal_failure` and records a
`terminal_failure` / `session_aborted` event — but it **does not change `LiveSnapshot.status`,
which stays `"active"`**. Any client that gates on status therefore never learns the session died.

Concretely: vLLM returns a provider error mid-meeting. The server marks the session terminally
failed. The user's browser shows "active", a frozen transcript, no error, and hammers `/snapshot`
+ `/events` twice per second indefinitely. This is the same shape as the "ordinary overload
converting into dead sessions" P0 that already reached `dev` once.

Decide the contract and implement it: either `status` reflects terminal failure, or the snapshot
carries a first-class terminal indicator that every client is expected to read. Whichever you
choose, it must be **discoverable from the snapshot alone** — the existing `/live` portal manages
this by reading `snapshot.terminal_failure` (`live_portal.py:492`), so at minimum make that the
documented, tested contract rather than folklore.

**Second defect, same file family:** `live_portal.py:179,478-480` has the inclusive-cursor bug
that was fixed in the capture harness — `eventSequence` starts at 0 while the server's `events()`
filter is `seq >= since_seq` and seq 0 is always `session_created`, so that event is fetched and
discarded forever and the cursor never advances off it. It was correctly reported rather than
edited by a ticket that did not own the file. **You own it. Fix it.**

Be careful: `_fail` is on the hot path and several tests assert current snapshot shapes. Changing
`status` semantics may ripple — if it does, that ripple is the point, but every affected assertion
must be re-reasoned rather than mechanically updated.

**Gate:** `.venv/bin/pytest -q tests/test_live_service_runtime.py tests/test_live_api.py
tests/test_live_portal.py` plus a committed probe showing a terminally-failed session is
discoverable from a single `/snapshot` read, and that the portal renders seq 0 exactly once.


## Guardrails (enforced — the loop stops on violation)

`RALPH_PREFLIGHT_REQUIRED=1` runs `scripts/afk-guardrails/preflight.py x6-terminal-visibility` before every
iteration: prerequisites, file ownership, banned patterns, and any evidence artifact citing a
probe not in the tree. You may only modify the paths this ticket owns
(`scripts/afk-guardrails/ownership.json`), plus your own loop dir, `evidence/phase1/`, `docs/`,
`tests/`. If you need a file you do not own, say so on the issue — do not edit it.

## Rules that come from real failures on this repo

1. **Do not certify yourself.** Emit `<promise>COMPLETE</promise>` only when the gate below
   passes with raw artifacts behind every claim. A separate reviewer reads them. Last round's
   honest blocked-stops were correct behaviour; false completions are the failure being fixed.
2. **If a test would pass with the feature deleted, it is not a test.** Real examples caught
   here: an assertion that sequence numbers are contiguous when the code makes them contiguous
   by construction; `code in FROZEN_SET` where the parametrize list *is* that set; a fairness
   "measurement" with zero decode cost.
3. **Build the thing, then measure it.** Two tickets shipped evidence scaffolding and no
   deliverable.
4. **Every artifact names a committed, re-runnable probe.** Three artifacts citing deleted
   probes were quarantined today; preflight now fails on this.
5. **Say exactly what you ran** and what your tests do *not* cover.

## You do NOT merge

Work only on your branch. Do not push to `dev`, do not take the merge lock. When your gate
passes, stop and report. The orchestrator reviews, then reconciles. You may
`git merge --no-edit dev` *into* your branch and must validate on that merged result.

## Definition of done

Gate passes · validation green after merging `dev` in · raw artifacts under
`evidence/phase1/x6-terminal-visibility/` with their probes committed · an issue-style summary in
`progress.txt` stating criterion-by-criterion what proves it and what is not covered.
