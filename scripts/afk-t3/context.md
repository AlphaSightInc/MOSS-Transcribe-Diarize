# Context — Phase 1 ticket #3

Iteration 8. The live issue acceptance contract and validation baseline are captured below. Numeric
latency/memory gates and their measurement semantics are frozen before measurement. A controlled
scheduler probe characterizes fairness and isolation, and the v2 canonical-queue overflow path is
now retryable and session-local. A local ARM64 vLLM image recognizes MOSS, but the shared 8.2 GB
Docker VM cannot safely host the qualifying run. The blocker persisted for iterations 6–8, so the
charter's stop-and-comment rule fired. Real dispatcher latency and memory have not been measured,
and all remaining work now waits on supervisor/operator input.

## Where things stand

- Branch: `afk/t3-*`, cut from `dev` at `a05a7f6`. Worktree 3 of 6 (treehouse pool).
- All 12 wayfinder decision tickets are **closed**. Design is settled; this is execution.
- Target repo `frontend/` is empty. `/` currently serves the inline Subtitle Studio.
- Live routes are default-off and enabled via `create_app(live_enabled=True, ...)`.

## Read these first (do not re-derive)

| Path | Why |
|---|---|
| `docs/phase1-afk-charter.md` | **Binding.** Authority, limits, capture spec §4, fidelity method §5, gates §6, attended checklist §7 |
| `.wayfinder/map-001-phase1-chrome-client.md` | Premises C1–C11 and the decision index |
| `.wayfinder/tickets/` | The 12 closed decision tickets with full rationale |
| `docs/research-chrome-capture-mvp-2026-08-03.md` | Gate 1 measured verdict. Frame geometry, worklet clock anchoring, activation ordering, error taxonomy — all settled |
| `AGENTS.md` | Measure-before-implement is mandatory |
| `CONTEXT.md` | Domain glossary. Use its vocabulary |

## Known traps, already paid for once

- `scripts/ralph-afk/` holds a **stale 285 KB `context.md` and an old PRD** from the earlier
  native-helper effort. **It is not yours. Ignore it.** Your loop lives in `scripts/afk-t3/`.
- Frame geometry is deploy-manifest data, never a code constant.
- 429 on the v2 lane path is non-terminal; on the legacy mono path it is terminal. Only ever send
  v2 lane frames.
- `setInterval` in a backgrounded tab collapses to ~1/min. Worklet port messages do not.
- `source_revision` comes from the provider manifest and must be re-finalized per host.

## Issue #3 acceptance checklist

Authoritative source: <https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/3>, read live
on 2026-08-13. These seven items are the ticket gate; do not add or substitute criteria.

- [ ] State numeric latency and memory gates before measuring; do not choose them afterward.
- [ ] Measure dispatcher concurrency 1, 2, and 4 with real 0.5 s ingress and real speech spans,
  not synthetic frames.
- [ ] At 1, 2, 4, and 8 simultaneous meetings, record real-time factor, p95 transcript lag,
  fairness across sessions, per-session queue depth, GPU OOM/errors, and vLLM active/queued
  request counts.
- [ ] Choose the largest concurrency under both gates and implement it as a bounded dispatcher.
- [ ] Regression-test cross-session markers under overload and across reconnect; no session may
  receive another session's text.
- [ ] Confirm the 16-item queue bound is per session and decode lag yields 429 backpressure
  independently per client.
- [ ] Introduce no additional Uvicorn workers; process-local state makes them unsafe here.

Charter G4 additionally defines how the measured criterion is accepted: sustain the chosen bound
for at least 10 minutes, keep p95 transcript lag under the predeclared gate, provide fair
round-robin service, avoid OOM, and observe 429 per session rather than globally. G5 defines the
cross-session criterion: text never crosses under overload or reconnect. Stub evidence cannot
satisfy any real gate. The remote 4070 host remains read-only; qualifying runs must use a locally
started service.

## Validation commands

This clean worktree has no `.venv`; use the repo-supported pyenv Python 3.12.10 environment where
pytest 9.0.2 and project dependencies are already importable. Build both Swift products before
the broad Python suite because integration and packaging nodes deliberately reuse them.

```bash
swift build --package-path macos/MOSSCapture --product mtd-capture
swift build --package-path macos/MOSSCapture --product MOSSCaptureApp
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/test_live_api.py tests/test_live_auth.py tests/test_live_mixer.py \
  -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests -q -p no:cacheprovider -rs \
  --ignore=tests/test_macos_uds_tracer.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_macos_uds_tracer.py \
  -q -p no:cacheprovider -rs
bash -n scripts/afk-t3/ralph-afk.sh
```

Iteration-2 baseline: focused ticket-adjacent suite **65 passed + 351 subtests**; broad suite
excluding only the separately-run lifecycle tracer **857 passed / 4 skipped + 373 subtests**;
shell syntax and both Swift builds pass. The lifecycle tracer is a mandatory unresolved baseline
gate: isolated execution reproducibly yields **1 failed / 5 passed** because
`NSRunningApplication(processIdentifier:)` cannot resolve the just-launched lab app after its UDS
status reply. This is outside ticket #3, has not been fixed or ignored as a completion gate, and
prevents claiming the full suite green. Raw command evidence:
`evidence/phase1/t3/iteration-2-validation-baseline.txt`.

## Frozen measurement gates

Machine-readable preregistration:
`prototypes/streaming-diarization/concurrency/preregistration.json`, SHA-256
`b6fbe1f5dc60c0f0a20128026eefa8bc369a456927fe267cf94aa2a8b2865d52`.

- Latency: maximum per-session Type-7 p95 transcript lag **10.0 s**. Lag starts at the real-time
  replay clock for the span's `end_sample` and ends when the matching production
  `canonical_processed` event is observed; the 250 ms poll delay stays included.
- Memory: peak vLLM GPU-cache usage **≤0.95**, locally-started service/inference process-tree RSS
  growth over warmed idle **≤4 GiB**, and **zero** OOM/accelerator errors. Missing vLLM metrics
  fail qualification; they are never interpreted as zero.
- Fairness: completed-dispatch count skew across continuously ready sessions **≤1**.
- Selection: largest dispatcher concurrency in `{1,2,4}` that passes its same-count run and a
  **600 s** soak. The 8-meeting run proves overload/cross-session/independent-429 behavior and does
  not relax normal-load latency.

Local capability inspection found an M3 Ultra with 256 GiB unified memory and usable Torch MPS.
Iteration 6 found an official ARM64 CPU vLLM `0.27.1` image that registers the MOSS architecture,
but its shared Docker VM exposes only 8.2 GB and already hosts unrelated workloads. A real startup
attempt never reached health or metrics, and Docker's API became unresponsive before checkpoint
weights downloaded. Restarting or resizing Docker would disrupt unrelated workloads and was not
attempted. Iteration 7 confirmed Docker is again responsive but still has 16 unrelated containers,
only 665 MB available, and effectively exhausted swap. No second container runtime or host vLLM is
installed, and the MOSS cache still contains no weights. Iteration 8 independently confirmed the
same state. This is the third consecutive blocked iteration, so charter §8 required stopping and
commenting on issue #3. The preregistration remains valid, but a real qualifying run is not
currently available. Raw evidence:
`evidence/phase1/t3/iteration-3-gate-preregistration.txt`,
`evidence/phase1/t3/iteration-6-local-vllm-smoke.txt`, and
`evidence/phase1/t3/iteration-7-resource-isolation-audit.txt`, and
`evidence/phase1/t3/iteration-8-stop-gate.txt`. Supervisor escalation:
<https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/3#issuecomment-5277031654>.

## Controlled scheduler evidence

`prototypes/streaming-diarization/concurrency/proto_controlled_dispatcher.py` hash-pins the frozen
preregistration and a 59.584 s real human-speech WAV. It replays real PCM at a 0.5 s wall-clock
cadence through `LiveServiceRuntime` and its production round-robin drain, with controlled speech
observations, decoder, identity, and scheduler release. These controls and the absence of vLLM
metrics make every result explicitly non-gating.

- 1/2/4/8 meetings each completed four dispatches per session; maximum prefix count skew was
  `0/1/1/1`, satisfying the frozen mechanical fairness gate.
- Controlled transcript markers stayed within their session, including a replacement runtime
  session. HTTP reconnect and resumable transport remain untested.
- One stalled session reached exactly 16 pending items while its peer accepted a frame, confirming
  the queue object and capacity are per session.
- The historical run exposed that first overflow raised raw `InferenceArbiterBackpressure` and
  terminalized the session. Iteration 5 repaired this at the production v2 transport/mixer/runtime
  seam; the iteration-4 artifact remains the before-fix evidence.

Raw evidence: `evidence/phase1/t3/iteration-4-controlled-dispatcher.json`.

## V2 canonical-queue backpressure repair

Canonical queue capacity is checked under the session runtime lock before v2 mono admission. A
full queue now returns a typed retryable 429 on the first response without advancing the mono frame
sequence or recording a terminal failure. The retained v2 frame can be retried identically after a
dispatch frees capacity. A second session continues accepting independently. Legacy mono admission
does not opt into this non-terminal policy.

The regression traverses HTTP, v2 ingress, the compatibility mixer, runtime, per-session arbiter,
and a controlled manual scheduler. It proves transactionality and per-session isolation but uses a
controlled decoder and speech observations, so it does not satisfy real G4/G5 evidence.
Raw evidence: `evidence/phase1/t3/iteration-5-v2-backpressure.txt`.

## Ranked candidates

No safe autonomous candidate remains.

1. **Blocked on supervisor/operator input:** provide an operator-approved Docker maintenance and
   resize window, or another resource-isolated local runtime with enough memory and the required
   vLLM metrics. Do not substitute the read-only remote service.
2. After that input, run the preregistered real 1/2/4/8 matrix and 600 s soak, select the largest
   passing bound, then implement the smallest bounded-dispatcher vertical slice. No implementation
   is authorized by evidence before that measurement.
