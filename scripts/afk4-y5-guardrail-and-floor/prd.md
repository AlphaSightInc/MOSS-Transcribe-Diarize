# PRD — y5-guardrail-and-floor

## Goal

Two hardening jobs that protect every other ticket's evidence. Do them in this order.

### 1. Adversarial fixtures for the preflight guardrail

The evidence-citation check in `scripts/afk-guardrails/preflight.py` (`check_forbidden`) had two
blind spots, both exploited during AFK3. They were repaired on 2026-08-16 — **but only smoke-tested
ad hoc. There is no committed regression fixture, so nothing stops them reopening.** An independent
review (Codex, 2026-08-16) called this out and it is correct.

**Bar:** a committed test that would **fail** against the pre-repair guardrail and passes against
the current one. At minimum it must cover:

- an artifact citing a runner whose filename contains neither `probe` nor `proto` (e.g.
  `run-final-gate.sh`, `regenerate_evidence.py`) which is **absent** from the tree → violation
- an artifact citing a Python runner that **exists but does not compile** → violation
- an artifact citing `module.py:88` — a traceback frame, not a runner claim → **no** violation
- an artifact citing an absolute path outside the repo → **no** violation
- the current tree → **zero** violations

Build the fixtures as real files under a temp tree, not by monkeypatching internals. A test that
mocks the thing it is testing is the same class of defect this guardrail exists to catch.

**Then state plainly, in the test and in the ledger, what it still does not cover:** compiling proves
a file parses, not that it runs. A probe importing a deleted module or failing against current `dev`
still passes. Do not close that gap by executing arbitrary probes inside a per-iteration preflight —
these probes drive Chrome for minutes.

### 2. A derived canonical queue-depth floor — failing test first

Weighted admission (`1db447c`) means a frame whose predicted span weight exceeds `max_queue_depth`
can never be admitted: `accept_frame` returns retryable backpressure forever
(`live_service_runtime.py:516-533`).

**Measured 2026-08-16, before you start — do not re-derive, and do not trust a closed-form formula:**

| endpoint geometry | worst spans / frame | worst Stop tail | floor |
|---|---|---|---|
| deployed (`min_speech 1600`, `min_silence 8000`, `pad 1600`, `hard_cap 40000`) | 1 | 1 | **1** |
| no hard cap | 1 | 1 | **1** |
| aggressive (`min_speech 160`, `min_silence 320`, `pad 0`, `hard_cap 1600`) | **25** | 1 | **25** |

Two facts that shape the work:

- **Nothing is broken at the shipping geometry.** `min_silence_samples` equals `frame_samples`, so at
  most one span closes per frame, and `_positive` already guarantees `max_queue_depth >= 1`.
- **The Stop tail is never binding.** `_close_open_partition` (`live_endpoint.py:155-165`) emits
  hard-cap spans *during* `observe()`, so the open partition never exceeds one hard cap. An
  adversarial search over 2268 geometry combinations found a Stop tail of exactly 1 every time. The
  `TimeoutError` at `live_service_runtime.py:643` is therefore unreachable — **do not "fix" it.**

The hazard is real but conditional: it appears only if endpoint config is tightened.

**Bar, in this order:**

1. A **failing seam test** that constructs a geometry whose worst-case frame exceeds a configured
   `max_queue_depth`, and demonstrates the permanent-retry outcome. This must fail before your guard
   exists. Without it, the guard is unjustified — the earlier closed-form derivation predicted 25 for
   the deployed geometry where the true answer is 1.
2. Then the guard: at manifest finalization, instantiate the **configured** `EndpointPolicy`, drive
   one `frame_samples` frame with the worst-case pattern, count the spans, and require
   `max_queue_depth >= that`. It cannot drift from the policy because it *is* the policy.
3. The guard must fail at **config load**, not at runtime, with a message naming the computed floor
   and the configured value.

It cannot live in `LiveServiceBounds.__post_init__` (`live_service_runtime.py:139-148`) — that
dataclass cannot see endpoint geometry. It belongs where both `endpoint_config` and `bounds_config`
are in hand: `live_manifest_finalizer.py`, or the bundle-level validation in
`live_provider_bundle.py` that already holds both on one config object.

## Evidence

Commit raw artifacts under `evidence/phase1/y5-guardrail-and-floor/`, including the re-runnable
probes. Show the seam test failing before the guard and passing after.

## Guardrails (enforced — the loop stops on violation)

`RALPH_PREFLIGHT_REQUIRED=1` runs `scripts/afk-guardrails/preflight.py y5-guardrail-and-floor` before
every iteration. You own `scripts/afk-guardrails/` and
`moss_transcribe_diarize/app/live_manifest_finalizer.py`, plus your own loop dir,
`evidence/phase1/`, `docs/`, `tests/`.

**You own the guardrail that gates every other ticket.** A change that makes preflight more
permissive, or that stops it running, is the most damaging thing you could ship. Every guardrail
change needs a fixture proving it still catches what it caught before.

`moss_transcribe_diarize/app/live_service_runtime.py`, `live_endpoint.py` and `live_provider_bundle.py`
are **read-only for you** unless the bundle-level validation seam genuinely requires an edit — in
which case make it minimal and say so on the issue.

## Hard constraints

- Push **your own branch only**, to remote `private`. Never push `dev` or `main`. Never force-push.
- You may not close GitHub issues. Comment evidence; the orchestrator closes.
- Do not weaken a test to make a gate pass.
- Never hardcode frame geometry; `frame_samples` / `sample_rate` are deploy-manifest values.
- Binding authority: `docs/phase1-afk-charter.md`, `docs/phase1-gate-status.md`, `AGENTS.md`.
