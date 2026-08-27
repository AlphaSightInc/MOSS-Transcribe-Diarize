# ADR-0011: The initiating browser owns Final-summary inference

- **Status:** Accepted
- **Date:** 2026-08-27
- **Scope:** Phase-2 Wave-3 language-model assistance

## Context

MOSS needs optional summaries without making the speech server own a model, provider credential,
prompt, scheduling load, or cross-Account content join.

## Decision

After one Meeting transcript is authoritative and final, the initiating browser may call its own
OpenAI-compatible `/v1/chat/completions` endpoint. Endpoint, model string, bearer token, prompt,
target language, timeout, and retry scheduling live only in that browser. MOSS provides no model,
proxy, provider adapter, or settings synchronization.

The request contains only that Meeting's finalized transcript, browser prompt, and request
parameters. It never contains audio, Voiceprints, Account history, another Meeting, or Account
identifiers. The default V15 prompt expects exactly five JSON fields: `summary`, `topics`, `details`,
`speaker_background`, and `data_references`; browser validation checks shape, nonempty summary, and
in-range detail timestamps. Validated output and provenance persist through an owner-bound Meeting
handle. Delivery failures alone receive identical retries after 60, 120, and 240 seconds; invalid
output gets no repair inference.

## Consequences

- Finalization, audio durability, and Meeting history never wait for the language model.
- View/history clients do not call automatically; explicit Retry makes that client the worker.
- Models, providers, languages, blind holdouts, and semantic quality beyond the measured V15 tuning
  set remain unmeasured rather than product promises.
