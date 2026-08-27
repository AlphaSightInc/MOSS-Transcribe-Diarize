# Client-configured LLM browser prototype

**PROTOTYPE — throwaway measurement code, not Phase-2 product code.**

## Focused summary-contract follow-up

**Question:** Can one revised prompt satisfy the deterministic summary contract alone, or does
exact contract feedback earn the default within three attempts?

```bash
node prototypes/client-configured-llm/run-t33.mjs
```

This measures the prompt-only and exact-feedback arms against every available reference in the
same frozen non-holdout split. It leaves blind-holdout content unopened, prints full state, writes
`latest-t33-result.json`, and writes the prior failing cases as unmodified before/after model text
in `t33-before-after.md`.

Model-comparison runs may set `T33_RUN_LABEL`, `T33_LLM_ENDPOINT`, and `T33_LLM_MODEL`; the label
keeps their result and before/after files separate from the default run.

## Final-summary-only prompt iterations

This separate prototype makes exactly one final-summary call per de-duplicated finalized
recording: no rolling summaries, prompt/feedback arm, or repair call.

```bash
T33_PROMPT_ITERATION=15 \
T33_LLM_ENDPOINT=https://openrouter.ai/api/v1 \
T33_LLM_MODEL=google/gemini-3.5-flash-lite \
T33_LLM_TOKEN=... \
node prototypes/client-configured-llm/run-final-summary-iteration.mjs
```

The active candidate is `final-summary-prompt.txt`. Each run writes its complete unmodified state
to `final-summary-iteration-NN.json` and a readable review to
`final-summary-iteration-NN.md`. Data references are a selective quantitative-evidence appendix
and never affect acceptance.

## Question

Can the supported Chrome capture tab call a browser-owned OpenAI-compatible endpoint, and do
the proposed rolling-summary state machine, adapted prompt, and full/delta policy work well
enough to become Phase-2 defaults?

## One command

```bash
node prototypes/client-configured-llm/run.mjs
```

The command:

- uses installed Google Chrome against the deployed MOSS HTTPS origin;
- exercises CORS, Local Network Access state, non-stream parsing, and cancellation against a
  deterministic fake endpoint, plus one real LM Studio browser call;
- prints the complete injected-clock state-machine trace;
- reads only available development/validation references in the frozen 16-case non-holdout
  split, reporting any pinned file absence rather than substituting another reference;
- compares always-full, always-delta, and hybrid terminal summaries with the live local
  `qwen/qwen3.6-35b-a3b` model; and
- writes the same full result to `latest-result.json` for inspection.

Configuration is browser-owned in the prototype. Optional overrides are `T31_LLM_ENDPOINT`,
`T31_LLM_MODEL`, and `T31_LLM_TOKEN`; the token value is never printed. Default timeout is
240 seconds, cadence 60 seconds, temperature 0, target language English, and the hybrid budget
12,000 estimated input tokens (four characters per token).
