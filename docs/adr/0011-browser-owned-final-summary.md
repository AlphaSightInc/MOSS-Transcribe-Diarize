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

## 2026-09-11 — Configured key-less tailnet relay (user-approved amendment)

The initiating browser still owns the summary attempt, prompt, cancellation, validation,
and final-result persistence. External HTTPS providers keep the direct browser request,
credentials-omitted policy and existing delivery retries unchanged.

For explicitly configured key-less tailnet models, an authenticated same-origin relay
now forwards a transient completion request. This amends the original “no proxy” decision
only for the config-listed models: the browser cannot supply an upstream URL. The server
does not journal request/response content, retain prompts, synchronize browser settings,
or forward workspace cookies. Discovery is config-only, with no upstream model call.

Fresh browser settings default to the first relay model if discovery is nonempty;
saved external or explicitly disabled settings remain selected. The next listed model
is tried once only on a relay 502 `empty_content`, `upstream_error`, or
`upstream_unreachable`. It remains the same generating attempt; invalid summary JSON
does not trigger repair inference. Successful model identity appears in the worker
tab's status event, not in persistent summary provenance.

The browser's default relay timeout is 200 seconds, leaving delivery time beyond the
server's 180-second timeout. Configured provider URLs allow only the declared tailnet
domain, loopback, or 100.64.0.0/10. Redirects are not followed. No deployment, new model
quality, or host configuration is implied by the local tests.

Measured prototype and integration record:
`prototypes/client-configured-llm/relay-NOTES.md`. Operator configuration:
`docs/llm-relay.md`.

### 2026-09-11 thinking-model response boundary

The relay floors/defaults positive completion budgets to 2048 (cap 4096), sends
`chat_template_kwargs.enable_thinking=false`, and permits one retry only for a
reasoning-only response. Both attempts share the original 180-second deadline.
Both configured deployments accepted the option; RTX's exact summary request
previously exhausted 1024 tokens entirely on reasoning. Frontend summaries now
explicitly request 2048. Reasoning remains separate from answer content.

A distinct MacStudio failure produced valid outer answer content but an empty inner
summary. The default prompt now explicitly requires a grounded nonempty summary
for introduction-only transcripts. The accepted V15 bench prompt remains unchanged;
the parity test permits only this measured clarification. Saved browser prompts
remain untouched: choose **Restore default prompt**, then **Save on this browser**
to adopt the clarification after deployment. Existing user-customized prompts
retain their own output-quality risks. Evidence and limitations:
`docs/audits/relay-thinking-models-20260911.md`.
