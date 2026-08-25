# M2 step 3 item 4 — the rolling witness runs in the live runtime (plan §10.5 step 4)

Recorded 2026-08-25, campaign branch `ralph/live-convergence-0824`, iteration 14.

## What this closes

Plan §10.5's fourth step: **wire the current 2.5-second base commits into the converger**.
Steps 1–3 shipped three pieces that each worked in isolation — the converger reproduces the
selected arm, the session validates every revision, the arbiter schedules a witness below the
base path — and each was driven by a hand-written harness. This step deletes the harness: the
runtime itself now feeds the converger, dispatches its windows, publishes what comes back, and
releases what it popped.

    audio frames -> LiveServiceRuntime.accept_frame
      -> WebRtcSpeechProvider + EndpointPolicy (deployed configuration)
        -> LiveCoordinator -> InferenceArbiter (canonical AND refinement)
          -> RollingTranscriptConverger -> LiveSession.apply_text_revision
            -> snapshot().effective_transcript

## Headline result

`verify_runtime_rolling.py` runs each trio case **twice** through the same real runtime — once
with no window decoder (the service as it shipped before this change) and once with one — so
every number is a before/after on one instrument.

| arm | trio WER | trio content recall | per case (bill / milei / keyu) |
|---|---|---|---|
| base (no witness) | **0.199870** | **0.913490** | .261364 / .144000 / .194245 |
| rolling (10/10)   | **0.131861** | **0.943916** | .198864 / .096000 / .100719 |

Both arms match the §10.2 grid to **six decimal places on every case**: the base arm reproduces
the published live trio and the rolling arm reproduces the arm §10.4 selected. Six windows
planned, dispatched, decoded and applied per case; zero failed windows, zero stale completions,
zero admission refusals; rolling PCM high-water 208 000–240 000 samples against the plan §6 M2
bound of 320 000. **Zero fresh MOSS requests** — 178 decodes, all replayed from the grid's cache.

## What shipped

- `app/live_coordinator.py` — the converger's runtime home. An optional `rolling_decoder`
  brings a `RollingTranscriptConverger` with it (no decoder, no witness, and the coordinator
  behaves exactly as before). `accept_frame` retains the newest audio in the converger;
  `submit_prepared_work` observes the base after every commit; `capture_refinement_item` /
  `decode_refinement` / `submit_refinement` / `release_refinement` are the dispatch cycle;
  `stop_rolling` ends it. Windows are admitted under a **session-qualified** coalesce key.
- `app/live_service_runtime.py` — dispatch. Readiness and the stop drain now count witnesses;
  `next_work` may return a refinement item and `_process_refinement_item` handles it with the
  canonical pump's shape (capture under the lock, decode outside it, publish under it again).
- `app/live_provider_bundle.py` — the deployed bundle supplies a second `RunnerBoundedWavInference`
  over the *same* runner, bounded at the rolling window rather than at the span cap.
- `tests/test_live_rolling_wiring.py` — 11 T2 tests.

## Three decisions, each with what it cost

**D1 — a second decoder, not a wider one.** The deployed manifest bounds the decoder at
`max_samples: 120000` (7.5 s); a 10-second window is 160 000 samples, so the base decoder
*cannot physically* accept one. The rolling adapter is a second bounded adapter over the same
runner, sized from `DEFAULT_ROLLING_GEOMETRY.window_samples`. The alternative — raising
`decoder_config.max_samples` in the manifest — would change `decoder_config_hash`, hence the
provider manifest hash and the deployed descriptor, to widen a bound that describes the *base*
path. Cost: two adapters instead of one, and a geometry change now needs a code change (which
it already did — widening the window is a new §10.2 grid run, not a config edit).

**D2 — the witness holds the session's single in-flight slot.** A running window blocks the
next canonical span for that session for as long as it decodes (~1 s at the measured RTF). That
is not an oversight: *one in-flight vLLM request per harness* is the deployment contract, so
rolling's cost is a serial cost. The arbiter still guarantees a witness is never *dispatched*
while canonical work waits. Cost: a bounded, one-decode addition to base first-publication
latency in the worst case, which plan §10.6's soak must measure rather than assume.

**D3 — a rolling defect ends rolling, never the meeting.** The canonical pump terminalizes the
session on an unexpected exception; the refinement pump logs it (counts and names only), stops
rolling for that session, and leaves the base path and the whole surface untouched. ADR-0005 D1
gives the session the last word precisely so the second listener cannot take down the first.
Cost: until §10.5 step 5 adds the §7.4 events, a stopped converger is visible only in the log
and in `LiveCoordinator.rolling_accounting()` — no event says it out loud yet.

## The defect this iteration found and fixed

`submit_refinement` originally planned the next window *before* releasing the witness that had
just answered. The arbiter refuses a newer witness while one is **running** for the same key
(plan §6 M5, correctly — it may not cancel a MOSS request already burning GPU), so the newly
planned window was refused and lost permanently, and the converger — still holding that window
in its one in-flight slot — stopped planning for the rest of the session.

It only fires when the base is already a whole window ahead at the instant a witness lands. An
unhurried real-time meeting never is, which is why **the trio corpus does not reach it**: the
verifier passed with the defect present (mutation M3, `verify exit=0`). What reached it was a
T2 test whose pump starves on purpose, so every base commit lands before the first witness runs
— the shape of a replay client or a post-hiccup burst. The fix is one line of ordering, and the
reason is in the docstring.

The counter that made it findable at all — `_rolling_admission_refusals`, kept because an
admission refusal from a well-behaved producer is a defect rather than an error — is now a
gate in the verifier (`G4 ... refused=0`).

## Mutations — five, all caught

Run: `prototypes/streaming-diarization/live-convergence/mutate_runtime_rolling.sh <out>`
(zero MOSS requests; both production files restored by a trap on exit; control clean before and
after).

| # | mutation | caught by |
|---|---|---|
| M1 | a base commit is never observed | verifier (0 of 6 windows, base-arm WER) **and** 5 T2 tests |
| M2 | no `observe_base` after an applied revision | **T2 only** (2 tests) — see finding |
| M3 | the next window is planned before the release | **T2 only** (3 tests) — the defect above |
| M4 | the coalesce key drops the session | **T2 only** (1 test) — see finding |
| M5 | stop does not wait for the witness | verifier (5 of 6 windows; bill .198864 → .204545) **and** 0 T2 |

**Finding — three branches the corpus cannot reach, for three different reasons.** M2 needs the
base to have *stopped* committing while a revision is still outstanding; on 60 s of continuously
committing audio the next base commit re-observes the frontier anyway. M3 needs the base to run
a window ahead. M4 needs two sessions on one arbiter, and the runtime builds one arbiter per
session (`live_service_runtime.py:482`). All three are properties of the *producer's pacing*,
not gaps in the sweep — recorded rather than papered over, the same shape as iterations 11–13.

## Validation

```bash
# the two-arm runtime verifier (exit 0 = all seven gates; no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_runtime_rolling.py
# the five mutations, in the production files, restored on exit
prototypes/streaming-diarization/live-convergence/mutate_runtime_rolling.sh /tmp/rolling-mutations
# the T2 wiring tests
.venv/bin/python -m pytest tests/test_live_rolling_wiring.py -q
```

- Full suite: **1072 passed, 2 skipped, 386 subtests** (1061 before) — `pytest-full.txt`.
- Targeted: 116 passed — `pytest-targeted.txt`.
- File mode byte-identical to HEAD: sha256
  `ad381d8bd247e4a8ebe56240dfbc29c0b5a86ffb35a2fcb411c07bbd5b7707f2` — the same digest
  iterations 7, 11, 12 and 13 recorded, so file mode has not moved across five production
  changes (`file-mode-{head,worktree}.json`, `sha256.txt`).

## Two things a reader should carry forward

**The offline runtime reproduces the deployed span grid exactly.** Driven with the deployed
endpoint configuration and real `webrtcvad`, the frozen spans are identical to the checked-in
baseline traces on all three cases (24 / 32 / 24). That is what makes a GPU-free, end-to-end
runtime verifier possible at all, and it re-confirms iteration 4's determinism finding from a
completely different direction.

**A base that falls a whole window behind stops rolling, by design and now by observation.**
The converger's ring is bounded at `2 x window`; reaching it means the audio a pending window
needs is already gone, so it names `pcm_evicted` and stops planning. The first draft of the
verifier hit exactly this (0 windows on all three cases) because its driver handed over the
whole meeting before the pump thread ran once — not a condition the deployed service can be in,
but the honest reading is that rolling degrades to the base path, statedly, when the base falls
behind. The verifier now paces the base within two spans, which is what real-time pacing
produces; §10.6's soak measures the real thing.

## What is NOT done here

Steps 5–7 of §10.5, in order: the §7.3/§7.4 snapshot and event serialization, the portal's
`effective_transcript` render, and the export switch **last**. The deployed `web_cli` was **not**
restarted onto this build: rolling would turn on in the live service before its events and portal
exist, and no measurement this iteration needs the running service (the verifier drives the real
runtime offline with the deployed configuration). The restart belongs with the paired rerun after
step 7, and must be recorded then.
