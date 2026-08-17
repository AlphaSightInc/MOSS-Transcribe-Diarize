# PRD — y4-concurrency-cert

## Goal

**Certify gates G4 and G5. Both are currently unmet, and the existing artifact says so itself.**

`evidence/phase1/t3/iteration-4-controlled-dispatcher.json`:

```
qualifies_g4_or_g5                          : false
correct_nonterminal_429_semantics_observed  : false
all_markers_isolated                        : true
fairness_skew_within_frozen_gate            : true
queue_capacity_is_session_local             : true
```

Nothing in `evidence/` sustains the measured bound for ten minutes, and **no p95 transcript-lag
figure exists anywhere in this repo.**

### G4 — concurrency (charter §6)

> The measured bound from ticket #3 sustained for **≥10 minutes** at that concurrency, with p95
> transcript lag under the stated gate, fair round-robin service, no OOM, and 429 backpressure
> appearing **per session** rather than globally.

The concurrency target is **2–4 concurrent live sessions, measured** (map-001 C4).

**Bar:** one ≥10-minute run at the ticket-3 bound that records, as raw arrays not summaries:
per-session commit-to-render latency (report p50/p95/max), round-robin fairness skew, process RSS
across the run, and every 429 with its session id. `correct_nonterminal_429_semantics_observed`
must become **true** — on the v2 lane path a 429 is non-terminal backpressure and the session must
survive it (charter §4).

### G5 — cross-session integrity (charter §6)

> Under overload and across reconnect, no session ever receives another session's text.

`t1/iteration-12` and `iteration-14` already prove marker isolation for **two** sessions on short
runs. What is missing is **overload** and **reconnect**. Note the criterion is *text never crosses*,
not *reads are forbidden* — T-01 accepted a single trust domain, so the historical `403` cross-read
result is explicitly **not** a criterion.

**Bar:** isolation holds while the queue is saturated and 429s are firing, and across a session
that disconnects and reattaches mid-run.

## Prerequisite — read this before iteration 1

`preflight.py` requires `model_runtime` and **will stop this loop immediately if none is
reachable.** That check exists because ticket 3 once spent eight iterations building scaffolding for
a measurement it could never run. One of these must be true:

- `pretrained/moss-transcribe-diarize/` present locally (`ops/download-model.sh`), or
- `MOSS_VLLM_BASE_URL` set, or
- `MOSS_MEASUREMENT_SSH_HOST` set and reachable over `ssh -o BatchMode=yes`.

If preflight stops you for this, **do not build scaffolding anyway.** Record the blocker in
`context.md`, comment on the issue, and stop. That is the correct outcome, not a failure.

## Evidence

Commit raw artifacts under `evidence/phase1/y4-concurrency-cert/`, including the re-runnable probe
itself. Extend `prototypes/streaming-diarization/concurrency/` rather than rebuilding measurement
scaffolding (`AGENTS.md` mandates measure-before-implement).

Pre-register the gate thresholds **before** the run and commit that registration, as
`iteration-3-gate-preregistration.txt` did for ticket 3. A threshold chosen after seeing the numbers
is not a gate.

State plainly in your evidence what the run does **not** cover.

## Guardrails (enforced — the loop stops on violation)

`RALPH_PREFLIGHT_REQUIRED=1` runs `scripts/afk-guardrails/preflight.py y4-concurrency-cert` before
every iteration. You own `prototypes/streaming-diarization/concurrency/` and
`evidence/phase1/y4-concurrency-cert/`, plus your own loop dir, `docs/`, `tests/`.
`moss_transcribe_diarize/app/live_service_runtime.py` is **read-only for you** — if the measurement
proves a runtime defect, record it and escalate; do not fix it here.

## Hard constraints

- The GPU host `ga0-alienware-rtx4070ti` is **READ-ONLY**. Never restart, reconfigure, deploy to, or
  send a mutating request to `moss-live-web`, `moss-vllm`, or `moss-web`. Measure against a
  locally-run service you start yourself, on a port you own.
- **Do not add Uvicorn workers** to solve concurrency (charter §8). Device state, session ownership,
  runtime objects, mixers, event queues and view grants are process-local; two workers can disagree
  about a token or session and route unsafely.
- Decode is **serialized today**: one `_TransientCanonicalPumpScheduler` worker drains sessions
  round-robin. Ingest is concurrent and fair; decode is not parallel. Measure what is, not what you
  wish were true.
- Push **your own branch only**, to remote `private`. Never push `dev` or `main`. Never force-push.
- You may not close GitHub issues. Comment evidence; the orchestrator closes.
- Do not weaken a test to make a gate pass.
- Binding authority: `docs/phase1-afk-charter.md`, `.wayfinder/map-001-phase1-chrome-client.md` (C4),
  `docs/phase1-gate-status.md`, `AGENTS.md`.
