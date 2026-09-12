# Relay thinking-model diagnosis — 2026-09-11

Status: root causes reproduced; fix verified through both real upstreams and real Chromium. Final regression suite green. No host operations; initial local stack check returned HTTP 200.

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

## Live controlled replay (before implementation)

Private saved browser settings matched the prompt file exactly; language was blank. Session credentials were used transiently and are not retained here. Request/response/metrics artifacts: `evidence/relay-thinking-models-20260911/`. Requests project only start/end/speaker/text, with JavaScript-equivalent compact Unicode JSON for the user message. Each stage runs once per upstream; independent upstreams run concurrently, stages sequentially.

| Stage | MacStudio | RTX4090 |
|---|---|---|
| Running relay, caller omits tokens | 200; 191 completion tokens; nonempty summary; 2.78s | 502 empty_content; 20.08s |
| Direct, effective old request: 1024, stream=false | 200; 249 tokens; 0 reasoning chars; 3.43s | 200; **1024 tokens, finish=length, 5073 reasoning chars, 0 content chars**; 20.41s |
| Change only enable_thinking=false | 200; 242 tokens; 0 reasoning chars; 3.53s | 200; 258 tokens; **0 reasoning chars, 1090 content chars**; 11.76s |
| Then change budget to 2048 | 200; 157 tokens; 0 reasoning chars; **empty inner summary**; 2.44s | 200; 212 tokens; 0 reasoning chars; nonempty summary; 3.37s |

**Verdict:** H1 confirmed for RTX. Both deployed upstreams accept the option (HTTP 200); RTX's reasoning stops when only that option changes. MacStudio already had reasoning disabled, so acceptance is measured but a further reasoning reduction cannot be measured. H2 independently reproduced: increasing tokens cannot fix an empty inner summary generated with finish=stop. H3 rejection not observed. Sampling and cache state vary; timings are observations, not a latency benchmark.

## Implementation decision

Use the verified chat-template option on both attempts for the configured compatible upstreams; clamp valid positive budgets into 2048–4096, default 2048. No arbitrary new caller options or model-name heuristics. Retry exactly once only when answer content is blank/missing and nonblank reasoning exists. Retain one overall 180-second deadline. Answer plus reasoning returns unchanged; both empty fails immediately. Reasoning is never substituted for answer content.

Clarify the default prompt that the empty skeleton is not a completed answer and introduction-only transcripts still require a grounded nonempty summary. This fixes the separately reproduced prompt/validator mismatch without relaxing validation or inventing transcript facts. Existing user-saved prompts remain user-owned.

Regression seam: real authenticated route with fake upstream responses. Seven new response-shape cases were run before production changes: **7 failed**, including the reasoning-only recovery and token floor (`/tmp/moss-thinking-red.log`).

Evidence custody note: the original 2048 pair's raw files were accidentally overwritten by the prompt-fixed pair during the throwaway probe. Those new files are now named `prompt-fixed2048`; the earlier 2048 metrics above are from captured terminal output, not retained raw JSON. The relay, direct 1024, and option-only 1024 request/response pairs remain intact. The original E2E raw MacStudio empty-summary response is also retained, independently establishing H2.

Prompt-only treatment (same 2048 budget and disabled thinking) returned nonempty summaries from both: MacStudio 195 completion tokens / 3.99s, RTX 163 / 3.92s, both zero reasoning and finish=stop. One sample each; no claim of universal generation/schema reliability.

## Patched real-browser verification

Run: `PYTHONPATH=. .venv/bin/python prototypes/client-configured-llm/thinking_browser_probe.py --output /tmp/moss-thinking-browser-fixed`.

This launches the built production frontend and patched production relay in a disposable app/workspace, then uses real Chromium and both real configured upstreams. The operator's HTTPS stack is not restarted or modified. The original transcript is committed into scratch meeting state; no transcription is rerun. Each model is selected using the Browser AI UI; Restore default prompt and Save are clicked; Generate/Regenerate drives the real frontend request, validation, and durable summary API.

**PASS both models:** HTTP 200, explicit 2048 tokens, exact original projected transcript, current default prompt, validated persisted state `current`. MacStudio: 168 completion tokens; RTX: 315; both finish=stop and zero reasoning. Requests, raw relay responses, persisted artifacts, screenshots, and browser checks are retained in `evidence/relay-thinking-models-20260911/browser/`. Five checks per model, 10/10 passed. Chrome version and SQLite version are recorded in browser-results.json.

One preliminary browser run stopped on a probe-only KeyError: the accepted POST response exposes attempt_id directly, unlike the wrapped GET response. Its MacStudio request/response are retained in `browser-aborted/`; the probe was corrected before the complete run. No product workaround was needed.

The original row-9 failure is resolved on the patched app for this reproduction. This is not a claim that the still-running operator stack has been deployed, or that all generated summaries meet quality/schema requirements on all transcripts. Saved browser prompts are intentionally preserved: after deployment choose **Restore default prompt**, then **Save on this browser** to adopt this clarification.

## Regression validation

- Authenticated relay tests: 48 passed. Includes ordinary content, content with reasoning, reasoning-only followed by content, missing/null content with reasoning, two reasoning-only responses, completely empty response, lower/default/upper budget bounds, and cancellation of a hanging retry under one original deadline.
- Frontend: 195 passed; typecheck and production build passed. Both external and relay summary requests explicitly send 2048.
- Fake-upstream real browser: 7/7 passed, including two primary attempts then exactly one browser model fallback.
- External HTTPS/CORS real browser regression: 8/8 passed. No external delivery-policy change.
- First full Python run: 1362 passed, 1 failed, 2 optional corpus skips, 37 subtests passed. Sole failure was the old default-prompt parity assertion. Preserved the accepted V15 bench prompt and changed the assertion to permit exactly the measured clarification; full-suite rerun: **1363 passed, 2 optional corpus skips, 37 subtests passed, zero failures** in 83.94s. Validation counts and exact skip reasons are retained in `evidence/relay-thinking-models-20260911/validation.json`.

Prevention: test the full summary-sized prompt against thinking-model response envelopes, not only short connectivity prompts. Keep generation content separate from reasoning and keep the prompt's required field semantics consistent with the validator.

## Integration

Pre-push rebase incorporated `ee52440d` (optional draft-lane launcher argument and its tests). No relay/frontend conflicts. Post-rebase launcher/deployment plus relay regression: **61 passed** in 11.05s. The full-suite result above precedes this unrelated launcher commit; the affected integration paths were checked after rebase. Push target is private/auto-mvp-0911 only. No host operations performed.
