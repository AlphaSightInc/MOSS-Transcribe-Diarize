# Context — Phase 1 ticket #3

Iteration 3. The live issue acceptance contract and validation baseline are captured below. Numeric
latency/memory gates and their measurement semantics are now frozen before measurement. Dispatcher
latency and memory have not been measured yet.

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

Local capability inspection found an M3 Ultra with 256 GiB unified memory and usable Torch MPS,
but no local `vllm` executable/module, no cached MOSS model in the standard locations, and no local
MOSS endpoint (`127.0.0.1:8000/v1/models` returns 502; LM Studio on 1234 advertises unrelated
models). Therefore the preregistration is valid, but a real qualifying run is not currently
available. Raw evidence: `evidence/phase1/t3/iteration-3-gate-preregistration.txt`.

## Ranked candidates

1. Add the smallest hash-pinned concurrency runner to the standing bench and measure dispatcher
   fairness, per-session queue depth, independent 429 behavior, and cross-session markers with a
   controlled decoder. Label the result non-gating unless a real local MOSS/vLLM path becomes
   available.
2. Establish a real local MOSS/vLLM measurement path; without local vLLM active/queued metrics, G4
   cannot qualify. Do not substitute the read-only remote service.
3. Smallest evidence-backed vertical slice toward the bounded dispatcher, only after prototype
   measurements choose the bound.
