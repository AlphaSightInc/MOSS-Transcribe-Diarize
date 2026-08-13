---
id: T-04
map: map-001-phase1-chrome-client
title: Gate 3 — bounded inference concurrency for 2-4 live sessions
type: prototype
status: closed
assignee: claude
blocked_by: []
---

## Question

C4 targets 2–4 concurrent live sessions. Decode is serialized today. What concurrency bound
does Phase 1 deploy, and what evidence sets it?

This is the research doc's **Gate 3**, unrun. It needs a GPU window (the 4070 Ti was observed
at 15,641 / 16,376 MiB used — effectively full), so it is independent of every UI ticket and
should be scheduled whenever the GPU is free.

Resolve by measurement, per the target repo's `AGENTS.md` measure-before-implement rule.
Extend the existing bench at `prototypes/streaming-diarization/` rather than rebuilding
measurement scaffolding.

1. Prototype dispatcher concurrency **1, 2, and 4** using real 0.5 s ingress and real speech
   spans — not synthetic frames.
2. For **1, 2, 4, and 8** simultaneous meetings measure: real-time factor, p95 transcript lag,
   fairness across sessions, per-session queue depth, GPU OOM/errors, and vLLM
   active/queued request counts.
3. Pick the largest concurrency that stays under the latency and memory gates — and state
   those gates as numbers before running, not after.
4. Regression-test cross-session markers under overload and across reconnect: no client may
   ever see another client's text.
5. Confirm the 16-item queue bound is per session and that decode lag produces **429
   backpressure independently per client** (v2 lane 429 is non-terminal; the legacy mono
   path's is terminal — Phase 1 must only ever send v2 lane frames).
6. Decide what the UI must show when a client is being backpressured or queued behind other
   sessions. Feeds the control triage.

Constraints that are already settled — do not re-litigate:

- **Do not** add Uvicorn workers. Device state, session ownership, runtime objects, mixers,
  event queues, and view grants are process-local; two workers can disagree about a
  token/session and route unsafely.
- Duplicating the full model almost certainly does not fit the observed GPU state. Measure
  one vLLM engine's batching first.

Ground truth: `moss_transcribe_diarize/app/live_service_runtime.py`
(`_TransientCanonicalPumpScheduler`); `docs/research-chrome-capture-mvp-2026-08-03.md`
§"Real multi-client bottleneck" and §"Gate 3"; `prototypes/streaming-diarization/README.md`
and `NOTES.md`.

## Resolution (2026-08-13) — graduated to implementation

The decision this ticket held was *how the bound gets chosen*, and that is settled: **by
measurement, gates stated as numbers before the run**. The measurement and the resulting
dispatcher are now implementation ticket **#3** on the private tracker
(`aiSight-us/MOSS-Transcribe-Diarize`), whose acceptance criteria carry the full method.

Operator ruling 2026-08-13: the GPU on `ga0-alienware-rtx4070ti` is available **without
scheduling limitation**, so there is no GPU-window constraint. However the AFK charter makes that
host **read-only** for overnight agents, so #3 measures against a locally-run service.

Gate G4 in `docs/phase1-afk-charter.md` §6 is the acceptance bar: the chosen bound sustained
≥10 minutes, p95 lag under the stated gate, fair round-robin, no OOM, and 429 backpressure
appearing per session rather than globally.
