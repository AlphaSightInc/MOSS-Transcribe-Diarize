# Concurrency prototype notes

## CPU/HF-local gate preregistration — 2026-08-18

**VERDICT: FROZEN, NOT RUN — a separately hash-pinned contract for the now-available local HF path.**

Question: at the descriptor geometry observed on the read-only deployed host, can one local CPU/HF
service sustain the measured two-to-four-session bound for 600 seconds while retaining fair,
session-local v2 backpressure and no cross-session text across overload and observer reconnect?

`cpu_hf_local_preregistration.json` is intentionally separate from the 2026-08-13 vLLM profile:
the old file remains the historical record for its controlled prototype, while this one freezes the
CPU/HF-local run before any result exists. Its validator prints the full contract and SHA-256 in one
command. The runner must use the real decoder, real human speech at wall-clock cadence, one local
service process, and descriptor-derived geometry; controlled collaborators cannot qualify it.

Frozen gates: per-session p95 transcript lag at most 10.0 s using linear Type-7; local process-tree
RSS growth at most 4 GiB from warmed idle; zero OOM/accelerator errors; continuously ready dispatch
skew at most one; retryable non-terminal v2 429 for a saturated session while its peer continues;
and marker isolation through overload plus observer reconnect. Raw arrays, not summaries, are
required. The CPU/HF-local latency column must always read **"CPU HF local decode, not the deployed
GPU bound"**. This profile explicitly cannot prove deployed GPU p95 latency, GPU memory, or GPU
utilisation.

## Gate preregistration — 2026-08-13

**VERDICT: PASS — numeric gates and measurement semantics frozen before measurement.**

Machine-readable preregistration SHA-256:
`b6fbe1f5dc60c0f0a20128026eefa8bc369a456927fe267cf94aa2a8b2865d52`.

- Latency: maximum per-session p95 transcript lag must be at most `10.0 s` (linear Type-7).
- Memory: vLLM GPU-cache usage must stay at or below `0.95`; locally-started service and inference
  process-tree RSS may grow at most `4 GiB` above warmed idle; OOM/accelerator errors must be zero.
- Fairness: continuously ready sessions may differ by at most one completed dispatch.
- Selection: choose the largest of `1, 2, 4` that passes its same-count run and a 600-second soak.
  The eight-meeting run is overload evidence, not a relaxed normal-load latency gate.

Lag is measured from the real-time replay clock at a span's `end_sample` until the observer receives
the matching production `canonical_processed` event. This intentionally includes the 250 ms poll
interval. Queue depth is sampled per session. Raw vLLM active/queued series are mandatory; a missing
series does not become zero.

Host capability inspection found an Apple M3 Ultra with 256 GiB unified memory and usable Torch MPS,
but no local `vllm` executable/module, no cached MOSS model, and no responding local MOSS endpoint.
The running LM Studio endpoint advertises unrelated models. Therefore this preregistration passes,
but a real qualifying measurement remains unavailable until a local MOSS/vLLM path exists. A later
stub run may measure dispatcher mechanics only and cannot satisfy G4/G5.

## Controlled scheduler probe — 2026-08-13

**VERDICT: PARTIAL — fairness, marker isolation, and per-session capacity pass; required
non-terminal 429 semantics fail. This run does not qualify G4 or G5.**

`proto_controlled_dispatcher.py` replayed the hash-pinned 59.584 s human-speech fixture in real
0.5 s wall-clock frames through `LiveServiceRuntime` and its production round-robin drain. Decode,
identity, speech observations, and scheduler release were controlled, and no vLLM metrics existed.

- At 1, 2, 4, and 8 meetings, every session completed four dispatches. Maximum prefix dispatch
  skew was respectively `0, 1, 1, 1`, within the frozen `<=1` fairness gate.
- All session markers remained isolated, including a replacement runtime session. This does not
  exercise HTTP reconnect or resumable transport.
- Holding decode filled one session to exactly 16 pending items while its peer still accepted a
  frame, proving the queue instance and capacity are session-local on this path.
- The first overflow raised raw `InferenceArbiterBackpressure` and marked the saturated session
  terminal. Only the following retry raised typed transport pacing that maps to HTTP 429. Therefore
  this path does not yet provide the required first-response, non-terminal 429 behavior.

Raw result: `evidence/phase1/t3/iteration-4-controlled-dispatcher.json`.

Iteration 5 repaired the production v2 HTTP path exposed by this historical run. Canonical-queue
capacity is now checked under the per-session runtime lock before mono admission: the first refusal
is a retryable typed 429, leaves the mono session non-terminal and unconsumed, does not block a peer,
and an identical retained-v2-frame retry succeeds after one dispatch frees capacity. The regression
uses the real HTTP transport, v2 ingress, mixer, runtime, arbiter, and manual scheduler; its decoder
and speech observations remain controlled, so it proves queue transactionality rather than G4/G5.
Raw result: `evidence/phase1/t3/iteration-5-v2-backpressure.txt`.

## Local ARM64 vLLM smoke — 2026-08-13

**VERDICT: PARTIAL, NON-GATING — engine and MOSS registration pass; serving and metrics remain
blocked by the shared Docker VM.**

The official `vllm/vllm-openai-cpu:latest-arm64` image (digest
`sha256:e6745d7ba6610f637c6f22fc06cd730342e50245b6c46767235600483adfbbde`) runs vLLM `0.27.1`
and registers both `MossAudioModel` and `MossTranscribeDiarizeForConditionalGeneration`. This
retires the claim that no local vLLM engine is available.

The real startup attempt did not reach `/health`, `/v1/models`, or `/metrics`. Docker Desktop's
shared ARM64 VM exposes only 8.2 GB and already hosts unrelated workloads; its API became
unresponsive before checkpoint weights downloaded. The agent did not restart or reconfigure
Docker because doing so would disrupt those workloads. No decoder request or required vLLM metric
was measured, so G4/G5 remain unsatisfied. Raw result:
`evidence/phase1/t3/iteration-6-local-vllm-smoke.txt`.

## Resource-isolation recheck — 2026-08-13

**VERDICT: BLOCKED, NON-GATING — no safe isolated local runtime is currently available.**

Docker recovered after iteration 6, but it is still the host's only installed Linux container
runtime. Its shared VM remains limited to 8.2 GB; 16 unrelated containers leave only 665 MB
available and its 1 GiB swap is effectively exhausted. Host Python has no vLLM module, and the
MOSS Hugging Face cache contains only the 2.3 KiB configuration blob rather than model weights.

No service was started and no shared workload was changed. A qualifying run still needs an
operator-approved Docker maintenance window or another resource-isolated local runtime. Raw
result: `evidence/phase1/t3/iteration-7-resource-isolation-audit.txt`.

## Three-strike stop gate — 2026-08-13

**VERDICT: BLOCKED — supervisor input required; no safe autonomous candidate remains.**

Iteration 8 independently found the same local-runtime blocker as iterations 6 and 7: Docker is
the only installed Linux runtime, its shared 8.2 GB VM still carries 16 unrelated containers,
host Python has no vLLM, and the MOSS cache contains no model weights. The charter's
three-consecutive-blocked-iterations rule therefore fired. Issue #3 was updated with the exact
blocker and a request for an operator-approved Docker maintenance/resize window or another
resource-isolated local runtime.

No dispatcher bound was guessed or implemented. The controlled results remain non-gating, and the
real G4/G5 measurement remains a prerequisite. Raw result:
`evidence/phase1/t3/iteration-8-stop-gate.txt`.
