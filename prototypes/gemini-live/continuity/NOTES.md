# P61 continuity prototype

## Contract before code

**Structural question.** A Gemini batch window numbers speakers only inside that call. Can overlapping observations identify the same person across windows, including after a long silence, while keeping committed rows stable enough for the live view?

**Minimum primitives.** (1) A window-local speaker label groups words within one call. (2) A meeting ID persists across calls. (3) Timed words provide shared evidence in overlapping windows. (4) A registry holds the mapping and committed rows. None can be removed: without local groups there is nothing to map; without meeting IDs no continuity; without shared evidence assignments are arbitrary; without a registry assignments cannot persist. An optional acoustic embedding from a continuous Gemini-attributed span of at least 2 s is independent evidence when words do not overlap or Gemini splits one voice locally.

**Invariants.** An ID means one hypothesized person for the whole meeting; IDs never recycle. In the main C3 arm, two local labels in one window share an ID only when their qualifying voice vectors match and their timed words do not overlap. The separate overlap-reuse arm tests a weaker rule and was rejected. Audio available to a window ends at simulated time `t`. A committed word is first shown only after its end is behind `t-H`; later relabels are counted separately. The terminal whole-recording pass is excluded from settled scoring.

**Assumptions and unknowns.** Gemini word timestamps and local labels may drift at window edges, and one physical voice may receive multiple local labels inside one call. Word overlap may fail after a long silence. Acoustic embeddings do not exist for many short Gemini labels under the L1 span rule. Real-time-paced label latency and full meeting billing are unmeasured. A no-timed-reference E1 count is not DER evidence.

**Hypothesis.** One-to-one overlap assignment with a small amount of persistent acoustic evidence can avoid speaker splits at rolling seams; extra complexity earns a place only if it improves the primary six-case settled diarization error rate (DER) without violating speaker count, latency, or cost bars.

**Falsifier.** No evaluated policy beats MOSS's ruled settled DER 0.145 on the six acceptance clips, or the best accuracy policy exceeds E1/synthetic speaker count true+1, 20 s p50 label lag, or $3/meeting-hour. Long-silence reappearance causing a birth also falsifies overlap-only continuity for that case.

**Tool decisions.** Use public `common.corpus` so the input population is fixed; `common.gemini_common.diarize_window` so calls use the actual model, cache, and P61 ledger; `harness/h1_offline.py` for every MOSS-relative H1 verdict. Use `common.score` for supporting corpora under the lead's exclusion rule. Compare fixed S/L/H schedules by replaying cached windows: differences then isolate mapping policy. Use the production ONNX embedder because overlap produced reappearance failures; its added acoustic evidence must earn its cost. L1 permits this as a Gemini-speaker linking input, not as a replacement diarizer; the pure-Gemini arm always appears beside it. Embed only continuous Gemini-attributed spans of 2–10 s, at most three per local label. Record every call count, audio duration, usage cost, and transcript availability. `measure.py` runs the prototype and stores each window mapping and aggregate state in receipts.

From the worktree root, one command runs the measured registry on accept6 and prints each window plus both mapping states (cached Gemini calls are reused):

```sh
PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/continuity/measure.py --tier accept6 --step 10 --length 30 --holds 0 --thresholds 0.3 --embedding-thresholds 0.46 --within-thresholds 0.60
```

## Results

Selection population: accept6 primary; gold9 excluding `benchmark:acquired_jamie_dimon` (only 12.3/60 s timed), the three complete `benchmark_5m:lex_*` references (300 s each), and complete `benchmark_30m:lex_bill_ackman` (1800 s) are supporting checks. The five acquired 5-minute references cover only 35.1–91.3/300 s, and 30-minute `acquired_jamie_dimon` only 374.4/1800 s. Their DER, miss, and WER are diagnostic only. Gold9 NFL (52.9/60 s), Rolex (51.1/60 s), and Shapiro/Destiny (152.5/181 s) have small or moderate untimed gaps that may inflate miss.

Scoring rule: accept6/MOSS comparisons use the H1-exact offline scorer. Supporting gold8, lex, long30m, and synthetic DER/WER use `common.score` (with the validated polynomial assignment equivalent when labels are numerous). For real references, rows with empty text or speaker `<EXCLUDE>` define excluded intervals: remove those reference rows and subtract those intervals from hypothesis **word** spans before grouping/scoring. NFL's song interval is 20.56–37.54 s. Synthetic truth has intentionally empty text and remains valid for DER; synthetic WER is unmeasured. Zero-duration hypothesis words have no scored interval and are omitted from support scoring.

L1-compliant embeddings use only continuous Gemini-attributed spans of at least 2 s. Earlier C3 receipts without `span2s` are superseded.

All accept6 DER figures below use the manifest-matching **H1 #3 reference set** selected by `common/corpus.py` at `a9634449`. Earlier checkout-current reference figures were superseded (preserved in P61 evidence with `-pre-H1-reference` suffix); ID counts, calls, costs, and anomalies were unchanged.

| Method | S / L / H (s) | accept6 first-commit settled DER macro, H1 exact | Last-revised settled DER macro, H1 exact | Displayed IDs total | Modeled batch cost per meeting-hour |
|---|---:|---:|---:|---:|---:|
| C1 overlap, pure Gemini | 10 / 30 / 0 | 0.154136 | 0.159063 | 20 | $0.488 |
| C1 + C3 cross/within-window, E=.46 / W=.60 | 10 / 30 / 0 | 0.102910 | 0.111448 | 17 | $0.488 |

Shorter holds on the **same** 62 calls and H1 #3 truth; first settled DER is the decision metric, last revised shows what later rolling evidence repairs:

| S / L / H (s) | Pure Gemini first DER | Fingerprint first DER | Fingerprint last revised DER | Fingerprint visible relabel-pairs |
|---|---:|---:|---:|---:|
| 10 / 30 / 0 | 0.154136 | **0.102910** | 0.111448 | 15 |
| 10 / 30 / 1 | 0.161446 | 0.110220 | 0.121385 | 11 |
| 10 / 30 / 2 | 0.172722 | 0.121843 | 0.133007 | 11 |
| 10 / 30 / 3 | 0.186802 | 0.138385 | 0.146804 | 10 |
| 10 / 30 / 5 | 0.211269 | 0.168326 | 0.169129 | — |

Accept6 is the same 62 cached Gemini calls in every row. C3 adds local CPU ONNX embeddings, not Gemini call cost. The H1-exact offline scorer at `3d5f61cb` evaluates the strict Stop frontier `t-H`. At H0, the best measured first settled DER is .102910 C3+local versus .154136 pure, on the verified H1 #3 reference set; MOSS H1 #3 raw settled DER is .171344 and ruled DER is .144626 after its S00 discount. Gemini has no S00 segments, so its ruled and raw DER coincide. The retained H1 #3 macro metrics, same six cases and first-committed surface:

| H1 metric | Pure Gemini C1 | C1+C3 WeSpeaker |
|---|---:|---:|
| Ruled / raw settled DER, lower better | .154136 | .102910 |
| Reference-speech DER, lower better | .140738 | .090596 |
| Immediate WER, lower better | .114139 | .114139 |
| Settled WER, lower better | .114139 | .114139 |
| Content recall, higher better | .956955 | .956955 |
| Time speaker attribution, higher better | .899781 | .920746 |
| Matched speaker accuracy, higher better | .865381 | .915991 |

Immediate equals settled at H0; terminal final is unmeasured. H0 C3 has 17 displayed IDs across accept6, 18 births, 2 local merges, 15 visible relabel-pair events (1.45/min), schedule-only label lag p50 4.85 s/p90 8.85 s; adding recorded offline API response gives p50 7.91 s/p90 11.73 s. **Real-time-paced lag remains unmeasured.** Earlier `.110645` C3 and `.161872` pure DER values at H5 committed the preview tail and are **superseded**.

E1 has no timed reference, so its gate is displayed speaker count. On the **same 10/30/0 schedule** as the accept6 H0 candidate, the system lane displays 7 IDs for 3 true voices under C3+local (pure C1: 10), exceeding true+1=4. H1–H3 still show 7, H5 shows 6. The microphone mix displays 8 IDs for 4 true (pure 11), exceeding true+1=5. The older 20/120/5 run shows 4/3 on system and 4/4 mixed, but that different schedule does not qualify the 10/30/0 candidate. Mixed call 29 had a severe offset failure: 4,483 words started beyond its 30 s audio window and were dropped by the shared parser; 14 more were clamped. That call returned 109 valid-window words, took 71.618 s, and reported only `spk:?`. **No winner qualified.**

The synthetic count failure is not confined to high speaker count. Corrected 10/30/0 first settled `common.score` results on all eight registered 600 s meetings:

| Synthetic meeting | True speakers | Pure Gemini DER / IDs | C3+local DER / IDs |
|---|---:|---:|---:|
| K2 seed 0 | 2 | .905428 / 101 | .573878 / 62 |
| K2 seed 1 | 2 | .696258 / 44 | .409236 / 27 |
| K3 seed 0 | 3 | .830223 / 47 | .327533 / 24 |
| K3 seed 1 | 3 | .869797 / 75 | .484490 / 45 |
| K4 seed 0 | 4 | .820740 / 80 | .371679 / 41 |
| K4 seed 1 | 4 | .855416 / 72 | .513739 / 36 |
| K6 seed 0 | 6 | .871603 / 96 | .441882 / 43 |
| K6 seed 1 | 6 | .823173 / 81 | .348844 / 41 |

Eight-case DER macro: .834080 pure versus .433910 C3+local first committed; .832076 versus .434869 last revised. Displayed IDs total 596 pure versus 319 C3+local, for 30 true speaker instances across meetings. Every C3 case exceeds true+1, including both K2 cases and both K6 long-silence reappearance cases. The available shared corpus contains K=2,3,4,6 seeds; no K=5 fixture is registered. Earlier H5 synthetic DER values used the incorrect final-window frontier and are superseded. Synthetic text is empty in truth, so WER is unmeasured. Batch audio cost is approximately $0.54/meeting-hour on this schedule; full Live/Stop cost is unmeasured.

Gold9: 91 calls; 4 clamped, 0 dropped offsets in 7,391 returned words. One 60 s clip, `benchmark:acquired_jamie_dimon`, has only 12.3 s of annotated speech and is excluded from selection. At H0, the lead-selected **gold8** first settled DER macro under the rule above is .183383 pure versus .124172 C3+local; last revised .173527 versus .117868. NFL's intentional `<EXCLUDE>` song interval is masked, yielding C3 first DER .075766 for that clip. These are secondary evidence, not the accept6 MOSS qualification gate. Earlier unmasked gold and incorrect-frontier values are superseded.

The three complete lex 5-minute references, each 300/300 s, use 90 calls at 10/30/0. `common.score` first settled DER macro is .104445 pure versus .034111 C3+local; last revised .093000 versus .029111. Displayed IDs total 15 versus 7 for 6 true across clips. One word offset was clamped in 6,942 returned words; the affected call is in the table below. Earlier H5 values used the incorrect final-window frontier and are superseded.

The complete lex Bill Ackman 30-minute reference covers 1800/1800 s. On 180 calls at 10/30/0, `common.score` first settled DER is .745834 pure versus .119529 C3+local; last revised .751277 versus .131526. Displayed IDs are 24 versus 7 for 2 true. Thus the fingerprint method still fails long-form speaker count. Modeled batch cost is $0.538/meeting-hour. Two Gemini words in the last-revised surface have zero duration (`Mhm.` at 736.8 s, `Yeah.` at 1298.2 s); support scoring omits them before grouping and retains them in the raw receipt. Three offset clamps occurred in 17,381 returned words, with exact per-call rates below. Immediate and terminal final remain unmeasured for this case.

Gemini offset parser anomalies per call (rate = clamped+dropped divided by returned+ dropped words):

| Tier / call | Returned words | Clamped | Dropped | Rate |
|---|---:|---:|---:|---:|
| accept6 Adam Frank window 4 | 73 | 1 | 0 | 1.3699% |
| accept6 Adam Frank window 12 | 93 | 1 | 0 | 1.0753% |
| gold9 Adam Frank window 4 (same cached call) | 73 | 1 | 0 | 1.3699% |
| gold9 Adam Frank window 12 (same cached call) | 93 | 1 | 0 | 1.0753% |
| gold9 Shapiro/Destiny window 1 | 20 | 1 | 0 | 5.0000% |
| gold9 Shapiro/Destiny window 8 | 113 | 1 | 0 | 0.8850% |
| lex5m Bill Ackman window 29 | 128 | 1 | 0 | 0.7812% |
| lex30m Bill Ackman window 29 (same cached call as lex5m) | 128 | 1 | 0 | 0.7812% |
| lex30m Bill Ackman window 163 | 100 | 1 | 0 | 1.0000% |
| lex30m Bill Ackman window 176 | 104 | 1 | 0 | 0.9615% |
| E1 mic mix window 27 | 91 | 1 | 0 | 1.0989% |
| E1 mic mix window 29 | 109 | 14 | 4,483 | 97.9312% |
| synth K3 seed 1 window 16 | 67 | 0 | 1 | 1.4706% |
| synth K3 seed 1 window 55 | 72 | 1 | 1 | 2.7397% |
| synth K4 seed 0 window 13 | 83 | 1 | 1 | 2.3810% |
| synth K4 seed 0 window 25 | 87 | 1 | 0 | 1.1494% |
| synth K6 seed 0 window 35 | 77 | 0 | 1 | 1.2821% |
| All other accept6 calls (60), gold9 calls (87), lex5m calls (89), lex30m calls (177), E1 system calls (31), E1 mic calls (29), and synth calls (483) | — | 0 | 0 | 0% each |

Every call, including zero-anomaly calls, appears in `evidence/P61/accept6-H1-reuse-run.jsonl`, `gold9-L30-span2s-run.jsonl`, `bench5m-lex3-L30-span2s-run.jsonl`, `long30m-lex-L30-span2s-run.jsonl`, `synth-all-L30-span2s-run.jsonl`, and the E1 system/mix `L30-hold-sweep-run.jsonl` files with its rate. Real-time-paced label latency and full meeting cost including Live and Stop are unmeasured. At H0, simulated schedule-only accept6 first-commit label latency p50 is 4.85 s; adding recorded offline API response gives 7.91 s. These do not establish the live latency gate.

### Next falsifier: overlap can be many-to-one

**Question.** When Gemini splits one physical speaker into two labels inside a window, can both labels independently overlap the same already known meeting ID? **Primitive.** A local label's timed word overlap with prior committed observation is evidence for an ID; two current local labels may share that ID only when their current word times do not overlap. **Hypothesis.** Permitting a second overlap-supported label to reuse an assigned ID reduces K=6 births without worsening accept6 DER. **Falsifier.** K=6 count still exceeds truth+1, or accept6 macro rises, or incompatible overlapping local speech is collapsed. **Tool.** Sweep the same cached calls with a many-to-one mapping switch and report pure-Gemini and C3 results side by side. This is a prototype policy, not a product change.

**Measured verdict.** On K=6, C3+local+reuse reduced first-view IDs 45→37 but still failed the ≤7 gate; DER .444027→.440111. On accept6 H1 truth it worsened first DER .110645→.112521. The short-label problem persists: among 47 IDs mapped anywhere in the K=6 reuse trace, 33 never received an L1-eligible voice vector. Lowering a fingerprint threshold cannot resolve IDs with no vector. A retrospective merge or split repair that lacks independent evidence would invent speaker identity, so no such repair is claimed as qualified.

Those numeric repair DER values used the old final-window frontier and are superseded for Stop-surface accuracy; the birth/ID mechanism and 33 vectorless-ID finding remain diagnostic. `SpeakerRegistry.observe_window` returns an empty retrospective `relabels` list: it does not rewrite past meeting IDs. `measure.py` separately counts visible relabel-pair events when a later rolling window changes already committed rows inside its overlap. At accept6 H0 C3 this happened 15 times over 620 s (1.45/min); it is rolling revision, not proven global identity repair. A global ID merge would need evidence for the vectorless fragments that these tests did not find.

**L1 threshold sweep.** With S10/L30/H0 fixed, 15 combinations of cross-window cosine `E=.30/.40/.46/.60/.70` and within-window cosine `W=.46/.60/.70` were replayed on the same six accept6 calls plus K2/K6 and E1 system/mix controls. At `W=.60`, accept6 first raw DER macro is .102910 for E=.30/.40/.46/.60 (the E=.46 point is independently H1-exact scored above). Across the whole grid, E1 counts remain 7/3 system and 8/4 mixed, K2 seed 0 has at least 60 IDs/2 true, and K6 seed 0 at least 42/6. Lowering the voice threshold cannot meet the count gate; no extra API calls were made for the sweep. Per-case data: `evidence/P61/threshold-sweep-S10-L30-H0-L1.json`.

**C4 growing-context cost boundary.** For a 30-minute meeting, 10 s step, a window growing from meeting start to cap `Lmax` then sliding has the following modeled batch-audio cost at $0.00005/audio-s. This is arithmetic, not DER evidence or a full meeting bill:

| `Lmax` (s) | Sent audio (s) | Modeled batch $/meeting-hour |
|---:|---:|---:|
| 30 | 5,370 | 0.537 |
| 60 | 10,650 | 1.065 |
| 90 | 15,840 | 1.584 |
| 120 | 20,940 | 2.094 |
| 150 | 25,950 | 2.595 |
| 180 | 30,870 | 3.087 |

`Lmax` 180 s crosses the $3 batch-only soft bar; ≤150 s requires a measured settled DER/count benefit before adding cost. Growing-context end-to-end DER is unmeasured. Longer whole-clip calls are known from the P53 public synthetic probe to shatter labels; that is a concern, not a C4 measurement.

**C2 anchor feasibility.** Pane 5.3's 30 public exemplar trials found same-speaker label agreement in 53/73 speaker trials (72.6%); every exemplar bound correctly in only 17/30 windows. Paired gold9 and synthetic window DER worsened. A wrong exemplar label would bind a persistent meeting ID to the wrong local voice, so C2 was not promoted to P61 end-to-end registry calls. C2 settled-surface DER/count remain **unmeasured**; this is a measured primitive rejection, not a direct end-to-end score.

## Verdict

**No measured policy qualifies as the continuity winner.** The best first-committed settled policy is C1 overlap plus C3 production WeSpeaker voice fingerprints, including within-window merging of Gemini local labels, at S10/L30/H0 and cosine E=.46/W=.60. It beats the MOSS H1 #3 ruled accept6 DER (.102910 versus .144626), but fails the count gate on both E1 lanes and every registered synthetic meeting. The best **pure-Gemini** policy is C1 overlap at the same schedule; it has no voiceprint dependency and has accept6 DER .154136. Same-corpus first settled DER, with lower better:

| Corpus / score | Pure Gemini C1 | C1+C3 WeSpeaker | Qualification role |
|---|---:|---:|---|
| accept6, H1 exact, six-case macro | .154136 | **.102910** | Primary MOSS comparator; H1 #3 truth |
| gold8, common.score, eight-case macro | .183383 | .124172 | Supporting; sparse Jamie excluded |
| complete lex5m, common.score, three-case macro | .104445 | .034111 | Supporting, 300 s references |
| complete lex30m Bill, common.score | .745834 | .119529 | Supporting, 1800 s reference; C3 count 7/2 fails |
| synth K2/K3/K4/K6, common.score, eight-case macro | .834080 | .433910 | Count gate; all eight C3 counts fail |

The fingerprint dependency is material: the pure-Gemini comparator loses .051226 accept6 DER, while C3 still fragments IDs. C3 uses WeSpeaker only to link Gemini-attributed spans of at least 2 s; Gemini supplies every within-window word and its speaker label. Neither a terminal final surface nor live-paced latency was measured here. The modeled batch cost of this schedule is below $0.54/meeting-hour on measured corpora, but that omits Live and Stop calls; the real cost gate remains unverified. The registry prototype is retained for reproducible measurement, with no production integration recommended from this evidence.

## C4 follow-up contract (phase 1)

**Stop correction applied.** `c4_stop.py` scores a separate H-specific Stop call over exactly `[current commit frontier, audio end]`. Earlier `c4.py` full-Lmax Stop scores are retained as superseded receipts and excluded from every verdict below; their periodic Gemini calls and vectors are reused.

**Structural question.** Can longer Gemini windows preserve enough of its own speaker clustering that overlap mapping stops birthing extra meeting IDs, while a Stop window drains held-back words and the live view remains timely and affordable?

**Minimum primitives.** A growing window ending at simulated time `t`; its word-local labels; the same meeting-ID registry; a live commit frontier `t-H`; a final Stop observation that advances the frontier to the audio end; and a pending local label that has less than 2 s of Gemini-attributed speech. The Stop observation is distinct from live progress: it repairs final coverage but cannot make a live label appear earlier. C3 vectors remain optional linking evidence, computed only from continuous Gemini-attributed spans ≥2 s.

**Invariants.** No observation uses audio beyond its simulated end. Before Stop, only words behind `t-H` are settled; at Stop, all remaining words from the final window are committed before close. The screen immediately before Stop uses the preceding scheduled observation. A pending label does not allocate a new meeting ID; a short label may follow existing timed overlap, otherwise its words display as `S00` and its unattributed duration is counted. The pure-C1 and C1+C3 policies consume identical Gemini calls, H1 #3 truth, and surfaces. Historical phase-0 receipts are not overwritten.

**Assumptions and unknowns.** The final Stop window may complete before the product stop deadline; that deadline is not measured by this offline replay. Batch response time is recorded, but real-time-paced live latency remains unmeasured. The Live words stream adds list $0.30/meeting-hour and no additional settled speaker labels in this simulation. Gemini may still shatter labels inside a long window, as prior synthetic whole-clip calls showed.

**Hypothesis and falsifier.** Increasing `Lmax` and requiring 2 s of local speech before a birth will reduce E1 and complete lex30m displayed IDs to ≤true+1 without losing the accept6 settled DER advantage. Falsified if no candidate has both count gates, H1 accept6 settled DER below .145, recorded schedule+API label lag p50 ≤20 s, and modeled batch+Live cost ≤$3/hour. Supporting gold8/lex5m/synth scores can expose regressions but do not replace those gates under L2.

Lead added `long60` at `581ce7e6`: a 2586 s public Lex concatenation with five named voices, 97 reference rows spanning the full 2586 s and 2580.4 s of timed speech. It joins the long-form identity stress checks; its count and DER will be reported independently because L2's formal real-long gate named lex30m. Separate sessions change Lex's recording conditions, so this tests durable identity as well as seam continuity.

**Tool and spend decision.** Extend only this measurement prototype: replay the fixed S/L/H matrix with `diarize_window`, `h1_offline` for accept6, `common.score` with the real EXCLUDE mask for support, and production WeSpeaker vectors for C3. The four lengths × three steps × two holds reuse each Gemini call across H and mapping policies. An all-corpus, all-schedule matrix would require over $50 in batch audio input alone, exceeding the follow-up's $8 *new uncached* cap. Measure accept6 and E1 schedules first, then spend the remainder on lex30m and supporting checks for candidates that could pass the gates; mark every unrun cell **unmeasured**. This order changes a decision because E1 can reject a schedule before long-form calls.

On a 30-minute meeting, audio-input arithmetic alone rules out L180/S10 (~$3.087/h batch + $.30/h Live) and L300/S10 or S15 (~$4.96/h or ~$3.32/h batch + $.30/h Live): all exceed the $3/h winner bar before any output tokens. Those three cells are **cost-rejected by arithmetic**, not DER measurements. The other nine schedules remain measurement candidates within the $8 follow-up spend cap.

### Stop-drain correction on cached 10/30 windows

The final Stop observation covers `[last periodic end − H, audio end]` and commits its remaining words. The immediate surface is captured from the preceding scheduled observation. H1-exact accept6 first-committed settled DER below uses all six H1 #3 references; label lag is the median of the six per-case p50 values with recorded offline API response time, excluding words first committed by Stop. Periodic calls are shared across holds and policies; Stop calls differ by H.

| H (s) | Pure C1 DER | Pure + 2 s birth DER | C3 DER | C3 + 2 s birth DER | C3 + birth displayed IDs total | C3 + birth `S00` seconds | Label lag p50 (s) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | .265664 | .261113 | .107139 | .102587 | 14 | 4.5 | 7.871 |
| 5 | .175662 | .173427 | .103393 | **.101158** | 13 | 2.7 | 12.841 |
| 10 | .185096 | .184798 | .120554 | .112528 | 13 | 1.8 | 18.118 |
| 20 | .157866 | .157661 | .119903 | .108452 | 13 | 1.8 | 27.892 |

The Stop drain fixes missing tail coverage; the larger holds still change which rolling observation first owns earlier words. H20 fails the 20 s label-lag bar. H5 has the lowest timely C3+birth DER on this 30 s schedule. At H0, immediate WER is .215181 versus settled WER .115620 because the Stop call is absent from the pre-Stop screen; provisional Live words are outside this P61 simulation. The 2 s birth rule reduces splits but makes 4.5 s of accept6 speech unattributed at H0.

The corrected E1 10/30 short-Stop replay gives C3+birth first IDs system/mix 3/3 at H0, 3/3 at H5, 4/3 at H10, and 4/3 at H20; pure+birth gives 7/7, 7/7, 8/7, and 8/7. The mixed C3 undercount against four true voices may be a merge. H20 recorded lag is about 28 s. Old full-Lmax Stop counts remain excluded.

### Growing-context E1, S20 (H0)

All four lengths completed on the same public E1 system and fixture-gain mic-mix. These are count diagnostics only: E1 has no timed reference. Cost is measured batch token usage plus the list $0.30/h Live words stream; lag is schedule plus recorded offline API response, not a real-time-paced run.

| Lmax (s) | Pure C1+birth IDs system / mix | C3+birth IDs system / mix | C3+birth `S00` s system / mix | Label lag p50 s system / mix | Batch+Live $/h |
|---:|---:|---:|---:|---:|---:|
| 60 | 7 / 7 | 3 / 4 | 4.0 / 4.1 | 13.603 / 14.001 | .802 |
| 120 | 6 / 6 | 3 / 3 | 4.0 / 2.7 | 15.915 / 16.124 | 1.196 |
| 180 | 5 / 6 | 3 / 3 | 3.1 / 5.1 | 17.381 / 17.247 | 1.482 |
| 300 | 4 / 6 | 3 / 3 | 2.9 / 3.4 | 18.307 / 18.456 | 1.732 |

The C3+birth first-committed count is within the L2 E1 gate at every S20 length, but pure C1+birth exceeds the mixed ≤5 gate. Last-revised C3 IDs for L120 mixed fall to **2 for 4 true voices**, indicating a likely merge; without a timed E1 reference the actual attribution error remains unknown. H10 has recorded lag p50 24–29 s at S20 and misses the 20 s soft bar. The H0 Stop call is only 2 s long on E1 and raises `S00` first-committed speech to 2.7–5.1 s. No parser offset anomaly occurred in these E1 calls.

### Growing-context accept6, S20

All six H1 #3 clips were scored against the same references; values are H1-exact first-committed settled DER macros. The first column is the best pure-Gemini C1 method under the 2 s birth rule, shown beside the fingerprint method. H0 is the timely arm; H10 is displayed to expose the accuracy/latency trade-off.

| Lmax (s) | Pure+birth H0 DER | C3+birth H0 DER | C3+birth H10 DER | C3+birth IDs total | C3+birth `S00` s H0 | H0 / H10 lag p50 s |
|---:|---:|---:|---:|---:|---:|---:|
| 60 | .298850 | .108363 | .089791 | 14 | 2.4 | 13.648 / 21.778 |
| 120 | .298812 | .108326 | .089846 | 14 | 2.4 | 14.237 / 22.313 |
| 180 | .298756 | **.108270** | .089790 | 14 | 2.4 | 14.237 / 22.313 |
| 300 | .298756 | **.108270** | .089790 | 14 | 2.4 | 14.237 / 22.313 |

The longest accept6 clip is 180 s, so L180 and L300 use identical periodic calls and numeric voice vectors on this tier. The H0 Stop call is short and largely determines the extra pure-C1 IDs; larger periodic context barely changes settled DER. H10 misses the 20 s recorded schedule+API lag bar at every length. H0 C3+birth immediate WER is about .267 versus settled WER about .109: the pre-Stop screen lacks the Stop drain and no Live words stream is modeled here. One Adam Frank L180 periodic window clamped 1/486 returned words (0.206%); its receipt gives the per-call rate. All other S20 accept6 calls had zero parser anomalies.

### Complete 30-minute Bill Ackman, S20/L60

This reference covers 1800/1800 s. On 89 periodic Gemini windows plus the exact H0 Stop call `[1780,1800]`, C3+2 s birth reaches **3 first/last-revised IDs for 2 true voices**, meeting the L2 real-long count gate. The best pure-Gemini C1+birth comparator displays **16 first / 15 last IDs**, failing count. `common.score` first/last DER is **.402022/.400855 C3** versus **.532993/.530604 pure**. The C3 `S00` cost is .5 s first and 0 s last. Recorded schedule+API label lag p50 is 14.463 s; measured batch tokens plus $0.30/h Live words cost is $.830/meeting-hour. The Stop call itself took 3.446 s offline. Three offsets were clamped in periodic calls, zero dropped; individual rates are in `c4-observations-long30m-benchmark_30m_lex_bill_ackman-S20-L60.jsonl` and `c4-stop-observation-*`.

The count gate alone hides a large real-meeting accuracy loss: pane 5.3's single whole-clip Gemini call on this complete reference scored DER .0615 with 3 labels, while C4 L60 rolling settles at .4021. That is a same-reference diagnostic with a different surface/call policy, not a paired rolling registry sweep. The longer C4 measurements and winner verdict follow below.

The failure is a concrete over-split, not a coverage loss: in the shared periodic observations M1 overlaps 444.2 s of Bill Ackman's reference speech, while M3 overlaps another 583.2 s of Bill. M2 overlaps 280.2 s of Lex Fridman. M3 is born at rolling window 36 (ending 720 s), when Gemini's two local labels map to M1 and a new M3. The exact-Stop scorer attributes nearly all of its .402022 DER to speaker confusion; the short final drain does not repair the 720 s split. A true+1 count gate permits this split, so the long-form DER must remain visible beside count.

At S20/L120, the same complete 1800 s reference improves: C3+birth **2 first/last IDs for 2 true**, first/last DER **.231615/.257332**; pure C1+birth **9/9 IDs**, DER **.358365/.366419**. C3 has 0 s `S00`, recorded schedule+API p50 lag 17.501 s, and measured batch+Live cost $1.340/h. The exact H0 Stop interval is [1780,1800] s. H10 C3 first DER .230560 but lag 27.812 s. Two periodic offsets clamped and one dropped; all per-call rates are in the numeric observation receipt. At S20/L180, C3 first/last DER is .229227/.251666 with 2/2 IDs, but its 20.662 s lag p50 exceeds the bar. L120 and L180 remain far above the one-call .0615 diagnostic.

### C4 continuation: support and 43-minute identity stress

The exact-short-Stop L120/S20 H0 support check uses the same Gemini calls for both registries. On the three complete 300 s Lex references, `common.score` first-committed DER is **.034333 C3+birth** versus **.184333 pure C1+birth**; C3 shows 2 IDs per clip, while pure shows 4/4/5. On gold8 (sparse benchmark Jamie excluded), DER is **.162935 C3+birth** versus **.383677 pure**, shared WER .131241. The Shapiro/Destiny calibration remains a concrete C3 failure at DER .616393 (speaker confusion .435410). Acquired NFL and Rolex have small untimed gaps. For real `<EXCLUDE>` or empty-text reference rows, the rows are dropped and hypothesis *words* are clipped out of those intervals before grouping and scoring; the NFL EXCLUDE is [20.56,37.54] s. Gold8 is supporting evidence, not H1 qualification.

The new `long60` complete-reference clip spans 2586 s with five named voices. At L120/S20 H0, C3+birth displays **6 first / 5 last IDs** and scores **.300806 first DER**; pure C1+birth displays **17/16 IDs** and scores **.333243 DER**. C3 schedule+recorded API p50 lag is 17.298 s, batch+Live cost $1.357/h, and the exact Stop call covers [2580,2586] s. The C3 count is within five true plus one, but identity is badly wrong: M1 overlaps 785.9 s of Bill Ackman and 317.7 s of Lex Fridman; M2 overlaps 299.8 s of Lex and 247.2 s of Bill. The registry also births M4 for 4.3 s of Lex speech. Three of 130 calls have parser offset anomalies (3 clamped, 1 dropped); the worst individual call's anomaly rate is .5435%, with each rate retained in `c4-observations-long60-long60-S20-L120.jsonl`. This stress result prevents treating a passing count as accurate identity.

### C4 schedule gates and H1-exact finalist

The nine cost-feasible schedules have paired pure/C3 accept6 and E1 scores in `c4-qualification-matrix.json`; the other three S/L cells were cost-rejected above. This table uses **H0, first-committed** values. DER is H1-exact six-case macro on H1 #3 references, E1 is first displayed system/mix IDs (true 3/4), and Bill is complete-reference 1800 s `common.score`. Long-form lag includes the recorded API response and excludes Stop-only words. Pure is C1 overlap with the same 2 s birth rule and no fingerprints.

| S/Lmax s | C3 / pure accept6 DER | E1 C3 IDs | Bill C3 IDs / DER | Bill lag p50 s | Bill batch+Live $/h | Gate/result |
|---|---:|---:|---:|---:|---:|---|
| 10/60 | .098624 / .237427 | 4/5 | 3 / .139413 | 9.684 | 1.361 | Passes written gates; real DER still material |
| 15/60 | .095640 / .263548 | 5/3 | unmeasured | — | — | E1 system count fails |
| 15/120 | .101110 / .255340 | 3/3 | 3 / .510387 | 15.018 | 1.688 | Count passes but real identity fails |
| **15/180** | **.098518 / .253951** | **3/4** | **2 / .056321** | **17.845** | **2.345** | **Best accept6 DER among full measured gate passers** |
| 20/60 | .108363 / .298850 | 3/4 | 3 / .402022 | 14.463 | .830 | Count passes but real identity fails |
| 20/120 | .108326 / .298812 | 3/3 | 2 / .231615 | 17.501 | 1.340 | Count passes but real DER poor |
| 20/180 | .108270 / .298756 | 3/3 | 2 / .229227 | 20.662 | 1.832 | Long-form lag misses 20 s bar |

S10/L120 scored .131414 accept6 C3 DER and was dominated before its long-form vector scoring; its 179 numeric periodic calls remain retained. S20/L300 has the same accept6 DER as L180 because these clips end by 180 s; no long-form call was justified before L180's lag miss. All H10 S20 arms reached about .0898 accept6 C3 DER but case-median recorded lag exceeded 20 s. The best *pure-Gemini* arm across the nine cells under that lag bar is S10/L60/H10 at .155236 accept6 DER and 18.874 s case-median lag; its E1 counts are 7/7 and fail both count gates. The paired pure H0 score beside every C3 score exposes the fingerprint dependency on identical calls and corpora.

For S15/L180/H0, all **eight H1 QUALITY_BOUNDS macros** use `h1_offline.score_case` on the six H1 #3 references; the final WER comes from the same six cached whole-clip Gemini calls for both policies (`c4-wholeclip-final-accept6.json`). The rolling immediate surface is pre-Stop committed words plus the last scheduled preview; it does not include provisional Live words. The score receipts' empty-final placeholder is superseded for this table by `c4-qualification-matrix.json`.

| H1 macro | Pure C1+birth | C1+C3+birth |
|---|---:|---:|
| Immediate WER | .238027 | .238027 |
| Settled WER | .114063 | .114063 |
| Content recall | .953971 | .953971 |
| Time-based speaker attribution | .861071 | .922006 |
| D45b ruled DER | .253951 | **.098518** |
| Matched speaker accuracy | .780641 | .920091 |
| Reference-speech DER | .238744 | .084406 |
| Final whole-clip WER | .104123 | .104123 |

The same H1 settled cases have **raw DER .264181 pure / .108748 C3** before D45b's `S00` confusion adjustment, versus the ruled values in the table. Raw reference-speech DER is .248317 / .093979. The ruled and raw views are both retained so 2 s pending births do not appear as unexplained diarization gains.

S15/L180/H0 complete lex5m macro DER is .032444 C3 versus .162000 pure (2 IDs per clip C3); gold8 macro DER is .133518 versus .331744. The same-call WERs are .121671 and .132466 respectively. S10/L60/H0 support gives lex5m .035889 versus .157111 and gold8 .111597 versus .285913. The 10/60 complete Bill clip scores .139413 C3 versus .528383 pure, with 3/15 first IDs. The 15/180 Bill result is much better despite slightly slower lag and higher cost. The six accept6 C3 cases at S15/L180 range from DER .020 (Javier mono) to .283553 (RTFL); the macro hides that RTFL remains difficult.

### Diagnostic identity stress and parser timing

The full eight chapter-spliced synthetic meetings at S20/L120/H0 score **.303951 C3+birth DER** versus **.535370 pure+birth** on the same calls. C3 first ID counts are 8/6 for true K2, 3/5 for K3, 9/12 for K4, and 11/10 for K6. Seven of eight exceed the true count, but ruling L2 makes this a diagnostic rather than a winner gate: each speaker's utterances were assembled from different recording chapters. The cosine receipt `c4-synth-cosine-evidence.json` uses production WeSpeaker vectors from Gemini-attributed spans ≥2 s, keeps labels with ≥80% timed overlap with one reference speaker, and compares windows at least 120 s apart. On `meet_k2_s0`, 4,010 same-speaker pairs have median cosine .721 and 13.9% fall below C3's .46 threshold; 3,787 different-speaker pairs have median .239 and 3.7% exceed .46. This overlap explains some missed links and false merges; it does not prove every synthetic split has that cause.

The 10/60 schedule on the 2586 s `long60` reference improves over 20/120: C3+birth first/last IDs **6/6 for five true** and first/last DER **.167493/.175438**, versus pure+birth **26/22 IDs** and DER **.479654/.480236**. It still has .143582 speaker confusion and 3.5 s `S00`. Recorded schedule+API lag p50/p90 is 9.558/13.624 s; batch+Live cost is $1.368/h. The winning 15/180 schedule's completed long60 check appears in the verdict below.

Every Gemini call carries `timing_anomalies` and `timing_anomaly_rate = (clamped + dropped)/(returned words + dropped)`. The table counts exact H0 periodic calls plus their short Stop calls; full per-call rows, including zero rates, are in `c4-anomaly-summary.json` and the observation receipts. The maximum is a **single call's** rate, not a corpus average.

| Corpus / schedule | Calls with anomaly / calls | Clamped / dropped words | Max per-call anomaly rate |
|---|---:|---:|---:|
| accept6, 15/180 | 1 / 42 | 1 / 0 | .4608% |
| E1 system+mix, 15/180 | 0 / 42 | 0 / 0 | 0% |
| complete lex5m ×3, 15/180 | 0 / 60 | 0 / 0 | 0% |
| gold8, 15/180 | 1 / 57 | 1 / 0 | .4608% |
| complete Bill 30m, 15/180 | 5 / 120 | 5 / 0 | .1828% |
| accept6, 10/60 | 4 / 62 | 4 / 0 | 4.7619% |
| complete Bill 30m, 10/60 | 8 / 180 | 8 / 0 | .5587% |
| long60, 10/60 | 8 / 259 | 8 / 0 | .5587% |
| **long60, 15/180** | **7 / 173** | **7 / 0** | **.2481%** |
| synth8, 20/120 | 1 / 248 | 1 / 0 | .3497% |

The 4.7619% 10/60 accept6 maximum is one clamped word in a tiny Javier Stop call, while 15/180's accept6 maximum is one Adam Frank periodic word. The parser repair is included in cached re-parses; these few offsets cannot account for the large speaker-confusion differences.

### C4 verdict: growing context wins this prototype selection

**Winner by the brief's rule: S15/Lmax180/H0, C1 overlap plus C3 WeSpeaker linking and the 2 s birth rule.** Gemini supplies all within-window word timestamps, text, and local who-spoke-when; WeSpeaker fingerprints only merge Gemini-local labels across and inside windows. It creates no speech turns. Voice embeddings come only from Gemini-attributed continuous spans ≥2 s. This dependency is essential: paired pure Gemini fails E1 count and is materially worse on accept6 and long-form identity.

The winner meets every measured gate: H1 #3 accept6 settled DER **.098518** (six-case macro); E1 first displayed IDs **3 system / 4 mixed** for true **3 / 4**; complete 30-minute Bill **2/2 IDs** and DER **.056321**; recorded schedule+API p50 label lag **11.027 s** as the six-case median, **17.845 s** on Bill, and **17.515 s** on `long60`; measured batch plus $0.30/h Live words **$2.345/h** on Bill and **$2.387/h** on `long60`, under the $3/h bar. Its 2 s birth rule leaves **5.9 s** `S00` across accept6, **0 s** on Bill and `long60`. On E1 it leaves **1.7 s system / 1.5 s mixed** unattributed. The complete-reference lex5m and gold8 checks are supportive as shown above.

At the **exact winner schedule** on `long60` (2586/2586 s reference, five true voices), C3+birth shows **5 first / 5 last IDs**, first/last `common.score` DER **.048287/.045574**, and first speaker confusion **.024376**. Pure C1+birth on those identical Gemini calls shows **14/12 IDs**, first/last DER **.207681/.188692**. C3 has five births, **39 within-window local merges**, and 80 visible relabel events (**1.856/min**); pure has 20 births and 100 relabels (**2.320/min**). C3's long60 lag p50/p90 is **17.515/23.842 s**, Stop covers **[2580,2586] s**, and that cached short Stop call's recorded API response was **2.186 s**. The winner also repairs the Bill/Lex mixing seen in the 20/120 stress run: M1 overlaps **1001.5 s Bill / 18.1 s Lex**, and M2 **599.7 s Lex / 34.7 s Bill**; the other three IDs are primarily Keyu, Javier, and Adam. Its long60 DER falls from .300806 to .048287 on the same reference, with exact five-voice count.

**Verdict boundary.** This is an offline, recorded-response prototype win and a candidate for live-path qualification, not a product acceptance claim. The Stop deadline and real-time-paced latency are unmeasured; pre-Stop immediate WER excludes provisional Live words. E1 has no timed speaker truth, so exact ID count does not prove every turn is correct, and accept6 RTFL still scores .283553 DER. A live run must check that the short Stop call finishes before close, that visible relabeling is acceptable (E1: **4.172/min system, 5.960/min mixed** in this replay), and that the measured lag/cost hold with the actual Live words stream. The smallest sufficient design remains growing Gemini context, overlap continuity, optional ≥2 s WeSpeaker links, a 2 s birth gate, and the exact short Stop drain; no production integration is made in this pane.

### Product registry parity, after C4 port

**Question and falsifier.** If the product and prototype receive the same ordered Gemini window words, the same numeric WeSpeaker vectors, and the same S15/L180/H0 frontier, they should assign each window-local label the same meeting identity. One differing label, birth, merge, or displayed-ID count falsifies registry parity. The minimum inputs are retained window observations, numeric vectors, frontier, and each stateful registry. This zero-send replay imports the runtime registry and growing scheduler read-only from `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-runtime` at `a3fbf081`. Run `PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/continuity/parity.py` from the prototype worktree. Full per-window maps and first differences are in `P61/parity-S15-L180-H0.json`; the equal-threshold diagnostic is retained separately as `P61/parity-isolated-overlap03.json`.

The actual product composition uses the registry's **.6 s** default overlap threshold; C4 measured **.3 s**. Product defaults otherwise match L180/S15, cosine .46/.60, birth 2 s, and current Stop drain uses `[rolling frontier, accepted end]`. On the same cached numeric vectors, the threshold difference caused no observed assignment change: **377/377 windows agreed**, and every case's birth count, within-window merge count, and displayed-ID count matched. This proves the ported *registry decisions* on these inputs; it does not prove live encoder-input parity.

| Same cached words/vectors | Windows agreed | Births prototype/product | Local merges prototype/product | Displayed IDs prototype/product | Settled DER prototype / product word-owner / product published-turn |
|---|---:|---:|---:|---:|---:|
| accept6, H1 #3 six-case macro | 42/42 | 14/14 total | 8/8 total | 13/13 summed cases | **.098518 / .099110 / .119253** |
| E1 system, no timed truth | 21/21 | 3/3 | 13/13 | 3/3 | unmeasured |
| E1 mic mix, no timed truth | 21/21 | 5/5 | 12/12 | 4/4 | unmeasured |
| complete Bill 30m | 120/120 | 2/2 | 11/11 | 2/2 | .056321 / .057432 / .082148 |
| complete long60, five voices | 173/173 | 5/5 | 39/39 | 5/5 | .048287 / .049062 / .074174 |

The prototype column uses the C4 first-committed surface and the H1-exact scorer for accept6; it reproduces the committed C4 values. The product word-owner column changes only which rolling observation owns a word: product `_publish_window` takes a word whose **start** is in `[old frontier, new frontier)`, while the prototype took one whose **end** is in `(old frontier, new frontier]`. The product published-turn column also runs its actual `ordered_segments(..., preserve_order=True)` and `speaker_turns` projection before the same scorers. These are deterministic cached-input projections, not a paced LiveSession run: the product's VAD word gate, actual encoder vectors, microphone lane behavior, and downstream session rendering are outside this replay.

**First output divergence.** In Jamie Dimon window 2 `[0,30]`, the word “bank” spans 14.9–15.2 s across the 15 s frontier. The prototype first commits it in window 2; the product owned it at the preceding window by start time. The registry maps it to the same M1 in both paths. On RTFL, the first positive-duration divergence is window 5, “What?” at 59.9–60.2 s; on Adam Frank it is window 3, “search” at 29.6–30.4 s. This ownership and turn projection raises the accept6 published-turn DER by **.020736** over the prototype macro. Exact per-case values and window states are in the parity receipt.

**Product input defect.** The runtime `WeSpeakerWindowEmbeddings` takes the *first* continuous span reaching 2 s with gaps ≤.5 s; C4's production ONNX vectors used up to three spans of ≤10 s each with gaps ≤.6 s. Interval selections differ for **829/861 window-local labels**, starting at Jamie window 1 `spk:0`: C4 encoded `[1.5,11.5]` s while runtime would encode `[1.5,3.5]` s. RTFL Stop `spk:1` is eligible for C4 at `[84.5,88.2]` s and ineligible in the runtime recipe. This is a real input mismatch even though the shared-vector registry assignments match. Actual runtime-vector DER and speaker counts are **unmeasured**; C4's .098518 cannot be claimed as a product score. The corresponding `DEFECT:` lines are in the pane status for the runtime owner. P61 provider ledger stayed at 2,204 calls/$8.7949 during parity; no new Gemini calls were made.
