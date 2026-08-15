# PRD — x3-capture-health

## Goal

Capture health claims to be server-authoritative and is not.

**1. It is dead code at the route.** `live_transport.py:725` calls
`project_live_capture_status(presence)` — the fusion parameter is keyword-only with a `None`
default and the only call site never passes it. Its unit test passes by calling the function
directly with an argument production never supplies. **You now own `live_transport.py`; wire it.**

**2. Even wired, it fuses one fact out of six.** `live_capture_status.py:97-100` is a single OR
over a **monotonic** counter: "has any lane ever accepted a frame". Measured consequences — all of
these currently report *"Capturing microphone and shared audio."*:
- mic sending, system lane never sent a single frame
- one frame each, then nothing ever again (accepted_samples never decreases, and the function
  takes no clock, so status is permanently "recording" even if capture died 20 minutes ago)
- 1000 frames all `silent=True`
- a lane wedged at a sequence gap with 58 consecutive rejects
- the server's own lane `health="failed"` — **already in the snapshot it receives, and ignored**

Fuse what the server actually knows: frame arrival *recency*, sequence gaps, per-lane accounting,
sustained silence, backpressure, and the lane health it is already handed.

**3. Every `failed` outcome is unreachable.** A terminal helper failure releases the access
registry, so the next `/snapshot` returns **403** and no server string survives — deny the mic
prompt and the user sees nothing. The `stopped` path has the same problem after a server stop.
Decide and implement how a client learns why its session died: either keep the session readable
through terminal state, or return the reason on the 403. Do not leave the user with nothing.

Note `live_capture_status.py:9` declares only `starting|recording|failed`, dropping the
reference's `awaiting_audio` — which is exactly the server-unique observation being discarded.

**Gate:** `.venv/bin/pytest -q tests/test_live_capture_status.py tests/test_live_api.py` plus a
committed probe showing, through the real route, that each of the five scenarios above no longer
reports healthy, and that a mic-denied session yields a readable reason.


## Guardrails (enforced — the loop stops on violation)

`RALPH_PREFLIGHT_REQUIRED=1` runs `scripts/afk-guardrails/preflight.py x3-capture-health` before every
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
`evidence/phase1/x3-capture-health/` with their probes committed · an issue-style summary in
`progress.txt` stating criterion-by-criterion what proves it and what is not covered.
