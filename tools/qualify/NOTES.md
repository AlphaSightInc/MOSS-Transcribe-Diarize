# WP21 prototype verdict

Question: can unchanged benches be composed into an isolated, content-safe result ledger?
Primitives: invocation, observed result, isolated resources, retained numeric evidence.
Invariants: missing observations never pass; byte-exact asset restoration; all started
processes stopped; decoder calls use own 18121 tunnel; no content or secrets retained.
Unknowns: live statuses, request cost, determinism. No new quality threshold.
Falsifier: omitted rows, escaped writes, fabricated pass, retained transcript or key.
Tool decision: inspect actual interfaces and exercise the existing layout check before
implementation; unsupported isolation arguments change the ledger to UNRUNNABLE.

One command: `PYTHONDONTWRITEBYTECODE=1 python tools/qualify/prototype.py` (throwaway,
removed after absorption). Output: `evidence/mvpfix/wp21/prototype.jsonl`.
Five real source witnesses found / five inspected; layout check exit 0. Partial
composition supported; complete acoustic qualification cannot run unchanged today.
Browser all restarts WP5 stack via 18105; identity cannot select base/output; WP16
queries 18116; capacity owns 18106. These require upstream interface work, not copied
bench algorithms or silently redirected globals. WP21 records each missing case.
Batch JSON state replaces interactive TUI for repeatable inspection. No product change.

Raw command output lives only in ignored scratch: tests/errors can contain transcripts.
Retained logs are counts/status projections; this deliberately qualifies the request for
raw logs to satisfy the stronger no-transcript/no-secret requirement. Manifest SHA is
explicitly required identity evidence. Shared metrics are sampled, own proxy counts exact.
