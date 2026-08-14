# PRD — x2-capture-client

## Goal

The capture client's audio core is a **faithful, correct port** — one AudioContext, worklet-driven
POSTs with no timers anywhere, clock anchored once and advanced arithmetically, exactly the nine
v2 keys matching the server's real validator. Keep all of that. Three things around it are wrong.

**1. One 429 permanently kills a lane.** `frontend/src/capture/captureClient.ts:388` increments the
sequence, `:391` fires the POST unawaited, and `:394-412` swallows *any* non-OK response into
`droppedFrames++`. There is no 429 retry, no 409 resync, no 400 stop.

The subtle part — **the two 429 sources need opposite responses**: lane-capacity 429 raises
*before* `lane.next_sequence += 1`, so the sequence is NOT consumed and the frame **must** be
resent; queue backpressure raises *after* `v2_session.accept`, so it IS consumed and the frame
must **not** be resent. Wrong either way → `LiveV2OutOfOrderFrameError` → 409 forever. They are
distinguishable via `failure.code`. Note a third 429 exists with **no** `failure` key
(`live_transport.py:280-284`) — handle it without wedging.

Also: `void this.postFrame(...)` is fire-and-forget with no per-lane serialization, so two
in-flight POSTs can reorder and 409 with no error at all. Serialize per lane.

**2. The whole browser failure vocabulary is dead.** `:468-477` hardcodes `state: "capturing"` and
`failure_code: null`. No `track.onended`, no `AudioContext` `statechange`, no clipping detection,
no silent-mic detection. So all seven `browser_*` codes the server understands can never be
emitted, and `stop()` sends no final `stopped` heartbeat — meaning the one genuinely-fixed
server-side behaviour (clean stop → "Audio capture stopped.") can never be triggered.

**3. Lane loss is unimplemented.** `deviceEpoch: 1` is a constant; `discontinuity` is never set
true. A mic replug produces a silent timeline splice the server cannot detect.

Two smaller ones: `:153` tags every frame with the *requested* sample rate, never
`context.sampleRate`, so a browser that hands back a different rate mislabels every frame
silently. And `:375` uses `level > 0` for the preflight signal gate where the verified reference
uses `>= 1e-4` — any dither satisfies `> 0`, so the gate is a no-op.

**Scope note:** the orchestrator owns the rest of `frontend/src/` and will mount your client into
the app. Export a clean, documented API and do not edit outside `frontend/src/capture/` and
`frontend/public/worklets/`.

**Gate:** `npm --prefix frontend run typecheck && npm --prefix frontend test`, plus tests for the
heartbeat path (currently zero — nothing would fail if someone reintroduced `setInterval`) and for
each 429/409/400 branch.


## Guardrails (enforced — the loop stops on violation)

`RALPH_PREFLIGHT_REQUIRED=1` runs `scripts/afk-guardrails/preflight.py x2-capture-client` before every
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
`evidence/phase1/x2-capture-client/` with their probes committed · an issue-style summary in
`progress.txt` stating criterion-by-criterion what proves it and what is not covered.
