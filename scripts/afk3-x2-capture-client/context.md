# Context — x2-capture-client

Iteration 7.

Branch `afk3/x2-capture-client` from `dev`. Every defect in the PRD was found by independent adversarial
review with a reproduction; they are facts, not hypotheses. Read `docs/phase1-afk-charter.md`
(binding) and the closed decisions in `.wayfinder/tickets/` before your first change.

## Known pre-existing test failures — not yours

`l2-stage0/test_legacy_ingest.py` (55 != 92) and four `test_macos_uds_tracer.py` tests fail
identically at `pre-afk-20260813`. `l15/test_l1_baseline.py` fails with `l15_product_tree_drift`:
that guard correctly refuses to run when the product tree moved — **do not edit its pin**, that
would falsify a measurement baseline.

## Validation

```bash
.venv/bin/pytest -q          # ~1006 pass, 2 skip, 387 subtests
python3 scripts/afk-guardrails/preflight.py x2-capture-client
```

## Acceptance checklist

- Preserve the settled core: one shared AudioContext; worklet-port-driven POSTs only; one
  arithmetic clock anchor per lane; descriptor-derived geometry; exactly nine v2 keys.
- Serialize POSTs independently per lane. For lane frames: retry capacity 429 without
  consuming its sequence; do not resend queue-backpressure 429 whose sequence was accepted;
  handle failure-less 429 without wedging; resync/recreate on 409; stop on 400.
- Emit the server's browser failure vocabulary from real browser events: track end,
  AudioContext state change, sustained clipping, and silent microphone. `stop()` must send a
  final `stopped` heartbeat; no timer-based heartbeat is permitted.
- Use `context.sampleRate` in frame metadata, enforce the `>= 1e-4` preflight-signal gate,
  and bump `deviceEpoch` plus mark `discontinuity` when a lane is replaced/restarted.
- Prove the 429/409/400 and heartbeat branches with non-vacuous tests. After merging current
  `dev`, run `npm --prefix frontend run typecheck && npm --prefix frontend test`; commit raw,
  rerunnable evidence under `evidence/phase1/x2-capture-client/`. The client does not prove
  attended display capture or server/inference behavior.

## Current implementation evidence

`dev` (`23afb6d`) remains an ancestor of this branch; no merge is pending. The owned r2 baseline
has now been restored from `afk2/r2-capture-client` without its loop state or server files:
`frontend/src/capture/captureClient.ts`, its focused test, and
`frontend/public/worklets/lane-framer.js`. `App.tsx` remains untouched and still does not mount
the client, per ownership.

Iterations 4–5 replaced the baseline fire-and-forget frame POST with an independent queue per
lane. Frames obtain their sequence only at the serial queue head. A structured 429 with
`failure.code == v2_lane_retention_capacity_reached` stays at that head, so the next worklet-port
frame retries the identical body before a later frame can post. A failure-less 429 is the
post-admission queue-backpressure response, so it advances the sequence and records one dropped
frame. A machine-readable out-of-order 409 sets the head to the server's non-negative
`expected_sequence` and retains it for the next worklet-driven retry; another 409 clears local
delivery state for caller-driven `createSession()` recreation. A 400 closes local capture. The
focused production-path tests prove one-in-flight ordering, capacity bodies `[0, 0, 1]`, consumed
429 bodies `[0, 1]`, 409 resync bodies `[0, 5, 6]`, terminal-recreation clearing, and 400 local
stop. Validation: `npm --prefix frontend test -- src/capture/captureClient.test.ts` (11 passed),
`npm --prefix frontend run typecheck` (pass), and `python3 scripts/afk-guardrails/preflight.py
x2-capture-client` (`PREFLIGHT OK`).

Iteration 6 introduced a serialized heartbeat state path without timers. A real `ended` event on
any retained media track fails only that lane with `browser_track_ended`, clears its unsent frames,
and immediately reports health while the peer remains capturing. A real `AudioContext`
`statechange` reports `browser_audio_context_suspended` as degraded on both active lanes and clears
that fact once the context returns to running. `stop()` now serializes one final `stopped`
heartbeat before the authenticated stop request; cleanup unregisters both kinds of listeners.
Focused tests dispatch both browser events, assert the stopped heartbeat precedes `/stop`, and
reject `setInterval`/`setTimeout` in the client. Validation: `npm --prefix frontend test --
src/capture/captureClient.test.ts` (14 passed), `npm --prefix frontend run typecheck` (pass), and
`python3 scripts/afk-guardrails/preflight.py x2-capture-client` (`PREFLIGHT OK`). Raw output:
`evidence/phase1/x2-capture-client/iteration-6-browser-health.txt`.

Iteration 7 exposes the three pre-session browser facts without inventing a server session.
`onPreSessionFailure` reports rejected microphone requests as
`browser_microphone_permission_denied`, rejected display requests as
`browser_capture_request_rejected`, and a selected surface without audio as
`browser_surface_audio_missing`. Each path tears down local capture and leaves retry to the caller;
the focused test proves the callback facts and zero fetches. This is intentionally a local UI seam:
the authenticated heartbeat route has no session to address. Raw output:
`evidence/phase1/x2-capture-client/iteration-7-pre-session-failures.txt`.

Sustained clip and mic-silence detection remain open and require the threshold prototype before
production code.

## Ranked candidates

1. Extend the existing browser-capture feasibility bench to measure sustained-clipping and
   microphone-silence thresholds, record its verdict in `NOTES.md`, then add the two remaining
   heartbeat facts with non-vacuous tests.
2. Add lane replacement/restart semantics: actual context sample rate in frames, thresholded
   preflight signal, epoch increment, and marked discontinuity. Do not touch `App.tsx`; mounting
   remains orchestrator-owned.
