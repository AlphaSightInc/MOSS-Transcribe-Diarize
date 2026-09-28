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
