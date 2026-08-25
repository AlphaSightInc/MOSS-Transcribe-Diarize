# M2 step 3, item 3 — `live_refinement` scheduling (plan §6 M5, §10.5 step 3)

**Verdict: shipped and green.** The arbiter has a fourth queue. The rolling witness is now
schedulable *below* the 2.5-second canonical span a listener is waiting on and *above*
provisional work, one witness per session, and a running MOSS request cannot be cancelled by a
newer one. Measured through three sessions sharing one arbiter: **98 dispatches, 14 of them a
canonical span going ahead of a waiting witness, 0 of them a witness going ahead of waiting
canonical work.** The answer did not move: trio WER `.131861`, content recall `.943916` — the
§10.2 grid's `10/10` column to 6 dp.

## What shipped

`moss_transcribe_diarize/app/live_arbiter.py`, three additions and one reordering:

| Addition | What it is for |
|---|---|
| `submit_live_refinement(*, coalesce_key, payload)` | admit one rolling witness per session; a *queued* predecessor is replaced, a *running* one is not |
| `release_live_refinement(*, item_id)` | say a dispatched witness is no longer running, so the next may be admitted |
| `ArbiterSnapshot.live_refinement` / `.live_refinement_running` | the two depths a §10.6 soak reads |
| `next_work()` | `batch > live_canonical > live_refinement > live_provisional`, and dispatching a witness marks it running |

Plan §6 M5's ordering, verbatim: `unresolved short canonical work > newest rolling refinement >
provisional-only work`. Batch keeps its existing place at the front; nothing about it changed.

## Two design decisions, and what each one cost

**D1 — no capacity knob for the refinement queue.** `max_live_canonical_items` and
`max_live_provisional_items` exist because those queues grow with frames. This one cannot: the
per-key rule *is* the bound. One arbiter serves one session in the runtime, so its depth is one;
a shared arbiter's depth is exactly the number of sessions with a pending witness, which is the
number that should be scheduled rather than a number to refuse. Cost: a future shared-arbiter
deployment with hundreds of sessions has no global cap. Recorded, not hidden — and the depths are
in the snapshot, so a soak would see it before a knob could help.

**D2 — the snapshot carries depths, never lifetime counters.** Plan §10.6 asks for a
"stale/coalesced refinement count", and the obvious move is a counter on the arbiter. It is the
wrong move: every drop is *already* reported to the caller that caused it — a coalesced witness
comes back as `replaced_item_id`, a suppressed one as `accepted=False` with a reason. A second
tally would be a second bookkeeping of the same fact, and the two would eventually disagree. The
one thing a caller cannot see from its own admission results is whether some *other* witness is
running, so that is what `live_refinement_running` reports. Cost: the §7.4 event serialization
(step 5) has to record the coalesce/suppress counts at the submission site rather than reading
them off the arbiter.

## Gates (all pass) — `verify_refinement_scheduling.py`, zero MOSS requests

Three sessions (the trio), one shared `InferenceArbiter`, interleaved span by span. Every unit of
work in the session goes through the arbiter: the canonical spans *and* the rolling windows.
The decoder is handed a runner that raises, so a cache miss fails instead of calling the GPU.

| Gate | Result |
|---|---|
| G1 scheduling changed no answer | bill `.198864`, milei `.096000`, keyu `.100719`; trio `.131861` / recall `.943916` — the grid's `10/10` column at 6 dp |
| G2 a witness never ran while canonical work waited | 0 of 98 dispatches; and canonical went ahead of a waiting witness **14** times, so the gate is not vacuous |
| G3 one running witness per session | never more running than sessions; 18 dispatched, 18 released, 0 releases matched nothing; ended 0 queued / 0 running |
| G4 every planned window dispatched once, in order | `[0,1,2,3,4,5]` for all three cases |
| G5 nothing dropped | 0 coalesced, 0 suppressed, 0 revisions refused; 6 of 6 windows applied per case |
| G6 zero fresh MOSS requests | 18 requests, 0 fresh |
| G7 one coalesce key per session | 1 each |

Max observed depths: canonical 3, refinement 3 (one per session) over 32 rounds.

## Mutations — five, in the production file, all caught

`mutate_refinement_scheduling.sh`; `live_arbiter.py` restored from a backup by an EXIT trap;
control clean before and after.

| # | Mutation | Caught by |
|---|---|---|
| M1 | refinement outranks canonical | **G2** (10 witnesses ran while canonical waited, and the non-vacuity check flipped too) + 2 T1 tests |
| M2 | refinement ranks below provisional | **T1 only** — see the finding below |
| M3 | dispatch does not mark the witness running | **G3** (18 releases matched no running witness) + 5 T1 tests |
| M4 | a newer witness cancels a running one | **T1 only** — see the finding below |
| M5 | release never clears the running mark | **G1/G4/G5** (bill decoded 1 of 6 windows, WER `.198864` → `.215909`) + 2 T1 tests |

### Finding — two branches the corpus cannot reach, and why that is the honest answer

M2 and M4 are caught by a named T1 test and by nothing else, for two different reasons, and both
are properties of the *producer*, not gaps in the sweep:

- **M2 (starvation below provisional).** The verifier's base path submits canonical spans, not
  provisional work, so its provisional queue is always empty and the two orderings are
  indistinguishable to it. Reaching this branch needs the runtime wiring of §10.5 step 4, where
  provisional previews and rolling windows coexist. Until then the T1 test is the whole guard.
- **M4 (cancelling a running witness).** `RollingTranscriptConverger` plans one window at a time
  and will not plan the next until the current one completes, so a second witness for the same
  session is never submitted while one is running. The branch is unreachable *given a
  well-behaved producer* — which is exactly when a guard earns its keep, since the producer that
  breaks it will be the terminal finalizer (§12.3) or a future multi-window witness.

Same shape as the M2-converger bundle's M5 and the M2-session-authority bundle's M3: recorded as
a corpus blind spot rather than papered over with a passing number.

## Carry-forward for §10.5 step 4 (the runtime wiring)

**The converger's coalesce key identifies an epoch, not a session.** It emits
`rolling:<epoch>`, and every session starts at epoch 0, so three sessions on one arbiter all
produce the same key. Production is safe today only because the runtime builds one
`InferenceArbiter` per session (`live_service_runtime.py:482`) — the collision is latent, not
active. This driver namespaces the key (`<case>:rolling:0`) rather than pretend otherwise, and
gate G7 checks the property that actually matters (one key per session, not one key per window).
Step 4 must decide: either the runtime submits a session-qualified key, or
`RollingTranscriptConverger` takes the session key the coordinator already has
(`LiveCoordinator.session_key`). Do not leave it to chance.

## Files

- `verify.json`, `verify-console.txt` — the three-session run above
- `mutations.txt`, `mutations/` — the five-mutation sweep, with each mutant's verifier and pytest output
- `pytest-targeted.txt` — `tests/test_live_arbiter_refinement.py tests/test_live_vad.py` (26 passed)
- `pytest-full.txt` — `tests/` (1061 passed, 2 skipped, 386 subtests; 1050 before)
- `file-mode-head.json`, `file-mode-worktree.json` — byte-identical, sha256 `ad381d8b…` — the same
  digest iterations 7, 11 and 12 recorded, so file mode has not moved across four production changes
- `sha256.txt` — checksums for everything above

## Reproduce

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_refinement_scheduling.py
prototypes/streaming-diarization/live-convergence/mutate_refinement_scheduling.sh /tmp/scheduling-mutations
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -q
```

No service restart was needed and none was performed: `submit_live_refinement` has no runtime
caller yet (§10.5 steps 4–7), so nothing the running `web_cli` executes changed.
