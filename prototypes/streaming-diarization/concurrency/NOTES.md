# Concurrency prototype notes

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
