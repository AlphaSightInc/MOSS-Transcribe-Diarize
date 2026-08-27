# Final-summary prompt optimization

**PROTOTYPE — one final summary per finalized recording. No rolling summaries, repair calls,
or product implementation.**

## Iteration 1 — intent-first baseline

- Measured 7 finalized recordings in 7 calls: structure 7/7; raw JSON 2/7; median 2.957 s;
  maximum 4.579 s; recorded cost $0.017776.
- Useful: substantive mental models emerged for Ackman, Milei, Adam Frank, and the political
  philosophy comparison; metric appendices were selective rather than exhaustive.
- Defect: frequent meta-framing ("this episode/briefing explores"), plus unresolved previews
  promoted into conclusions in Jamie Dimon and Alphabet outputs.
- V2 change: require direct synthesis, distinguish established insight from question/preview,
  avoid unattributed evaluative language, and strengthen raw-JSON instruction.

## Iteration 2 — direct synthesis and raw JSON

- Structure 7/7; raw JSON 7/7; median 2.368 s; maximum 4.090 s; recorded cost $0.0155075.
- Fixed: meta-openings disappeared; Jamie Dimon remained an open question rather than a
  fabricated playbook; every response was raw JSON.
- Defect: summary/topic repetition remained high and many "why it matters" statements were
  generic rather than explanatory.
- V3 change: impose a synthesis -> mental model -> evidence hierarchy, require distinct topics,
  and explicitly handle setup-only finalized transcripts.

## Iteration 3 — hierarchical briefing

- Structure 7/7; raw JSON 7/7; median 2.565 s; maximum 3.638 s; recorded cost $0.0153527.
- Improved: less cross-field repetition and selective metric use in 3/7 recordings.
- Defect: pressure to produce "insight" manufactured significance, most clearly by turning the
  J.P. Morgan dueling-pistols anecdote into a lesson about institutional continuity.
- V4 change: require explicit or tightly entailed reasoning, attribute contestable claims,
  suppress anecdotes/logistics, and avoid invented consensus.

## Iteration 4 — evidence-bound insight

- Structure 7/7; raw JSON 7/7; median 2.358 s; maximum 3.487 s; recorded cost $0.0154675.
- Fixed: the Jamie output dropped the fabricated historical-continuity lesson and accurately
  labeled the transcript as framing a future investigation.
- Defect: epistemic inflation remained—possible future constraints became an answer to alien
  existence, while Alphabet's preview became a settled strategic conclusion.
- V5 change: preserve observation/argument/forecast/question/preview status and modal certainty.

## Iteration 5 — epistemic-status instruction

- Structure 6/7; raw JSON framing 7/7; median 2.355 s; maximum 4.079 s; recorded cost
  $0.0162031.
- Improved: Adam Frank's output now said future data can set limits rather than promising an
  answer to alien existence; Alphabet was framed more cautiously.
- Defect: Javier Milei output omitted quotes around three JSON property names. Instruction
  accumulation also allowed some meta-framing to return.
- V6 change: replace the accumulated prompt with a shorter, priority-ordered version and an
  explicit valid-JSON preflight.

## Iteration 6 — compact priority-ordered prompt

- Structure 7/7; raw JSON 7/7; median 2.349 s; maximum 4.295 s; recorded cost $0.0155578.
- Fixed: valid structure recovered; outputs retained strong explanatory chains for Ackman and
  Adam Frank.
- Defect: adjacent sections were fused into causality (Milei policy/results), inferred agreement
  remained in the political comparison, and low-value event/anecdote details survived.
- V7 change: separate narrator/guest/outcome evidence, apply a counterfactual centrality test,
  prohibit inferred consensus, and compress the summary to 1-2 sentences.

## Iteration 7 — source separation and centrality

- Structure 6/7; raw JSON framing 7/7; median 2.428 s; maximum 4.192 s; recorded cost
  $0.0155469.
- Improved: Jamie and Alphabet became concise, appropriately bounded briefings.
- Defect: one malformed NFL object; inferred agreement persisted in the political comparison;
  Milei sections were still causally fused; Adam Frank's possible future constraints again
  became a promise to answer whether aliens exist.
- V8 change: use a silent evidence-map/ranking workflow and explicit output patterns for speaker
  arguments, comparisons, forecasts, and setup-only transcripts.

## Iteration 8 — evidence-map workflow

- Structure 7/7; raw JSON 7/7; median 2.353 s; maximum 3.770 s; recorded cost $0.0157751.
- Improved: clear attribution and reasoning chains; source audit confirmed that Adam Frank's
  "capacity to answer" and Ben/Destiny's shared opportunity premise were explicitly supported.
- Defect: short setup transcripts still elevated opening banter, announcements, and event
  logistics because novelty/line count was mistaken for importance.
- V9 change: define importance as explanatory leverage, not novelty or frequency; permit empty
  details/metrics when a setup-only transcript contains no substantive evidence.

## Iteration 9 — explanatory-leverage filter

- Structure 7/7; raw JSON 7/7; median 2.559 s; maximum 4.110 s; recorded cost $0.0160034.
- Improved: Jamie's summary became a precise one-sentence statement of the unanswered question;
  the main summaries consistently prioritized central mechanisms over logistics.
- Defect: orphan appendix items survived even though they did not support selected takeaways—the
  dueling pistols in Jamie details and a casual beef-patty price in Ackman metrics.
- V10 change: require every detail/metric to support a chosen summary/topic, delete orphan facts,
  and add a final grammar/relevance preflight.

## Iteration 10 — cross-field relevance candidate

- Structure 7/7; bare JSON without fences 7/7; median 2.632 s; maximum 2.998 s; recorded cost
  $0.0158484; optional metric appendix used in 3/7 recordings.
- V1 -> V10 objective change: bare JSON without fences 2/7 -> 7/7; median latency 2.957 s ->
  2.632 s; maximum 4.579 s -> 2.998 s. Metrics were never acceptance criteria.
- Manual evidence review: clear summary-level improvement in 5/7 recordings (Jamie Dimon,
  Bill Ackman, Javier Milei, Adam Frank, Alphabet); mixed in NFL and Shapiro/Destiny.
- Residual: NFL details still retain event logistics; Jamie details still retain the dueling-pistol
  anecdote despite the summary correctly centering the unanswered leadership question.
- Verdict: material improvement, but **breakthrough quality is not certified**. There are no gold
  human summaries, the seven recordings were also the tuning set, and operator semantic review
  remains required.

## Iterations 1-10 totals

- 7 finalized recordings x 10 versions = **70 calls**; **0 rolling-summary calls**, **0 repair
  calls**, and **0 blind-holdout content files opened**.
- Endpoint `https://openrouter.ai/api/v1`; requested/resolved model
  `google/gemini-3.5-flash-lite`; total recorded cost **$0.1590384**.
- Final candidate prompt: `prototypes/client-configured-llm/final-summary-prompt.txt`.
- Full final outputs: `prototypes/client-configured-llm/final-summary-iteration-10.json` and
  `prototypes/client-configured-llm/final-summary-iteration-10.md`.

## Data-reference follow-up — iterations 11-15

**Question:** Can positive selection increase relevant `data_references` above the V10 baseline
of 3/7 summaries and 4 entries while retaining 7/7 valid five-key JSON in the final candidate?
Metrics remain non-gating.

| Version | Valid structure | Summaries with references | Entries | Median | Maximum | Cost |
|---|---:|---:|---:|---:|---:|---:|
| V11 | 7/7 | 3/7 | 3 | 2.262 s | 4.528 s | $0.0154110 |
| V12 | 7/7 | 3/7 | 5 | 2.560 s | 4.217 s | $0.0171903 |
| V13 | 6/7 | 4/7 | 6 | 2.561 s | 3.584 s | $0.0164823 |
| V14 | 7/7 | 4/7 | 5 | 2.111 s | 3.979 s | $0.0155069 |
| V15 | 7/7 | 5/7 | 9 | 2.207 s | 3.360 s | $0.0154912 |

- **V11:** added a positive pass over selected takeaways; coverage did not move.
- **V12:** mirrored selected quantitative evidence; entry count rose, but an orphan fiscal metric
  showed that general recording relevance was still too permissive.
- **V13:** defined years and time horizons as data references and restored Adam Frank's evidence,
  but Alphabet copied a prompt placeholder into malformed JSON.
- **V14:** replaced the risky populated shape with a valid empty JSON skeleton and explicit item
  shapes; 7/7 structure recovered, but a low-value NFL release date entered and Adam's time
  evidence disappeared.
- **V15:** treated time as evidence only when it changes the mental model, excluded recording and
  release logistics, and required exact topic mapping. Final coverage reached 5/7 and 9 entries.

Manual V15 audit found all nine quantitative values in the source transcripts. The appendices
retain NFL's >3x popularity comparison, Ackman's 15x Alphabet valuation, Milei's three-part
historical trajectory, Adam Frank's three time/rarity anchors, and Alphabet's 2004 IPO milestone.
Jamie Dimon and Shapiro/Destiny correctly remain empty. No recording/release logistics survived.

One residual remains: Ackman's metric context names a non-final topic (`Alphabet's Valuation and
AI Positioning`) instead of the final topic `Market Overreaction to Technological Shifts`, although
the value and explanatory relationship are source-supported. The other 8/9 contexts map to final
topic titles. The deterministic digit diagnostic flags NFL `3x` and Adam Frank `1` because their
sources spell the quantities as words; manual source review confirmed both.

Follow-up total: **35 calls**, **0 rolling summaries**, **0 repair calls**, **0 blind-holdout files
opened**, and **$0.0800817** recorded cost. Verdict: V15 materially improves data-reference
coverage over V10 without a final-candidate JSON regression, but remains tuning-set evidence, not
semantic certification.

The operator selected V15 and closed T-33 on 2026-08-27. The closure adopts one call after the
finalized transcript, with no rolling/interim summary or repair call; no product code was written.
