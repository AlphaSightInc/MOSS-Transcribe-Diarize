# PRD — x1-frame-drop

## Goal

**P0 you must fix first: this branch's predecessor silently discards 29–36% of captured audio.**

`prototypes/browser-capture-feasibility/capture_pipeline_page.html:962`
```js
if (st.sendPaused || st.sendInFlight) return;
```
The worklet callback **drops the PCM** when a POST is in flight. Proven from the branch's own G7
artifacts: 3194/4977 and 3499/4959 frames admitted — the worklet ran full real-time throughout,
so a third of the meeting was captured and thrown away.

It is invisible everywhere: `discontinuity` stays false (it is set only on track replacement),
`device_epoch` is unchanged, `st.seq` advances only on 200 so sequences stay **contiguous** — the
server sees continuous audio where seconds are missing — and the heartbeat still sends a
hardcoded `dropped_frames: 0`, which is now a false statement to a production route.

Fix it properly: queue or backpressure the send rather than discarding, or — if you must drop —
mark `discontinuity`, bump nothing, and report the true `dropped_frames`. Silent loss is the
unacceptable outcome.

**Then add the assertion that would have caught it:** admitted frames ≈ elapsed / frame_period.
None of the current G7 assertions can fail — `contiguous_hidden_accepted_sequence_progression` is
tautological, and `strict_v2_accounting_matches_descriptor_frames` is an arithmetic identity.

**Then re-run G7 at production geometry.** Production `frame_samples` is **8000**, hard-enforced
by `live_manifest_finalizer.py:181-185`. The runs submitted as proof used **1000**, because commit
`a843bb4` deleted the `--frame-samples` argument that iteration 7 had made required. Restore it,
run >5 minutes hidden at 8000 with the strict-v2 admission join, keep the raw arrays.

**Also:** `recreateSession` (`:642-664`) is the only escape from a 409 and is never exercised. It
resets `state.seq = 0` while in-flight POSTs are still outstanding — the resolving POST then sets
seq forward and the new session immediately 409s, recreating the exact failure it exists to
escape. A failed recreate also disables its own button permanently. Drain in-flight sends first,
and keep the button usable.

**Gate:** your committed probes demonstrate (a) no silent loss under slow POSTs, with a frames-vs-
elapsed assertion that fails if loss returns; (b) G7 >5 min hidden at `frame_samples=8000` with
raw arrays; (c) a 409 → recreate → clean resume with no sequence poisoning.


## Guardrails (enforced — the loop stops on violation)

`RALPH_PREFLIGHT_REQUIRED=1` runs `scripts/afk-guardrails/preflight.py x1-frame-drop` before every
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
`evidence/phase1/x1-frame-drop/` with their probes committed · an issue-style summary in
`progress.txt` stating criterion-by-criterion what proves it and what is not covered.
