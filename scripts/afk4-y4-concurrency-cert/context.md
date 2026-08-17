# context — y4-concurrency-cert

Living working memory. Update it every iteration so it matches reality. History goes in progress.txt.

## BLOCKER — check this first

`preflight.py` requires `model_runtime`. As of 2026-08-16: `pretrained/moss-transcribe-diarize/`
**absent**, `MOSS_VLLM_BASE_URL` **unset**, `MOSS_MEASUREMENT_SSH_HOST` **unset**. The loop will stop
at iteration 0 until the operator provides one.

If that is still true: record it here, comment on the issue, stop. **Do not build scaffolding for a
measurement you cannot run** — that is the exact failure this prerequisite check was added to prevent
(ticket 3 lost eight iterations to it).

## Known state (verified 2026-08-16, `dev` @ 5b20a95)

- `evidence/phase1/t3/iteration-4-controlled-dispatcher.json` self-declares
  `qualifies_g4_or_g5: false` and `correct_nonterminal_429_semantics_observed: false`.
  It does record `all_markers_isolated: true`, `fairness_skew_within_frozen_gate: true`,
  `queue_capacity_is_session_local: true`.
- No 10-minute run and **no p95 transcript-lag figure exists anywhere in this repo**.
- `t1/iteration-12` and `iteration-14` prove marker isolation for 2 sessions on short runs, plus
  `per_session_backpressure_observed: true`. Missing: overload, and reconnect.
- Concurrency target is 2–4 concurrent live sessions, measured (map-001 C4).
- Decode is serialized: one `_TransientCanonicalPumpScheduler` worker, round-robin. Ingest is
  concurrent and fair. Measure what is.

## Candidates (ranked; re-rank as you learn)

1. Resolve or report the model-runtime blocker. Nothing below is reachable without it.
2. Re-establish the ticket-3 bound on this host — do not assume the old number transfers.
3. Pre-register gate thresholds and commit that registration **before** the run.
4. The ≥10-minute run: raw per-session latency arrays, fairness skew, RSS, every 429 with session id.
5. Overload isolation and reconnect isolation for G5.

## Not yours

`live_service_runtime.py` is read-only. If the measurement proves a runtime defect, record and escalate.
