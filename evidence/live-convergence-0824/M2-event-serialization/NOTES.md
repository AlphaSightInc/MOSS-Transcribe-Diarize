# M2 step 3 item 5 — the rolling witness on the event stream (plan §10.5 step 5, §7.3/§7.4)

Iteration 15, 2026-08-25. Campaign branch `ralph/live-convergence-0824`.

## What this closes

Plan §10.5's fifth production step: **add snapshot/event serialization**. After iteration 14 the
rolling witness ran inside the real runtime and published a measurably better surface — but what
it *did* left no trace outside the process. A stopped converger, a failed window and an admission
refusal were visible only in the process log and in `LiveCoordinator.rolling_accounting()`, which
a soak cannot read and a replay trace does not carry. §10.6's resource gate has to measure rolling
correction latency, per-kind queue delay and stale/coalesced refinement counts from outside; §7.3's
snapshot fields have to reach a portal and a trace unchanged. Both are now readable, and both are
checked on real audio.

Five §7.4 event kinds ship, which is every one that has a producer today:

| event | when | carries |
|---|---|---|
| `rolling_decode_queued` | a window is planned | item id (null if the arbiter refused), `admitted`, window index, extent, `window_samples` |
| `rolling_decode_completed` | a dispatched window ends, on **every** path | outcome, window samples, owned samples, queue delay, decode elapsed, generated tokens, cap status, RTF, converger counters |
| `text_revision_applied` | the session accepted a revision | source, owned interval, revised segments, version, frontier, finalization status |
| `text_revision_refused` | the session refused one, by name | the same, plus the refusal |
| `decode_salvaged` | M1 published words the grammar had rejected | span id, disposition, committed samples, span sample count, generated tokens |

The three `terminal_finalization_*` events are E4's and are deliberately absent: an event kind with
no producer is a contract, not a serialization.

`canonical_processed` also gains `rolling_status`. That is the one place a converger that stops
while planning nothing — an evicted ring, a failed window — can still be seen, because it emits no
rolling event of its own to be seen in.

The §7.3 snapshot half needed no new code (`dataclasses.asdict` has carried the four fields since
iteration 12) but it did need checking, and it is now checked rather than assumed: JSON round trip
plus reconstruction through `live_service_replay._live_snapshot_from_dict`, per case.

## Result

```
lex_bill_ackman    queued=6 closed=6 applied=6 refused=0 salvaged=0 frontier=960000 segments=21 wer=0.198864
lex_javier_milei   queued=6 closed=6 applied=6 refused=0 salvaged=0 frontier=960000 segments=14 wer=0.096000
lex_keyu_jin       queued=6 closed=6 applied=6 refused=0 salvaged=0 frontier=960000 segments=16 wer=0.100719
TRIO               wer=0.131861 (grid 0.131861) recall=0.943916 (grid 0.943916)
payload vocabulary: 36 names
decode cost: {'requests': 98, 'fresh_requests': 0}
PASS
```

Nine gates, fixed before the run (the verifier's docstring is the preregistration):

- **G1** every planned window is announced exactly once, indices in order from 0, unique item ids,
  `window_samples` equal to the geometry's 160000.
- **G2** every admitted window is closed exactly once, and every completion carries §7.4's record —
  window samples, owned samples, queue delay, decode elapsed, generated tokens, cap status, RTF —
  with no field missing and no impossible timing.
- **G3** the revision events reconcile with the session: applied count == `text_revision_version`,
  refusal count == refused completions, last applied event's version and frontier == the snapshot's.
- **G4** no §7.4 payload carries transcript text: every string value is a snake_case name from a
  vocabulary **read out of the production sources**.
- **G5** the §7.3 fields survive the wire: four fields present, five §7.1 segment fields present,
  JSON round trip, and replay reconstruction equal to the snapshot the session produced.
- **G6** every event JSON round-trips and reconstructs equal through `_event_from_dict`.
- **G7** the arm is unchanged (per case to 6 dp, trio `.131861` / `.943916`).
- **G8** `decode_salvaged` count == the number of `canonical_processed` reporting the `salvaged`
  disposition, with the same span ids.
- **G9** zero fresh MOSS requests.

## Two things the numbers say that the gates do not

**The completion's RTF is a real field with an unreal number here.** The replay decoder answers in
microseconds, so the six windows report RTF ~3e-5 and queue waits of 0.01–2.9 ms. What this run
proves is that the fields are present, populated and correctly derived; what the witness actually
costs is §10.6's measurement on the GPU, and iteration 14's D2 (a witness holds the session's single
in-flight slot while it decodes) is the thing that soak has to price. Generated tokens per window
are real: 77–110 for bill.

**G8 passed on zero.** No span in this instrument reaches the salvage gate — the grid's decode cache
records different answers for bill's span 02 than the deployed 4070 Ti produced on 2026-08-25, which
is iteration 4's "the deployed decoder is not a function" seen from a third direction. So the corpus
reading of `decode_salvaged` is a negative control (no spurious events) and the positive control is
a T2 test that drives a genuinely unparseable answer through the production adapter and the runtime.
Reported rather than papered over.

## Validation

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_rolling_events.py --output verify.json
.venv/bin/python -m pytest tests/ -q
prototypes/streaming-diarization/live-convergence/mutate_rolling_events.sh /tmp/event-mutations
```

- verifier exit 0, nine gates (`verify.json`, `verify-console.txt`).
- full suite **1079 passed, 2 skipped, 386 subtests** (1072 before) — 7 new T2 tests in
  `tests/test_live_rolling_wiring.py::RollingEventSerializationTest` (`pytest-full.txt`,
  `pytest-targeted.txt`).
- file-mode decoder A/B against a HEAD worktree: byte-identical, sha256
  `ad381d8bd247e4a8ebe56240dfbc29c0b5a86ffb35a2fcb411c07bbd5b7707f2` — the same digest since
  iteration 7, unmoved across six production changes (`file-mode-{head,worktree}.json`).
- six mutations, all caught, control clean before and after (`mutations.txt`, `mutations/`).

## Mutations

| # | what it breaks | caught by |
|---|---|---|
| M1 | a planned window is never announced | verifier (G1/G2, 0 announced vs 6 planned) **and** T2 |
| M2 | only a window that decoded is closed | **T2 only** |
| M3 | a refused admission is dropped instead of reported | **T2 only** |
| M4 | a refusal is announced as an application | **T2 only** |
| M5 | the completion omits §7.4's decode record | verifier (G2) **and** T2 |
| M6 | a salvaged span is not named | **T2 only** |

Four of six are corpus-blind, and each for a stated reason: a window nobody was waiting for needs a
dispatch after stop; a refused admission needs the base a whole window ahead; a refused revision
needs a producer race; a salvaged span needs a decode this instrument's cache does not contain.
Same shape as the producer-pacing findings of iterations 11–14 — the corpus reading of the stream is
necessary and not sufficient, and the T2 tier is where the rest lives.

## Decisions, and what each cost

**D1 — the runtime emits, the coordinator reports.** Every new event is recorded in
`live_service_runtime.py` from data the coordinator returns on its result objects
(`CoordinatorFrameResult.rolling_windows`, `CoordinatorWorkResult.rolling_windows` +
`rolling_status`, and eight new fields on `CoordinatorRefinementResult`). Plan §6 M7 says adapters
serialize the authority module's result and implement none of its rules; a runtime that reached into
`item.payload` to describe a window would have been the second place that knows what a window is.
Cost: three result dataclasses grew.

**D2 — one announcement per planned window, one completion per admitted window.** A refused
admission is announced with `item_id: null` and gets no timing entry, because nothing will ever
complete it; every dispatched item is closed exactly once, including the paths where no decode
happened (`not_awaited`, `defect`, `session_terminal`), with the decode fields null rather than
zero. Cost: a small `rolling_timing` table in the runtime session, keyed by item id, popped on
completion — the same shape `canonical_timing` already had. What it buys is that queued minus
completed is a live queue depth and never a leak.

**D3 — the payload vocabulary is read, not listed.** G4's allowed-name set is built from
`RollingStatus`, `LiveTranscriptDisposition`, the finalization statuses, and the string literals
inside `LiveSession._text_revision_refusal` and `LiveServiceRuntime._process_refinement_item`. A
refusal name added to production extends the gate automatically; a payload that starts carrying a
word somebody said does not. Cost: two `inspect.getsource` regexes, and the gate is worth more than
the hard-coded list it replaces — which would have gone stale on the first new refusal.

## Files

```
moss_transcribe_diarize/app/live_coordinator.py         RollingWindowPlan; rolling fields on three results
moss_transcribe_diarize/app/live_service_runtime.py     _record_rolling_queued/_record_rolling_completed; five event kinds
tests/test_live_rolling_wiring.py                       RollingEventSerializationTest (7 T2 tests)
prototypes/.../verify_rolling_events.py                 the nine gates
prototypes/.../mutate_rolling_events.sh                 the six mutations
prototypes/.../verify_runtime_rolling.py                collect_events=True (additive; step 4's gates unchanged)
```

## What is still owed to M2

Step 6 (the portal renders `effective_transcript` as one replacement surface) and step 7 (the
export switch, **last**, in the same reviewed change as its terminal/effective export tests), then
the headless portal render/serialization test and the §10.6 soak. The deployed `web_cli` is still
pid 22561 on the M1 build and must be restarted onto this build — and recorded — before any paired
rerun.
