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

## Verdicts

See `## Results` below — filled in after the runs.
