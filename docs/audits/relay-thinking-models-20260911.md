# Relay thinking-model diagnosis — 2026-09-11

Status: investigation in progress. No host operations; local stack responds HTTP 200.

## Contract

- **Question:** does the summary request spend its completion budget on reasoning, or produce an invalid summary despite a usable answer envelope?
- **Primitives:** immutable prompt/transcript request; upstream answer versus reasoning; completion budget; bounded retry. Each controls a distinct observable failure boundary.
- **Invariants:** authenticated configured-model routing; no reasoning promoted to the answer; at most one reasoning-only retry; one overall 180-second deadline; frontend validates the final document.
- **Unknowns:** whether each deployed upstream accepts and honors `chat_template_kwargs.enable_thinking=false`; whether 2048 tokens suffices for this recorded transcript. Not a general model-quality qualification.
- **Falsifier:** identical input still produces empty content with thinking disabled and a larger budget, or an upstream rejects/ignores the option.
- **Tools:** replay exact requests to distinguish relay behavior from generation; raw JSON exposes content/reasoning/finish reason/usage; fake upstream tests establish retry bounds and response handling deterministically.

## Retained reproduction and hypotheses

Input: `evidence/e2e-feature-verification-20260911/meeting-4XEDDwdaowqbw63xwSsE3s95.json`, three segments ending at 17.64 seconds, projected exactly as `providerBody`; system prompt is `frontend/src/lib/final-summary-prompt.txt`, language blank. Frontend omits max_tokens; existing relay sends 1024 and stream=false.

- **H1:** RTX exhausts the budget thinking. Prediction: raw upstream reasoning with empty content and length finish; disabling thinking restores answer content.
- **H2:** short introduction plus the prompt's empty skeleton produces an empty summary field. Retained MacStudio response `relay-response-1789170282-1.json` has 509 characters of answer content, 142 completion tokens, zero reasoning tokens, finish=stop, but parsed summary is empty. This is distinct from H1.
- **H3:** a deployed upstream rejects or ignores the thinking-disable option. Prediction: HTTP rejection or reasoning remains after changing only that option.

Live measurements and implementation verdict will be appended below before completion.
