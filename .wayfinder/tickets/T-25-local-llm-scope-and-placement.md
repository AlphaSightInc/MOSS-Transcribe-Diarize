---
id: T-25
map: map-002-phase2-multiuser
title: Client-configured LLM — functions, browser ownership, artifact access, and UI contract
type: grilling
status: closed
assignee: codex-20260827
blocked_by: [T-14, T-19, T-31, T-33]
---

## Question

Which LLM functions does multi-user MOSS adopt, and where does the model run?

Decide, with the operator, on the evidence of *LiveTranscribe LLM layer inventory* and the
identity model from *Identity and isolation architecture*:

- **Function selection** — from the reference's real inventory (live formatting, summary,
  title, other), which enter the MVP and which are ruled out; per-function live vs post-hoc.
- **What "local" means** — server-local (on `ga0-alienware-rtx4070ti`, sharing the RTX 4070 Ti
  with ASR) vs user-device-local (in-browser or user-machine runtime). The operator requirement
  names this decision explicitly. Note the repo already runs a vLLM service (`moss-vllm` —
  Phase-1 charter forbade mutating it remotely; T-14/T-18 establish what it serves today).
- **Contention with speech inference** — C4's 2–4 concurrent live sessions is the gate the LLM
  must not break: scheduling/queueing policy, VRAM budget, degradation order (LLM yields to
  ASR). If the paper budget is close, demand a named measurement (`/prototype`) before the
  decision closes.
- **Artifact access and privacy** — which user/session artifacts the LLM may read (transcript
  of the owner's session only — isolation applies to prompts too) and which artifacts it
  persists (summaries, titles), keyed to the owning account per T-19.
- **Prompt provenance** — adopt/adapt the reference's exact prompts vs rewrite; where prompts
  live (server config, versioned).
- **UI contract** — how results reach the Chrome client through the polling seam (Phase-1
  declared the reference's `llm_*` events unreachable — this ticket makes the needed subset
  reachable), pending/cancel states.

Resolution records the function list, runtime placement with model identity, the contention
policy with its measurement provenance, the artifact-access rule, and the event contract —
decision-complete for the AFK builder.

## Working decisions

- **D18 — Meeting scope:** Apply the final-summary contract to every owner Meeting after its
  authoritative transcript is finalized: Live, file, URL, and batch-created Meetings. The
  initiating browser queues multiple ready Meetings and calls the configured endpoint one at
  a time.
- **D19 — Failure recovery:** Retry failed final-summary calls automatically. This amends the
  one-call lifecycle adopted by T-33; D20 and D21 bound that amendment.
- **D20 — Retry boundary:** Retry only delivery failures: network errors, timeout, rate limit,
  and provider/server errors. Re-send the identical request. A completed but invalid or
  unusable model response fails visibly without an output-repair call.
- **D21 — Retry budget:** Make one initial call, then at most three identical delivery retries
  after 60, 120, and 240 seconds. After the fourth failed delivery attempt, publish a visible
  terminal failure. Never retry indefinitely.
- **D22 — Automatic title:** When the accepted output contains `topics[0].title`, use it as the
  automatic Meeting title only if no owner-written title exists. Otherwise retain the existing
  title. The T-33 corpus supplied this source in 6/7 accepted outputs; no separate title call.
- **D23 — Terminal recovery:** After delivery retries exhaust, cancellation, or invalid output,
  show the failure and an owner-only Retry action. Each click starts a fresh capped attempt group
  with the same request; it never constructs a repair prompt.

## Resolution

**Accepted — client-configured final summaries, with no MOSS-hosted model.**

- **D1 — MVP functions:** Generate one **Final summary** only after a Meeting has one finalized
  authoritative transcript. Apply the same contract to Live, file, URL, and batch-created
  Meetings. Exclude live formatting, rolling summaries, speaker-name enrichment, manual
  reformatting, and reconciliation. An **Automatic title** is a deterministic projection of the
  successful summary, not another model call: use `topics[0].title` only when present and no
  owner-written title exists; otherwise retain the existing title.
- **D2 — Runtime and model identity:** The LLM runs wherever the operator's browser-configured
  endpoint resolves: loopback, LAN, or remote. MOSS supplies no model runtime, server proxy, or
  provider adapter. The browser calls user-supplied OpenAI-compatible
  `POST /v1/chat/completions`, non-streaming, and reads `choices[0].message.content`.
  `/v1/models` is not required. The requested `model` string is provenance, not verified model
  identity. Chrome must be able to reach and trust the endpoint and its CORS policy.
- **D3 — Browser-owned settings:** Endpoint, model, bearer token, prompt, target language, and
  request timeout live only in that browser's local storage and Summary settings modal. Blank
  endpoint or model disables calls; Clear removes the local values. The fixed retry schedule is
  also browser-owned. The server never stores, synchronizes, or serves endpoint, token, or prompt.
  Before enablement, state plainly that the finalized transcript will be sent to the configured
  endpoint. The former 60-second refresh cadence and hybrid full/delta budget are retired because
  this function is final-only.
- **D4 — Prompt and output contract:** Default to the exact V15 prompt at
  [`../../prototypes/client-configured-llm/final-summary-prompt.txt`](../../prototypes/client-configured-llm/final-summary-prompt.txt),
  while allowing the browser owner to edit it. Require raw JSON with exactly `summary`, `topics`,
  `details`, `speaker_background`, and `data_references`; validate the five field types, nonempty
  summary, and in-range `HH:MM:SS` detail timestamps. Persist the validated JSON, artifact version,
  source-transcript version, requested model string, and prompt profile (`v15` or `custom`) through
  the account-scoped Meeting handle. Never persist the rendered prompt. Custom prompts and models
  beyond the measured one are explicitly unmeasured.
- **D5 — Worker, serialization, and retries:** The initiating browser is the automatic **LLM
  worker**; for batch completion it queues ready Meetings and runs one endpoint request at a time.
  The server admits at most one active summary attempt per Meeting. Stop, transcript durability,
  audio durability, and Meeting history never wait for the LLM. One attempt group is the initial
  request plus, only after network error, timeout, HTTP 408/429, or HTTP 5xx, identical retries at
  60, 120, and 240 seconds. Other HTTP failures and completed invalid output fail immediately.
  Cancellation aborts the request and scheduled retries. A visible owner-only Retry starts a fresh
  capped group; no automatic or manual path creates a repair prompt.
- **D6 — Artifact and privacy boundary:** Send only that owner Meeting's finalized transcript,
  the browser's prompt, and request parameters to the configured endpoint. Never send audio,
  Voiceprints, another Meeting, Account history, or Account identifiers. Store summary state and
  validated output only through an authorized account-scoped Meeting handle. Same-Account clients
  may read the persisted artifact; another Account cannot address it.
- **D7 — UI and polling contract:** Restore the existing Transcript | Summary presentation and a
  Summary-only settings modal; add no separate LLM panel. Persist shared states `queued`,
  `generating`, `retry_wait`, `current`, `failed`, and `cancelled`. Make only two existing polling
  event families reachable: `llm_status` carries state, attempt number, next retry time when any,
  source-transcript version, and coarse failure kind; `llm_summary_update` carries the validated
  artifact, artifact/source versions, requested model, prompt profile, and resulting automatic
  title when any. `llm_format_update` remains unreachable. View/history clients never call the LLM
  automatically; an explicit Retry makes that client the worker.
- **D8 — Contention and evidence:** LLM calls begin only after speech inference has produced the
  final transcript and execute outside MOSS's RTX 4070 Ti server, so they consume no server ASR
  VRAM or scheduling slot and cannot reduce C4's 2–4-session speech capacity by architecture.
  T-31 measured the Chrome/controller request, cancellation, serialization, and fake-endpoint
  state path. T-33 measured 7/7 structurally valid V15 outputs, 2.207 s median and 3.360 s maximum,
  on one configured model; its seven recordings were the tuning set. Non-loopback LAN/cloud bearer
  handling, other browsers/models/endpoints, blind holdouts, meetings beyond 30 minutes,
  non-English output, and broader semantic quality remain unmeasured.
