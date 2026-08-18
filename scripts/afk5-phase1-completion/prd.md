# PRD — afk5-phase1-completion

## Goal

Take Phase 1 from **5 gates certified** to **all 10**, and every tracker issue to closeable.
This is the last cycle. Work the backlog below **in order** — later items genuinely depend on
earlier ones.

Authoritative current state is `docs/phase1-gate-status.md`. Read it first; it is maintained and it
is honest about what is not covered. Do not re-derive numbers it already carries.

Certified: G1, G2, G7, G8, G10. Plus G6's local real-browser bar (19/19 assertions, each falsified
against a corrupted observation).

---

## W0 — a live service that starts on this host  ← DO THIS FIRST, everything waits on it

`--live` requires `--live-provider-manifest`, and **no provisional or finalized manifest exists in
this repo**. So nobody can currently start the live routes locally, which blocks G3, G4 and G5 at
once. This is the single highest-leverage item in the backlog.

`ops/finalize-live-provider-manifest.py` is the tracked tool; `--help` gives its arguments. The
deployed host advertises the shape you must match — read it (read-only, this is allowed):

```
curl -sSk https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861/api/live/descriptor
```

It reports `provider_name: moss-rtx-webrtc-wespeaker`, its `provider_revision`, and the deployed
geometry. **Charter §8's provider-manifest trap applies:** `source_revision` comes from the manifest
and must be re-finalized per host — do not copy the deployed host's revision onto ours.

**Bar:** `scripts/g3-attended-session.sh` starts a working live service on `127.0.0.1:7861` over TLS
with a shared bearer, against `MOSS_VLLM_BASE_URL`. Prove it by fetching `/api/live/descriptor` from
the *local* service and creating a session. Commit the recipe and the manifest. If
`MOSS_VLLM_BASE_URL` is unset or unreachable, say so in `context.md` and continue to W1 — do not
fabricate a model.

## W1 — file mode cannot send its bearer (issue #8, last criterion)

y7 guarded all four job routes and proved it over real TLS (`401,401,401,401` for missing/wrong,
`200,200,200,200` for correct — `evidence/phase1/y7-jobs-auth-and-export-caveat/iteration-6-uvicorn-job-route-auth.json`).
It then correctly **stopped** rather than exceed its scope, recording this:

> `App` unmounts `ControlPanel` on file mode, `captureBearer` is component-local, and `FilePanel`
> calls `submitJob(selectedFile)` without options — an adapter-only change cannot transmit a bearer
> that has no surviving source.

**Bar:** lift the bearer to a single memory-only owner above both panels so file mode can send it.
It must remain **memory only** — never `localStorage`, never a query parameter (issue #2's criterion
is still binding, and #2 is closed on that basis). Switching Live ↔ File must not drop it. Add
component coverage proving a file upload carries the header and that an unauthenticated upload is
refused.

## W2 — G4 and G5  (needs W0, and needs `MOSS_VLLM_BASE_URL` reachable)

G4 bar: the ticket-3 bound sustained **≥10 minutes**, p95 transcript lag under the stated gate, fair
round-robin, no OOM, and 429 backpressure appearing **per session** not globally.
G5 bar: under **overload** and across **reconnect**, no session ever receives another session's text.

The existing prototype declares its own insufficiency — `qualifies_g4_or_g5: false`,
`correct_nonterminal_429_semantics_observed: false`. Both must become true.

**Pre-register the thresholds and commit that registration before the run.** A threshold chosen
after seeing the numbers is not a gate. Extend `prototypes/streaming-diarization/concurrency/`.

Note honestly in the evidence that the model is reached over the tailnet, so latency includes
network transit and the figures are not a pure-GPU bound.

## W3 — package the operator's G3 evidence  (only after the attended run happens)

The operator runs charter §7 themselves; **no agent may claim G3 or automate the display picker**
(charter §1 — the standard requires a fresh gesture per capture; the 2026-08-03 CDP-flag attempt
failed with `NotReadableError`). Do not retry it.

When `evidence/phase1/g3-attended/` gains a raw session log, verify it against the §7 expectations —
exact `frame_samples` frames, no sequence gaps, 0.5 s capture-timestamp deltas, zero fetch errors,
both lanes non-zero RMS — and write the verdict. If the directory holds only the fixture wav, this
item is not ready; skip it and say so.

## W4 — reconcile the ledger

Every gate row must match measured reality with its evidence path and an explicit statement of what
that evidence does **not** cover. Charter §3 requires it and nothing else enforces it.

---

## How to work

- **One logical change per iteration.** Validate with the smallest command that produces real
  evidence.
- **Write assertions that can fail.** Two of G7's assertions were tautologies that survived weeks of
  review; y6 set the standard by falsifying all 19 of its checks against corrupted inputs. Match it.
- **A gate satisfiable by stub evidence is not satisfied** (charter §3). State plainly what each run
  does not cover.
- **If blocked, say so and move to the next item.** A well-documented blocker is a good iteration; a
  fabricated pass is not.

## Hard constraints

- The GPU host `ga0-alienware-rtx4070ti` is **READ-ONLY**: probe `/api/live/descriptor` and send
  inference requests to `MOSS_VLLM_BASE_URL`. **Never** restart, reconfigure, deploy to, or send any
  mutating request to `moss-live-web`, `moss-vllm` or `moss-web`.
- **Do not add Uvicorn workers.** Device state, session ownership, runtime objects, mixers, event
  queues and view grants are process-local.
- Never hardcode frame geometry — `frame_samples` / `sample_rate` are deploy-manifest values.
- Never automate the display-capture picker.
- Push **your own branch only** to `private`. Never `dev`, never `main`, never force-push.
- **You may not close GitHub issues.** Comment evidence; the monitor closes them.
- Do not weaken a test to make a gate pass. Do not touch the l15 pin or the l2-stage0 corpus — those
  two failures are permanent Phase 1 baselines.
- Baseline to protect: pytest **2 failed / 1066 passed / 396 subtests**; frontend **110/110**.
- Binding authority: `docs/phase1-afk-charter.md`, `.wayfinder/map-001-phase1-chrome-client.md`,
  `docs/phase1-gate-status.md`, `AGENTS.md`.
