# P2 — row-10 timing receipt (THROWAWAY LOGIC PROTOTYPE)

## Structural question

What is the smallest row-owned, content-free projection that preserves the
causal timing chain `capture seal -> canonical queued -> decode elapsed ->
identity/publish -> snapshot version -> DOM mutation`, after evidence
sanitization removes event payloads and event kinds?

## Minimum primitives

1. A narrow, explicit allowlist of causal event kinds and numeric/enumerated
   fields only.
2. A keyed span/item correlation so the projection cannot conflate parallel
   canonical work.
3. Browser `started` / `matched` performance timestamps paired to the emitted
   snapshot version.
4. Per-stage `null` values, missing counters, and an `INCOMPLETE` attribution
   state.

## Invariants

- The prototype projects actual runtime events; it does not reproduce runtime
  timing or decode behavior.
- It keeps no transcript, speaker/name, header, request/response body, vector,
  PCM/audio, or opaque runtime/session identifier other than the row meeting ID.
- A missing fact is `null`, never zero; product event/sanitizer behavior is not
  changed by this prototype.
- No decoder, provider, tunnel, microphone, audio playback, shared listener, or
  product setting is used (budget: 0 decoder requests).

## Assumptions / unknowns

- The historical row-10 audit is representative of the runtime event schema.
- Browser timing is available from the row harness only at the observation
  boundary; its exact existing fields still need source inspection.
- A fresh 4.1405 s miss cannot be decomposed from the retained sanitized trace:
  it has null kinds and no payload.

## Falsifier

If a required link has no producer-owned fact in the runtime/harness chain
(seal, queue, decode, publish/snapshot, or DOM), the design is falsified for
that link. The report must name the precise absent event/field; that is the
only justified product change, which this branch will not make.

## Why each tool changes the decision

- The historical audit provides observed event shape and exact positive-control
  timings.
- `retained_metadata` proves the current sanitizer loss and supplies the
  negative baseline.
- The real row-10 `bank()` harness is the only authorized row-owned write seam;
  its self-tests prove the capture artifact is emitted beside the sanitized
  trace.
- The prescribed Python/pytest suite checks the harness-only patch without
  exercising a decoder.

## Run

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python prototypes/round5-p2/run.py`

## Verdict placeholder

## Field contract and outcome

The row-owned file is `row-10-timing.json`. It has no raw event payload and no
names, transcript, headers, bodies, vectors, or audio.

- `capture_seal`: `seq`, start/end samples, and reason code (1 hard-cap, 2
  end-silence, 3 leading-silence) from `span_frozen`
  (`live_service_runtime.py:799-811`).
- `canonical_queue`: `seq` and numeric item ID from `canonical_queued`
  (`live_service_runtime.py:1886-1901`); queue wait comes from
  `canonical_started` (`:1632-1640`).
- `decode`: queue-wait seconds, decode elapsed seconds, processing elapsed
  seconds, and real-time factor from `canonical_processed`
  (`:1774-1809`).
- `identity_publish`: numeric item/span IDs, submitted flag, identity-status
  code (1 prepared, 2 abstain, 3 empty span), and runtime snapshot version.
  `_record_event` owns that version and immediately notifies the publication
  observer (`:1865-1884`); `phase2_live.py:573-690` carries its pinned snapshot
  through identity and publication.
- `browser`: `started`, snapshot-response received time/version, and DOM
  `matched` `performance.now()` values. The harness observes only the numeric
  version returned through the actual response's `.json()` path, then restores
  `window.fetch` (`verify_workspace.py:582-630`). The production poller uses
  that snapshot to dispatch the rendered items (`frontend/src/api/mossPoller.ts:190-267`).

Controls ran with zero decoder requests:

- Loss: `retained_metadata` reduced all 78 audit kinds to null and removed all
  payload keys; the retained run cited by the brief has 22/22 null kinds.
- Positive: the historical first chain reproduces 0.000173667 s queue wait,
  7.438577042 s processing, and 7.068335624877363 s runner elapsed.
- Violating: four injected content classes (transcript, name, header, body)
  survive 0 times.
- Missing stage: removing all `canonical_queued` events yields a null queue
  sequence and `INCOMPLETE`, never zero.

The historical audit remains `INCOMPLETE`: it predates top-level snapshot
versions, `canonical_decode_rtf`, and browser snapshot-response timing. This
is not the falsifier: current production `_record_event` emits snapshot version
and current `canonical_processed` emits RTF. A fresh raw row-10 run can populate
both, while the harness adds the browser side without a product change.

Attempts: 2/3. The first control exposed binary-float presentation drift for
milliseconds-to-seconds; deterministic 12-decimal projection corrected that.
The second passed. The prototype is throwaway; retain this result, then delete
or absorb it after the decision.

Final verification: targeted harness tests 3 passed; prescribed full backend
suite 2,317 passed / 5 skipped / 2 xfailed / 0 failed (37 subtests); frontend
312 passed, typecheck clean, build clean. All runs used the prescribed runtime
where applicable, with zero decoder requests.
