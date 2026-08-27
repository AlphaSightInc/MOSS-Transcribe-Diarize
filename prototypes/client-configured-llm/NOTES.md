# Client-configured LLM browser prototype — accepted measured verdict

**PROTOTYPE — not Phase-2 product code. Accepted by the operator and recorded in T-31 on
2026-08-26.**

## Question

Does the supported Chrome capture tab work as the owner of an OpenAI-compatible LLM client,
and do the proposed prompt and hybrid full/delta policy earn Phase-2 defaults?

## One command

```bash
node prototypes/client-configured-llm/run.mjs
```

Full measured state: `prototypes/client-configured-llm/latest-result.json`.

## Accepted verdict

**Browser path: feasible after TLS trust is resolved. State controller: accept. Hybrid shape:
accept with the whole request as the budget input, but the exact 12,000-token switch remains
unmeasured. Current summary prompt: reject as the production default and run one focused
prompt/output-contract follow-up before T-25 closes.**

### Browser proof

- Google Chrome **151.0.7922.174**, deployed origin
  `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861`, endpoint contract
  `POST /v1/chat/completions`, model measurement `qwen/qwen3.6-35b-a3b`, no token.
- Strict navigation failed `ERR_CERT_AUTHORITY_INVALID`. With the prototype-only certificate
  bypass, the deployed page reported `isSecureContext=true`.
- The HTTPS page completed an authenticated CORS preflight and parsed a non-stream fake
  completion (`200`, response type `cors`). Chrome rejected cancellation with `AbortError` in
  **1 ms**. Local Network Access permission remained `prompt`; Chrome sent no private-network
  preflight header for loopback. Non-loopback LAN behavior is unmeasured.
- No `/v1/models` route is required by the prototype contract.

### Controller proof

The injected-clock/fake-endpoint trace passed every requested behavior:

- one call at the 60-second due time; one in flight; pending transcript coalesced to the latest
  sequence;
- JSON became valid on attempt **3/3**;
- failure backoff was exactly **60/120/240/480 seconds**;
- Cancel preserved the last good summary;
- history and view roles made **0** calls;
- a full-context rejection retried delta exactly once and made delta sticky for the Meeting;
- externally visible events were only `llm_status` and `llm_summary_update`.

The deep module seam is the capture-tab-owned rolling-summary controller. Its small interface
accepts transcript commits/configuration and emits the two event types. Browser HTTP and the
deterministic fake are the two adapters behind an internal chat-completion port. History/view
tabs consume owner-scoped Meeting artifacts and never instantiate the controller.

### Corpus and policy proof

- Frozen split: **16** non-holdout cases (8 development, 8 validation); **15 available and
  measured**, **1 unavailable** because the pinned
  `5m-acquired-rolex/reference-v2-human-20260804.jsonl` file is absent. All **3** blind
  holdout content files remained unopened.
- Real model: **34 HTTP requests including one repair**. The 15 cases yielded 45 policy views;
  six 60-second cases share one first summary, while nine longer cases used a prefix seed plus
  independent full and delta terminal calls.
- 60-second replay over the 15 available transcripts: always-full and hybrid both made
  **64 calls / 187,639 estimated input tokens / 0 cases entering delta**. Always-delta made
  **64 calls / 91,696 tokens / 9 cases entering delta**. The injected 61-second prior call
  selected delta, so the latency branch works; the real corpus never crossed the 12,000-token
  budget (maximum full request **10,183** estimated tokens).
- Terminal full: **15/15 schema-valid**, **1 repair**, **38,871 estimated input tokens**,
  **302.221 s** aggregate latency. Terminal delta: **15/15 schema-valid**, **0 repairs**,
  **33,076 tokens**, **226.320 s** latency.
- Full retained digit-bearing facts better: missing facts in **3/15** cases versus **6/15** for
  delta. Both produced an unsupported digit-bearing value in **1/15**. Full violated its own
  25-word summary limit in **3/15** cases; delta in **1/15**. Topic-count and
  speaker-background-name checks passed 15/15.

These numbers support full as the authoritative default and delta as a bounded fallback. They
do **not** support adopting the current prompt unchanged: its explicit quantity and length
requirements failed on measured inputs.

## Remaining unmeasured

- The absent pinned 5-minute Rolex transcript.
- Non-loopback LAN endpoints, real bearer-token cloud endpoints, and browsers other than
  Chrome 151.
- Meetings longer than 30 minutes, languages other than English, and contention beside 2–4
  concurrent automatic speech recognition sessions.
- Broader semantic factuality beyond schema, timestamps, summary length, digit-bearing facts,
  and speaker-background names.

## Recorded map action

T-31 closed with the verdict above. The unassigned *Revised summary prompt and deterministic
output contract* prototype (T-33) now owns the prompt replacement, and T-25 waits on it. Do not
turn this prototype into product code.

---

## Revised summary prompt and deterministic output contract — measured candidate

**Operator verdict pending.** Full state:
`prototypes/client-configured-llm/latest-t33-result.json`. Unmodified human-readable outputs for
all five cases that failed the prior prompt:
`prototypes/client-configured-llm/t33-before-after.md`.

One command:

```bash
node prototypes/client-configured-llm/run-t33.mjs
```

### Measured result

- Frozen non-holdout split: **15/16 available and measured in both arms**; the pinned 5-minute
  Rolex reference remained absent; **0/3 blind-holdout content files opened**.
- Revised prompt alone: **11/15** passed the deterministic contract; **16 attempts**; median
  **20.422 s**, maximum/p95 **143.710 s**, aggregate **470.005 s**.
- Same prompt with exact contract feedback: **15/15** passed within three attempts; **20
  attempts**, with feedback needed in **4/15** cases; median **23.340 s**, maximum/p95 **187.466
  s**, aggregate **569.527 s**.
- Feedback corrected missing quantities in three first outputs, one invalid/unsupported
  timestamp/quantity output, and one malformed JSON plus a second quantity defect. No model text
  was truncated and no facts were synthesized after inference.
- The existing controller proof passed: one in flight, high-watermark coalescing, prior good
  summary retained through repair, and the next call targeting the coalesced transcript.

### Candidate disposition

**Recommend the exact revised prompt plus deterministic contract feedback**, conditional on the
operator accepting the unmodified before/after semantics and a measured **187.466 s** worst-case
30-minute repair latency. Prompt-only is rejected at **11/15**. If that latency or the examples
are unacceptable, reject automatic summary as the Phase-2 default; do not add a third design.

Broader semantic factuality, the absent pinned Rolex case, non-English output, meetings beyond
30 minutes, and contention beside 2–4 simultaneous speech-recognition sessions remain
**unmeasured**.

### RTX4090 `qwen38-27b-mtp` comparison

The operator proposed the more capable `qwen38-27b-mtp`. Live verification on 2026-08-26 found
the exact model at `http://ga0-rtx4090:1235/v1`; `/v1/models` and a real completion both echoed
that model ID.

The direct browser route is **not usable unchanged**: Chrome at the deployed HTTPS MOSS origin
returned `TypeError: Failed to fetch` for the remote HTTP URL. A temporary loopback tunnel
`127.0.0.1:1237 -> ga0-rtx4090:1235` succeeded with HTTP 200, CORS response type `cors`, echoed
model `qwen38-27b-mtp`, and content `{"ok":true}`. The temporary tunnel was removed after proof.

Full result:
`prototypes/client-configured-llm/latest-t33-qwen38-27b-mtp-result.json`. Unmodified comparison:
`prototypes/client-configured-llm/t33-qwen38-27b-mtp-before-after.md`.

- Same frozen denominator: **15/16 available**, both arms measured, **0/3 holdouts opened**.
- Prompt alone: **13/15 terminal pass**, median **101.318 s**, maximum/p95 **240.003 s**,
  aggregate **1,816.768 s**.
- Contract-feedback arm: **13/15 terminal pass**, median **116.670 s**, maximum/p95 **240.002
  s**, aggregate **1,836.603 s**.
- Every returned output passed the contract on its first attempt: **13/13**. The missing two were
  not quality failures; the 5-minute Jamie Dimon and 30-minute Bill Ackman cases each exceeded
  the 240-second per-attempt timeout in both arms, producing no summary.

**Disposition: do not replace the automatic default with this configuration unchanged.** It is
cleaner on completed outputs but requires a browser-local bridge and times out on two reachable
cases. Keep the Qwen3.6 revised-prompt-plus-feedback candidate unless the operator explicitly
authorizes a new measured model-specific policy such as disabling reasoning or increasing the
timeout; either changes the evaluated contract and requires another run.

### OpenRouter `google/gemini-3.5-flash-lite` comparison

The operator supplied OpenRouter access and requested the exact model
`google/gemini-3.5-flash-lite`. Live verification on 2026-08-26 found that exact ID in
OpenRouter's model inventory at `https://openrouter.ai/api/v1`. An authenticated smoke
completion echoed the exact model, reported provider `Google`, and returned the requested
content. The token was used only in process memory and was not recorded.

The endpoint is structurally browser-compatible from the deployed HTTPS application: an
unauthenticated CORS preflight to `/chat/completions` returned HTTP 204,
`access-control-allow-origin: *`, allowed `POST`, and allowed `Authorization`. The full live
benchmark used the same HTTPS API directly; a real authenticated call from Chrome remains
unmeasured.

Full result:
`prototypes/client-configured-llm/latest-t33-openrouter-gemini-3.5-flash-lite-result.json`.
Unmodified comparison:
`prototypes/client-configured-llm/t33-openrouter-gemini-3.5-flash-lite-before-after.md`.

- Same frozen denominator: **15/16 available**, both arms measured, **0/3 holdouts opened**.
- Prompt alone: **10/15 terminal pass**, median **2.430 s**, maximum/p95 **4.205 s**,
  aggregate **39.554 s**.
- Contract-feedback arm: **15/15 terminal pass** within three attempts, **21 attempts** total,
  feedback used in **5/15** cases, median **2.340 s**, maximum/p95 **13.521 s**, aggregate
  **53.166 s**.
- No transport failures or timeouts. The contract-feedback arm repaired all missing or
  unsupported quantities, topic-count, and malformed-output failures. The 30-minute Bill Ackman
  case completed in both arms.
- The authenticated 20-token smoke call reported cost **$0.0000236**. Full-benchmark cost is
  **unmeasured** because this runner records model text and latency, not provider usage metadata.

**Disposition: this is the strongest measured automatic-summary candidate if sending transcript
text to OpenRouter/Google is acceptable.** It is not better at following the prompt unaided
(10/15 versus Qwen3.6's 11/15), but exact feedback reaches 15/15 with roughly one-tenth the
median latency and no long-case timeout. Broader semantic factuality remains unmeasured and the
This comparison alone did not close T-33; the operator later selected V15 after the
final-summary-only prompt iterations.

### Final-summary-only prompt optimization — iterations 1-10

After the operator rejected rolling/interim summaries as the measurement unit, the prototype was
re-scoped to exactly one final-summary call per de-duplicated finalized recording. Seven visible
non-holdout recordings were used per version; interim prefixes were excluded; the unavailable
5-minute Rolex final was not replaced; blind-holdout content remained unopened.

Ten sequential prompt versions made **70 total calls**, with **0 rolling-summary calls** and **0
repair calls**. All used `https://openrouter.ai/api/v1` and
`google/gemini-3.5-flash-lite`. Total provider-recorded cost was **$0.1590384**.

The final candidate explicitly states the insight/mental-model goal, embeds the five-key JSON
shape, treats metrics as an optional final appendix, preserves epistemic status, separates source
roles, ranks facts by explanatory leverage, and asks every detail/metric to support a selected
takeaway. Metric inclusion, omission, and coverage never affect pass/fail.

- V1: structure **7/7**, bare JSON without fences **2/7**, median **2.957 s**, maximum **4.579 s**.
- V10: structure/bare JSON without fences **7/7**, median **2.632 s**, maximum **2.998 s**; optional metrics
  used in **3/7**.
- Manual evidence review found clear summary-level improvement in **5/7** recordings and mixed
  results in NFL and Shapiro/Destiny.
- Residual defects remain: NFL details retain event logistics; Jamie Dimon details retain the
  dueling-pistol anecdote even though its summary correctly states the unanswered leadership
  question.

**Disposition: material improvement, not certified breakthrough quality.** No gold human
summaries exist, the same seven recordings were the tuning set, and operator semantic review is
still required. Final prompt: `final-summary-prompt.txt`; full outputs:
`final-summary-iteration-10.json` and `final-summary-iteration-10.md`; iteration evidence:
`final-summary-prompt-iterations.md`. At this V10 checkpoint T-33 remained open and no Phase-2
product code was written.

### Data-reference follow-up — iterations 11-15

The follow-up asked whether a prompt-only positive-selection pass could raise useful
`data_references` above V10's **3/7 summaries and 4 entries** while returning to **7/7 valid
five-key JSON** in the final version. The same seven finalized non-holdout recordings were each
called once per version: **35 calls**, **0 rolling summaries**, **0 repair calls**, and **0 blind
holdout files opened**. OpenRouter recorded **$0.0800817** total cost.

- V11: valid structure **7/7**; references **3/7 summaries, 3 entries**.
- V12: valid structure **7/7**; references **3/7 summaries, 5 entries**.
- V13: valid structure **6/7**; references **4/7 summaries, 6 entries**. Alphabet copied a prompt
  placeholder into malformed JSON.
- V14: valid structure **7/7**; references **4/7 summaries, 5 entries**. A valid empty skeleton
  removed the placeholder failure.
- V15: valid structure **7/7**; references **5/7 summaries, 9 entries**; median **2.207 s**,
  maximum **3.360 s**, cost **$0.0154912**.

Manual V15 review found all nine values in the transcript and no recording/release logistics.
Jamie Dimon and Shapiro/Destiny correctly remained empty. One residual mapping defect remains:
Ackman's source-supported 15x valuation entry names a non-final topic in its context; 8/9 entries
name an actual final topic. Digit-only diagnostics falsely flag NFL's `3x` and Adam Frank's `1`
because the source spells those quantities as words.

**Disposition: V15 is the stronger measured prompt candidate.** Relative to V10, final
data-reference coverage improved **3/7 -> 5/7** and entry count **4 -> 9**, while final valid JSON
remained **7/7**. This is tuning-set evidence, not semantic certification; metrics remain
non-gating. The operator selected V15 and closed T-33 on 2026-08-27; no Phase-2 product code was
written. Full output:
`final-summary-iteration-15.json` and `final-summary-iteration-15.md`; complete history:
`final-summary-prompt-iterations.md`.
