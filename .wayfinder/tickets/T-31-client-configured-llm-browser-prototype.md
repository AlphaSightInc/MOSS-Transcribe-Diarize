---
id: T-31
map: map-002-phase2-multiuser
title: Client-configured LLM browser path and hybrid-summary policy
type: prototype
status: closed
assignee: codex-20260826
blocked_by: [T-14, T-19]
---

## Question

Does the proposed client-configured LLM design work through the supported Chrome path, and do
the reference-derived prompt plus hybrid full/delta policy earn their defaults before
*Client-configured LLM — functions, browser ownership, artifact access, and UI contract* closes?

Build a throwaway prototype under `prototypes/client-configured-llm/`; do not write Phase-2
product code. It must have one command, print full measured state, and leave `NOTES.md` with the
verdict. Exercise these already-grilled candidate decisions:

- The capture tab alone calls a user-supplied OpenAI-compatible
  `POST /v1/chat/completions`; endpoint, model, token, prompts, cadence, timeout, temperature,
  hybrid budget, and target language are browser-owned. No provider-specific adapter and no
  required `/v1/models` route.
- Prove the browser path in current supported Chrome: MOSS HTTPS origin/security state, Local
  Network Access permission where applicable, endpoint CORS, non-stream response parsing, and
  cancellation. Record exact Chrome version, origin, endpoint/model, commands, and outcomes;
  do not infer success from `curl`.
- Use a deterministic fake endpoint and injected clock to prove one in-flight call, transcript
  high-watermark coalescing, 60-second cadence, three JSON-repair attempts, exponential
  60/120/240/480-second backoff, Cancel preserving the last good summary, and no calls from
  history/view tabs.
- Measure the adapted LiveTranscribe summary prompt on every eligible non-holdout real
  transcript available in the standing corpus. Preserve exact denominators. Record prompt
  size, latency, schema-validity/repair count, full-to-delta transition, and factual defects;
  report absent corpus shapes or semantic quality as `unmeasured`, never extrapolated.
- Test the candidate hybrid rule: full authoritative transcript until the browser-owned
  12,000-estimated-token budget is crossed or the prior call exceeds 60 seconds; then previous
  summary plus new transcript, with context-limit rejection retried once and sticky delta for
  that Meeting. Compare against always-full and always-delta on the same measured inputs so the
  verdict can accept, revise, or reject the policy.
- The prototype may submit fake owner-scoped artifact lifecycle records, but must not depend on
  server-side endpoint settings or GPU inference. It must show the state projected through the
  existing `llm_status` and `llm_summary_update` vocabulary.

The resolution records a measured browser-feasibility verdict, exact prompt/policy verdict,
accepted defaults or replacements, and any remaining `unmeasured` limits. T-25 stays open until
this prototype closes.

## Resolution

Resolved with the operator on 2026-08-26. The operator accepted the recommended disposition:
accept the measured browser/controller seam and full-first/delta-fallback structure, reject the
unchanged reference summary prompt as a production default, and surface one focused follow-up
prototype before *Client-configured LLM — functions, browser ownership, artifact access, and UI
contract* closes.

Full evidence and the one-command reproduction live in
[`../../prototypes/client-configured-llm/NOTES.md`](../../prototypes/client-configured-llm/NOTES.md)
and
[`../../prototypes/client-configured-llm/latest-result.json`](../../prototypes/client-configured-llm/latest-result.json).

### Accepted browser and controller decisions

- The capture tab owns one deep rolling-summary module. Its interface accepts browser-owned
  configuration plus transcript commits and emits only `llm_status` and
  `llm_summary_update`. Browser HTTP and the deterministic fake are its two internal
  chat-completion adapters. History/view tabs consume owner-scoped Meeting artifacts and make
  no LLM calls.
- Use the user-supplied OpenAI-compatible `POST /v1/chat/completions` contract directly; no
  provider adapter and no required `/v1/models`. Keep endpoint, model, token, prompts,
  60-second cadence, 240-second timeout, temperature 0, hybrid budget, and target language in
  the capture browser.
- The state rule is one in-flight call with transcript high-watermark coalescing, at most three
  JSON attempts, 60/120/240/480-second failure backoff, Cancel preserving the last good
  summary, and no calls from non-capture tabs. All passed the injected-clock/fake-endpoint
  trace.
- Full authoritative transcript is the default. Delta is a bounded fallback when the complete
  request exceeds the browser budget, the previous call exceeds 60 seconds, or a context-limit
  rejection occurs. Context rejection retries delta once and makes delta sticky for that
  Meeting. Budget the **whole request**, not transcript text alone.

### Browser evidence and prerequisite

Google Chrome 151.0.7922.174 at the deployed MOSS origin completed authenticated CORS
preflight, parsed a non-stream response, and returned `AbortError` on cancellation. The Local
Network Access permission state remained `prompt`; loopback sent no private-network preflight
header, so non-loopback LAN endpoints remain unmeasured.

Strict navigation to the deployed origin failed `ERR_CERT_AUTHORITY_INVALID`. The prototype
proved the path only after a certificate bypass, where `isSecureContext=true`; trusted TLS or
an explicit attended trust step is therefore a prerequisite owned by the authentication/TLS
route, not silently solved here.

### Prompt and policy verdict

The frozen split names 16 non-holdout cases: 15 available references were measured, the pinned
5-minute Rolex reference was absent, and all 3 blind-holdout content files remained unopened.
The real `qwen/qwen3.6-35b-a3b` run made 34 HTTP requests including one repair.

- Full: 15/15 schema-valid, one repair, 38,871 estimated input tokens, 302.221 seconds
  aggregate terminal latency, digit-bearing omissions in 3/15, one unsupported digit-bearing
  value, and 3/15 violations of the prompt's own 25-word limit.
- Delta: 15/15 schema-valid, no repair, 33,076 tokens, 226.320 seconds, digit-bearing omissions
  in 6/15, one unsupported digit-bearing value, and 1/15 length violation.
- On 64 replayed 60-second calls, the 12,000-token hybrid behaved identically to always-full
  (187,639 estimated input tokens; zero cases entered delta); the largest measured full request
  was 10,183. The injected prior latency of 61 seconds did select delta. Thus the hybrid
  **shape** is accepted, while 12,000 is a configurable conservative ceiling, not a
  quality-optimized measured constant.

Full retained measured facts better, so always-delta is rejected. The unchanged summary
prompt is also rejected as a production default because its explicit quantity and length
requirements failed on reachable inputs. The newly surfaced *Revised summary prompt and
deterministic output contract* prototype owns that remaining decision.

### Explicitly unmeasured

The absent pinned Rolex case; non-loopback LAN and real bearer-token cloud endpoints; browsers
other than Chrome 151; meetings beyond 30 minutes; non-English output; contention beside 2–4
simultaneous speech sessions; and broader semantic factuality beyond the recorded schema,
timestamp, length, digit-bearing-fact, and speaker-background checks.
