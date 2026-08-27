---
id: T-14
map: map-002-phase2-multiuser
title: LiveTranscribe LLM layer inventory — prompts, runtime, endpoints, UI, persistence
type: research
status: closed
assignee: charting-research-20260826
blocked_by: []
---

## Question

What does LiveTranscribe's local-LLM layer actually implement? The Phase-2 decision *Client-configured
LLM — functions, browser ownership, artifact access, and UI contract* must choose from the reference's real feature set, not its marketing
surface. The operator's requirement: determine what LiveTranscribe implements, then decide which
live formatting, summary, title, or other functions belong in MOSS.

Audit read-only over SSH (`ga0@m4mbp:~/Desktop/AI_Projects/LiveTranscribe`, branch
`ralph/production` @ `6a8d0c1`, dirty worktree — `git show HEAD:<path>` where local edits
overlap; never edit/clean/run). Surface, with file:line evidence:

- **Feature inventory** — every LLM-backed function (live reformat/polish, summary, title,
  anything else), and which are live-streaming vs post-hoc.
- **Exact prompts** — the full prompt templates per function, including system prompts and how
  transcript context is windowed into them.
- **Runtime** — which model(s)/runtime (llama.cpp, MLX, Ollama, remote API…), exact model ids,
  quantization, context sizes, and how the runtime is launched/managed.
- **Endpoints and contracts** — internal API routes/events between UI and LLM layer; request,
  cancellation, retry, and streaming semantics.
- **UI states** — how results render (overlay vs replace), pending/error states, user controls
  (the reference's `LlmSettingsModal` semantics).
- **Persistence** — which LLM artifacts persist (summaries, titles, reformatted text), where,
  and keyed how.
- **Resource behavior** — observable contention handling between LLM and ASR (scheduling,
  queueing, GPU/ANE assumptions).

Record findings in `.wayfinder/research/T-14-livetranscribe-llm-layer.md`: facts with paths,
verbatim prompts, exact model identifiers, and an explicit "unmeasured/unknown" list.

## Resolution

Resolved 2026-08-26 by a charting-session research subagent (read-only SSH audit of
`ralph/production` @ `6a8d0c1`; every dirty-file diff verified zero-LLM-content). Full findings
incl. verbatim prompts: [`../research/T-14-livetranscribe-llm-layer.md`](../research/T-14-livetranscribe-llm-layer.md).

Load-bearing facts for *Client-configured LLM — functions, browser ownership, artifact access, and UI contract* (T-25):

- **Feature inventory (6)**: (1) format cycle — live segment-polish overlay, every 30 s + final
  pass at stop, non-destructive over canonical ASR; (2) summary cycle — rolling structured
  summary (summary/topics/details/data_references/speaker_background), every 60 s + final +
  manual refresh; (3) auto title at live stop from the summary (never overwrites manual); (4)
  speaker-name enrichment mapping `SPEAKER_NN`→real names, post-hoc, **off by default**,
  display-name-only firewall (ADR-0021); (5) manual re-format with cursor; (6) tier-I LLM
  diarization reconciliation — engine exists, **disabled**, no production client.
- **There is no in-process LLM runtime.** The whole layer is an OpenAI-compatible HTTP client
  (`POST {endpoint}/chat/completions`); user runs LM Studio or anything compatible. Defaults:
  `http://127.0.0.1:1234/v1`, model `qwen3.6-35b-a3b`, temperature 0, timeout 240 s.
  Enrichment lane seeded (disabled) with `https://openrouter.ai/api/v1`,
  `google/gemini-3.1-flash-lite`; remote endpoints require an API key, loopback does not.
- **No quantization/context config anywhere** — app sends `{model, messages, temperature?,
  reasoning_effort?}`; context is the server's problem except the summary delta-switch.
- **"Local" in the reference means user-machine-local by policy** (ADR-0015 "local by default,
  cloud opt-in"), decoupled from the app process — directly reusable shape for MOSS's
  server-local vLLM question.
- Batch/file sessions get **no** format/summary cycles (only optional name enrichment at
  finalize); connection probe `GET {endpoint}/models` gates Save in the settings modal.

Unknowns (full list in findings): concurrent multi-client settings races (last-write-wins, no
locking); integration-test coverage; whether the deployed built bundle matches HEAD.
