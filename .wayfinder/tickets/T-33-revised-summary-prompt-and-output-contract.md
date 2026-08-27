---
id: T-33
map: map-002-phase2-multiuser
title: Revised summary prompt and deterministic output contract
type: prototype
status: closed
assignee: codex-20260826
blocked_by: [T-31]
---

## Question

What is the simplest revised summary prompt plus deterministic browser-side output contract
that corrects T-31's measured quantity omissions, unsupported quantity, and 25-word-limit
failures without giving up full-transcript factual retention or making summary latency
unacceptable?

Extend the throwaway `prototypes/client-configured-llm/` bench; do not write Phase-2 product
code. Use the same browser-owned `qwen/qwen3.6-35b-a3b` configuration and the same frozen
non-holdout split. Measure every available eligible reference, preserve the exact
available/manifest denominator, keep all blind-holdout content unopened, and report absent
shapes or semantic quality as `unmeasured`.

Compare only the smallest credible replacements surfaced by T-31:

- a revised prompt alone; and
- that same prompt with deterministic contract feedback inside the existing maximum of three
  JSON attempts (schema, summary <=25 words, topics 2–4, valid timestamps, every digit-bearing
  transcript quantity present verbatim, and no unsupported digit-bearing value).

Do not truncate model text or synthesize missing facts after inference. A contract failure may
re-ask with the exact missing/unsupported fields, but it must preserve the last good summary
and the one-in-flight/high-watermark controller already accepted in T-31. Record prompt size,
attempt count, latency, every contract failure, and a human-readable before/after output for
each failing T-31 case.

Resolution accepts one exact prompt/validator default or rejects automatic summary as a
Phase-2 default. It leaves the broader function/UI/artifact decision to *Client-configured LLM
— functions, browser ownership, artifact access, and UI contract*.

## Resolution

**Adopt V15 for the final-summary function (operator, 2026-08-27).** This is a prompt and output
contract decision, not Phase-2 implementation.

- **D1 — Prompt:** use
  [`../../prototypes/client-configured-llm/final-summary-prompt.txt`](../../prototypes/client-configured-llm/final-summary-prompt.txt),
  the exact prompt recorded with V15. It prioritizes insight, mental models, reasoning,
  implications, and important quantitative anchors; data-reference coverage remains non-gating.
- **D2 — Invocation:** make exactly one summary call after an audio recording has one finalized
  authoritative transcript. Do not create rolling or interim summaries and do not make a repair
  call. An unusable response fails visibly rather than triggering another inference. For this
  function, this operator decision supersedes T-31's measured rolling-summary candidate.
- **D3 — Output contract:** accept one raw JSON object with exactly `summary`, `topics`, `details`,
  `speaker_background`, and `data_references`, with the item shapes stated in V15. Deterministic
  validation requires the five-key types, a non-empty summary, and in-range `HH:MM:SS` detail
  timestamps. Metric presence, count, omission, and digit-token coverage never determine pass or
  fail. A data reference is retained only when it supports a selected summary/topic takeaway.
- **D4 — Measured evidence:** V15 used `https://openrouter.ai/api/v1` with requested/resolved model
  `google/gemini-3.5-flash-lite`. On seven finalized visible non-holdout recordings it returned
  valid structure in 7/7, used data references in 5/7 summaries with 9 entries, and had 2.207 s
  median / 3.360 s maximum latency. Manual review found all nine values in their source
  transcripts and no recording/release logistics. The final five-version follow-up made 35 calls,
  with zero rolling, repair, or blind-holdout calls, at $0.0800817 recorded cost.
- **D5 — Boundary:** one Ackman reference has a correct value and explanatory relationship but
  names a non-final topic; the other 8/9 reference contexts map to final topics. The seven
  recordings were also the tuning set. Other models/endpoints, blind holdouts, meetings beyond 30
  minutes, non-English output, and broader semantic quality remain unmeasured. T-25 owns the
  product function, browser ownership, artifact, privacy, and UI decisions.

Full prompt-iteration evidence:
[`../../prototypes/client-configured-llm/final-summary-prompt-iterations.md`](../../prototypes/client-configured-llm/final-summary-prompt-iterations.md).

## Lifecycle amendment (2026-08-27)

[Client-configured LLM functions, browser ownership, artifacts, and UI](T-25-local-llm-scope-and-placement.md)
retains this ticket's single request shape and ban on output-repair calls, but permits an
identical request to be retried after delivery failure. This does not change this prototype's
one-call-per-recording evidence.
Unmodified V15 output:
[`../../prototypes/client-configured-llm/final-summary-iteration-15.md`](../../prototypes/client-configured-llm/final-summary-iteration-15.md).
