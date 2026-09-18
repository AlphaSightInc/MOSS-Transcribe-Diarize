# WP35 — Stop-time drain on the per-lane build

Prototype question (from the brief): *at Stop, which queued work must still run for
correctness (committed canonical spans whose frames were accepted but not yet decoded)
versus work that is superseded by terminal (pending rolling windows, draft), and what is
Stop→final for 1 and 4 concurrent 600 s sessions if superseded work is cancelled or
deprioritised at Stop?*

One command (LOGIC prototype, no network, no GPU, stub ASR with per-request latency):

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <COMMON python> \
  prototypes/stop-drain/run.py --sessions 4 --seconds 600 --output <out.json>
```

## Code trace (read before probing)

* `live_service_runtime.stop` creates `state.stop_task = _finish_stop(state)` under the
  runtime lock. From that moment `accept_frame` raises `LiveSessionClosed`, so
  `accepted_samples` is frozen for the rest of the session's life.
* `_finish_stop` (a) submits the tail partition with `stop_endpoint()`, (b) awaits
  `_wait_for_drain`, (c) **only then** calls `coordinator.stop_rolling()`, (d) finalizes
  identity, (e) `session.stop()`, (f) `_begin_terminal_locked`.
* `_has_unresolved_work_locked` counts canonical queue + in-flight canonical + pending
  frozen spans **and** `live_refinement` + `live_refinement_running`.
* Every rolling completion re-plans: `submit_refinement` → `_observe_base_and_queue()` →
  `converger.observe_base()` → `_queue_refinement()` → `arbiter.submit_live_refinement`.
  That loop only stops when `converger.accounting().status is not RollingStatus.ROLLING`,
  i.e. after `stop_rolling()`, which step (c) above runs *after* the drain.
* All canonical **and** refinement work for every session is dispatched by one
  process-scoped `_TransientCanonicalPumpScheduler` worker thread
  (`_drain_ready_sessions` → `_pump_next_ready_session`), one item at a time.
* Terminal runs off that worker: `_ThreadTerminalScheduler` starts one daemon thread per
  meeting, and `finalize_lanes` decodes each lane tape whole. Terminal proposes
  `start_sample=0 … plan.end_sample`, `source="terminal"`, i.e. it *replaces* the rolling
  surface for the whole meeting (`live_transcript_convergence.finalize`).
* The deployment ceiling of 2 concurrent decoder requests is imposed by the harness
  (`prototypes/capacity-campaign/stack.py`, `BoundedSemaphore(2)` around
  `VllmRunner._post_multipart`), not by the runtime.
* The draft lane is **off** in the campaign stack: `run_local_stack.py` only passes
  `--live-draft-lane-seconds` when asked, and `stack.py` never asks.

## Ranked, falsifiable hypotheses (written before probing)

**H1 — rolling treadmill (rank 1).** The post-Stop drain is unbounded in the number of
rolling decodes because each completed window re-plans the next, and rolling is only
stopped *after* the drain. *Prediction:* calling `stop_rolling()` at the start of
`_finish_stop` drops post-Stop rolling decodes from O(rolling lag in windows) to at most
one already-dispatched window per session, and cuts Stop→final by roughly
(post-Stop rolling decodes × per-request latency), since the single pump worker serialises
them. *Falsifier:* post-Stop `rolling_decode_completed` events with a real decode outcome
stay the same, or Stop→final does not move.

**H2 — one process-scoped worker (rank 2).** Even with zero rolling work the tail
canonical work of N sessions serialises through one pump thread. *Prediction:* after H1's
fix, 4× Stop→final is still ≳ 4 × the 1× drain component. *Falsifier:* 4× ≈ 1×.

**H3 — terminal becomes the floor (rank 3).** Once the drain is fixed, Stop→final is
dominated by the terminal whole-meeting per-lane decode: 4 sessions × 2 lanes = 8 whole
600 s decodes through a 2-slot decoder ceiling, against WP6's mono baseline of 30–40 s for
one 600 s mixed tape. *Prediction:* the real 4×600 does **not** reach final inside the
campaign's 90 s bar even with H1 fixed, and the failure moves from "terminal never started"
to "terminal started and is still decoding". *Falsifier:* real 4×600 final ≤ 90 s.

**H4 — the drain's refinement gate alone (rank 4).** `_has_unresolved_work_locked` counting
`live_refinement` is *not* the cause on its own: at most one window is queued per session
(the arbiter coalesces per key), and a queued-but-superseded window is already dropped for
free by `capture_refinement_item` returning `None`. *Prediction:* removing only that gate
changes Stop→final by less than one decode per session. *Falsifier:* it changes materially.

**H5 — draft lane (rank 5).** Post-Stop draft decodes contribute. *Prediction:* zero, the
campaign runs with `draft_lane_seconds=None`. *Falsifier:* draft requests after Stop.

## Results — stub, 0.5 s real-time frames, system lane = corpus audio, mic lane = digital zeros

Evidence: `evidence/mvpfix/wp35/stub-{1,4}x600-{before,after}.json`. "Before" is
`integration/mvp-fix-20260917` @ `a6b512fd`; "after" adds the `_finish_stop` change only.
Decoder latency: flat 0.22 decode RTF clamped to [0.15, 0.60] s, terminal charged 0.6 s per
120 s stride window, all requests through a 2-slot ceiling (the campaign harness's).

| Arm | Stop→final per session (s) | outcome | rolling requests after the first Stop | terminal started | words at Stop → at final | accepted = accounted |
|---|---|---|---|---|---|---|
| 1×600 before | 4.314 | final | 1 | yes | 956 → 960 | 9,600,000 ✓ |
| 1×600 after | **3.710** | final | **0** | yes | 956 → 960 | 9,600,000 ✓ |
| 4×600 before | none — all four still draining at the 600 s cap | `not_started` 4/4, Stop returned `LiveServiceStopPending` | **143** (35 admitted / 36 completed per session) | **0/4** | 956 → 960 | 9,600,000 ✓ |
| 4×600 after | **5.518 / 5.544 / 8.537 / 8.544** | **final 4/4** | **0** admitted (1 already-queued window per session dispatched as `not_awaited`) | **4/4** | 952–956 → 960 | 9,600,000 ✓ |

Total stub decoder requests at 4×600: 1200 → 1060; peak in flight 1 → 2 (terminal now runs).
No backpressure retries in any arm. No `text_revision_applied` from rolling after Stop in the
after arms; the surface between the stop request and the terminal revision does not move.

The before arm reproduces WP25 capacity_4x600 F4 in every respect that matters: accepted and
accounted 9,600,000 per session, no final inside the bar, terminal never started, and a
post-Stop rolling backlog that is larger the longer the meeting ran.

## Verdicts

- **H1 — rolling treadmill: CONFIRMED, and it is the whole cause.** Post-Stop rolling decodes
  went 143 → 0 admitted and 4×600 Stop→final went "never" → 8.5 s worst case. The fix is
  three lines: end rolling at the top of `_finish_stop` for the meetings that will get a
  terminal pass, which is where `submit_refinement`'s `observe_base` re-plan loop stops.
- **H2 — one process-scoped worker: CONFIRMED but not the binding constraint here.** Four
  sessions cost 8.5 s where one costs 3.7 s, and the tail canonical work of each session
  still serialises through the single pump. At 600 s that tail is one span per session, so
  the residual serialisation is seconds, not minutes.
- **H3 — terminal becomes the floor: CONFIRMED in shape, unquantified in the stub.** With the
  drain fixed, Stop→final is the tail canonical work plus the terminal decode; the stub prices
  a whole 600 s lane at 3.0 s, so the stub number is a lower bound on the real one by
  construction. The real measurement is the campaign run, reported separately.
- **H4 — the refinement gate in `_has_unresolved_work_locked`: FALSIFIED as a cause.** The
  arbiter coalesces one window per session, so at most one queued window per session survives
  Stop, and `capture_refinement_item` already drops it for free once rolling has ended: the
  after arms show exactly one `rolling_decode_completed` per session with no decode. The gate
  was left exactly as it was; removing it would have bought one dispatch per session.
- **H5 — draft lane: FALSIFIED.** `run_local_stack.py` only passes `--live-draft-lane-seconds`
  when asked and the campaign stack never asks, so `draft_decoder_factory` is `None` and no
  draft request exists to cancel. No production change was made for it.
- **Candidate (b), "prioritise terminal over any session's rolling work": not needed.** Terminal
  never contends with rolling through the arbiter — it runs on its own per-meeting thread and
  goes straight to the runner — and after (a) there is no post-Stop rolling work left to
  outrank. Implementing (b) would have added a priority rule with nothing to order.

## What still runs at Stop, and why (the question's first half)

**Must still run:** canonical decode of every span whose frames were accepted, including the
tail partition `stop_endpoint()` freezes. Those are the words the meeting has not published
yet, and `accepted_samples == accounted_samples` at Stop is what says they all landed.

**Superseded by terminal:** every rolling window not yet decoded, and any window queued but
not dispatched. A rolling window only ever revises the *text* of spans the base path has
already committed (ADR-0005 D2/D4); the terminal pass then proposes `[0, end_sample)` for the
whole meeting and replaces that text wholesale. So cancelling it cannot lose anything the
meeting acknowledged — the measured word counts are identical in both arms — and keeping it
costs the whole drain.

**Not superseded when there is no terminal pass:** a deployment with no finalizer, a meeting
whose audio was not retained, or one with no witness gets no replacement, so rolling stays its
last listener and its drain is unchanged. That is the exact condition the fix keys on.

## Real-decoder confirmation (`evidence/mvpfix/wp35/real-4x300-after/`)

`prototypes/capacity-campaign/run.py --sessions 4 --seconds 300 --allow-contention`, own
loopback forward on 18135, own stack on 17835, isolated finalized manifest
(`max_tape_bytes` 57,600,000), against the existing vLLM. 549 real decoder requests, peak 2
in flight, `foreign_load_detected` false. Re-scored with `rescore.py` because the run
predates the `prestop_inference_projection` repair the same change required.

| Session | clip | Stop→final (s) | outcome | accepted = accounted | frames | words | rolling admitted after Stop | rolling completions after Stop | terminal started |
|---|---|---:|---|---:|---:|---:|---:|---|---|
| 1 | bill_ackman | 32.443 | final | 4,800,000 ✓ | 1200 | 920 | **0** | 1 × `not_awaited` | yes |
| 2 | keyu_jin | 18.325 | final | 4,800,000 ✓ | 1200 | 740 | **0** | 1 × `not_awaited` | yes |
| 3 | mono_javier | 35.355 | final | 4,800,000 ✓ | 1200 | 647 | **0** | 1 × `not_awaited` | yes |
| 4 | jamie_dimon | 29.247 | final | 4,800,000 ✓ | 1200 | 964 | **0** | 1 × `not_awaited` | yes |

Every session `clean`; 0 backpressure retries, 0 wrong-owner failures, `reopened_status`
`completed` 4/4; fairness passes (max pairwise dispatch skew 1 over 1074 contended
observations); pre-Stop RTF 0.0804; max refinement queue depth 1; max GPU cache use 0.0946;
RSS growth 702,283,776 bytes. WP25 measured 30/31/5/22 windows admitted after Stop and
terminal started 0/4 on the same build.

**Length deviation, stated plainly:** the brief asked for one real 4×600. The stub after-arm
needs 1,060 decoder requests at that length (960 canonical + 96 rolling + 4 terminal) and the
WP's budget is 800, so 4×600 cannot be run inside it; 4×300 costs 549 and keeps the property
under test — four near-simultaneous Stops sharing one pump worker. The two things 4×300 does
**not** confirm are the absolute Stop→final at 600 s (terminal decodes twice the audio) and
the 90 s campaign bar at that length. Per-session WER is not comparable to `QUALITY_BOUNDS`
here either: each session loops a 50–180 s clip to fill 300 s, which is the WP6/WP25
construction, and session 4's reference is partial (`wer` null by the harness's own rule).

## Prototype status

Retained as executable before/after evidence for this WP rather than deleted: it is the only
harness that reproduces the concurrent-Stop drain without a GPU. It imports production modules
but nothing production imports it.
