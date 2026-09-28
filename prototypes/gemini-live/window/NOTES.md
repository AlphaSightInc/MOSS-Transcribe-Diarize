# P53 diarized-window prototype (throwaway)

## Contract before measurement

**Structural question.** Can one bounded Gemini 3.5 Transcribe audio window yield fast, accurate speaker-attributed words, and can whole-recording/chunked calls meet the final-transcript bar?

**Minimum primitives.** (1) A public PCM16 mono 16 kHz interval defines the audio and its time origin. (2) A model call returns ordered words, local speaker labels, timestamps, latency, and usage. (3) A clipped reference supplies timed speech and text. (4) The production scorer compares those intervals. (5) A ledger counts paid calls. Removing any one loses the input boundary, observable output, truth, comparable quality, or cost.

**Invariants.** Word times are interpreted relative to the submitted audio; reference and hypothesis must share one origin. Speaker IDs have meaning only within one call unless an experiment establishes continuity. No private/operator audio is sent. Cached calls are never counted as independent latency/repeatability samples. All reported denominators and scorer variants are explicit. A final chunk seam needs an explicit label map before global scoring.

**Assumptions and unknowns.** The common corpus registry identifies the authorized public audio. Real-time quality from accelerated/offline calls is unknown. The production scorer may differ from the H1 collector's DER rules. Google concurrency limits, edge behavior, and label stability are unmeasured. Synthetic meetings have timed speakers but no reference text.

**Falsifiers.** Hybrid label primitive fails if no L ≤120 s reaches accept6 macro window DER <0.145. Anchors fail if exemplar labels do not reliably bind the same voice in the main window or degrade its DER. D4 fails if accept6 whole-clip final DER exceeds 0.110 under the comparable production score. A slower or less accurate alternative is rejected on measured paired windows.

**Tool decisions.** Use `common/gemini_common.diarize_window` for the actual paid API and its ledger/cache; a different wrapper would confound comparisons. Use `common/corpus.py` for authorized inputs and `common/score.py` for production metrics. Use distinct clips/offsets to estimate latency and controlled uncached repeats for determinism. Use one throwaway command in this directory to print each case and write numerical receipts. A result that crosses a bar or reverses a latency/quality trade-off changes L, stride, anchor, alternative, or final-pass verdict. No production implementation is authorized by this brief.

**Chunk-stitch subquestion.** Can a 20 s overlap carry local labels across three 10 min final chunks? Minimum primitives: each chunk's local label, its absolute word interval, the shared audio interval, and an injective label map. Invariant: each word is emitted once by keeping each chunk's 10 min core; an unmatched local label remains new/unknown. Assumption: at least one recurring speaker talks in each overlap. Falsifier: overlap evidence is absent or maps a recurring voice incorrectly, increasing stitched DER against the one-pass result. Tool: two 30 min public clips, three calls each using the shared helper; this decides whether simple overlap stitching is sufficient or continuity remains unresolved.

**Post-merge subquestion (lead requested).** Can production WeSpeaker audio centroids identify Gemini labels that are actually one voice? Minimum primitives: Gemini label, a continuous Gemini-attributed span of at least 2 s, the production ONNX embedding, cosine between centroids, and a pairwise merge threshold. Invariant: no label without enough observed audio is forced into a merge; no reference speaker identity informs the merge; score the same cached Gemini words before and after. Assumption: the cross-meeting 0.46 voiceprint threshold may or may not transfer to within-call fragments. Falsifier: no threshold improves accept6 macro without merging distinct true speakers, or the 74-label synthetic split is mostly ineligible/gets worse. Tool: reuse P61's interval selector plus the production CPU embedder, sweep 0.30–0.80; this determines whether acoustic post-merge can rescue D4 rather than merely treating the threshold as settled.

**Timestamp failure boundary.** Raw Gemini annotations produced a 55,935.6 s word end in a 606.3 s call. The shared parser now reports clamped/dropped anomalies on cached reparse; all verdict scores use the corrected parser. Preserve the raw-score receipt as failure evidence. A diagnostic ±0.5 s tolerance in P53's scoring is not a proposed product threshold.

**Scorer scale subquestion.** The production DER scorer's exact speaker assignment enumerates hypothesis-label subsets. Two K=6, 300 s windows yielded 60 and 52 labels and exhausted CPU without a result. The necessary primitive is the same maximum-weight one-to-one assignment over timed overlap weights. Invariant: a polynomial assignment must match production DER/miss/FA/confusion on tractable windows before use on those two. Falsifier: any material metric mismatch on a tractable control. Tool: SciPy's exact linear assignment for those measurements only; no production scorer change is proposed here.

## Command

`PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/window/probe.py all` from the worktree.

## Measurement populations and score meaning

All inputs are the public `common/corpus.py` registry. Calls use `common/gemini_common.py`, and diarization error rate (DER) uses `common/score.py` / production `moss_transcribe_diarize.evaluation`; H1-exact final comparisons use `harness/h1_offline.py`. Window DER remaps speaker labels **within each call**; it does not test continuity between calls. Synthetic reference files have speaker times but no reference text. Full-span DER on sparse references counts valid unannotated speech as false alarms, so reference-supported DER also restricts hypotheses to labeled spans. Selection evidence is accept6 primary; gold9 except `benchmark:acquired_jamie_dimon` (only 12.3/60 s timed), three fully labeled Lex five-minute clips, and fully labeled Lex Bill Ackman 30-minute clip as support. Gold9 NFL/Rolex cover 52.9/51.1 of 60 s; their small gaps can inflate miss. Acquired five-minute and Acquired Jamie Dimon 30-minute references are sparse, diagnostic only. RTFL 90 s covers 60.9 s, so its DER is a partial-reference diagnostic. Gold9 and accept6 contain overlapping source clips; they are not independent populations.

**Reference sets:** F1/F3 accept6 scores use the verified H1 #3 manifest reference selected by `common/corpus.py` at `a9634449`; the final comparison uses the H1-exact offline scorer at `3d5f61cb`. Non-accept6 scores use their corpus references. Earlier checkout-reference accept6 receipts remain append-only evidence and are superseded.

### F0 — Uncached latency

Each cell is API wall-time p50/p90 in seconds over **five distinct uncached audio inputs** at the stated length and concurrent-call count: 165/165 completed calls, zero API failures or 429s. Groups ran in order; other bake-off panes may share provider capacity, so concurrency differences are descriptive. The 30-minute inputs were two real public clips plus three distinct permutations of K2+K2+K3 public synthetic speech (at most seven source voices); no quality claim uses the permutations.

| L (s) | 1 call p50/p90 | 2 calls p50/p90 | 4 calls p50/p90 |
|---:|---:|---:|---:|
| 10 | 2.02 / 2.70 | 1.60 / 1.76 | 1.81 / 1.89 |
| 20 | 2.65 / 2.67 | 2.21 / 2.28 | 2.50 / 2.74 |
| 30 | 3.22 / 3.38 | 2.56 / 2.70 | 2.84 / 3.08 |
| 60 | 4.24 / 5.76 | 3.76 / 4.04 | 4.11 / 4.69 |
| 90 | 5.53 / 5.91 | 5.35 / 6.08 | 5.63 / 6.14 |
| 120 | 6.54 / 7.21 | 6.52 / 8.03 | 7.36 / 8.98 |
| 180 | 10.24 / 10.52 | 9.56 / 11.38 | 11.27 / 12.45 |
| 300 | 14.19 / 14.35 | 14.54 / 16.75 | 17.44 / 18.83 |
| 600 | 27.74 / 29.72 | 29.01 / 29.36 | 36.89 / 40.61 |
| 1200 | 68.03 / 69.37 | 67.77 / 73.25 | 81.38 / 87.80 |
| 1800 | 91.91 / 97.86 | 103.39 / 113.66 | 126.72 / 135.06 |

Least-squares fit to each length's p50: one concurrent call `latency ≈ 0.771 + 0.05166 L` seconds (R²=.9941); two `-0.321 + 0.05664 L` (R²=.9968); four `-0.738 + 0.06940 L` (R²=.9975). The negative fitted intercepts are interpolation artifacts, not physical startup times. Receipt: `evidence/P53/latency-fit.json`.

### F1 — Window quality (complete non-overlapping tiling)

DER below is the arithmetic mean of per-case DER, with each case's windows weighted by reference speech duration. WER uses **only whole reference turns fully inside each window**; the reference has no word-level timing, and this WER is a restricted text subset. `n` counts scored windows.

| L (s) | accept6 n | DER / confusion | Count error | WER / ref words | covered gold8 n | Supported DER / confusion | Count error | WER / ref words |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 62 | .1223 / .0238 | -.032 | .2564 / 195 | 84 | .1089 / .0156 | -.012 | .2329 / 219 |
| 20 | 32 | .1272 / .0387 | -.062 | .1967 / 478 | 42 | .1022 / .0346 | +.024 | .1713 / 613 |
| 30 | 21 | **.0938 / .0181** | .000 | .1600 / 850 | 28 | **.0797 / .0147** | .000 | .1592 / 1011 |
| 60 | 11 | .0961 / .0250 | +.182 | .1268 / 1412 | 14 | .1148 / .0394 | +.214 | .1555 / 1852 |
| 90 | 8 | .1085 / .0387 | +.125 | .1070 / 1570 | 11 | .1070 / .0330 | +.182 | .1325 / 2120 |
| 120 | 8 | .1180 / .0470 | +.250 | .1166 / 1578 | 11 | .1321 / .0573 | +.182 | .1425 / 2161 |

The hybrid primitive falsifier is **not triggered**: L=30 s is below .145 on accept6 H1 truth. This does not itself qualify live settled DER, because local labels still need continuity across calls. The 90 s RTFL fixture by itself scores .2747 DER at L30 over 3 windows and .4143 as one 90 s call.

Cross-pane continuity evidence (P61, not a P53 measurement): offline replay at **S=10 s, L=30 s, hold=5 s** on the same accept6 audio used 62 window calls. On the verified H1 #3 reference set, pure-Gemini first-view DER macro=.161872 / 6; L1 WeSpeaker fingerprint linking/within-window merging at .46/.60 gave .110645 / 6. Receipt: `evidence/P61/accept6-*-S10-L30-C3-span2s.json` and P61 `NOTES.md`. This supports S=10 as the continuity candidate, while real-time-paced row latency remains unmeasured here.

| Synthetic truth | L30 DER / confusion / count error | L60 | L120 | L300 |
|---|---:|---:|---:|---:|
| 4 voices | .2408 / .1157 / +1.22 (41 windows) | .2453 / .1312 / +2.57 (21) | .2983 / .1647 / +4.55 (11) | .2628 / .1112 / +1.20 (5) |
| 6 voices | .2098 / .0966 / +1.52 (40) | .3244 / .2166 / +4.05 (20) | .3577 / .2558 / +9.90 (10) | .5620 / .4636 / +27.75 (4) |

Count error is hypothesis minus reference speakers per window. Many-voice over-splitting worsens with L, especially K=6.

RTFL90 is a **partial-reference diagnostic** (60.9/90 s timed): L10/20/30/60/90 s window DER=.3606/.4522/**.2747**/.2786/.4143; confusion=.0752/.1549/**.0169**/.0255/.1579; mean count errors=-.111/-.400/.000/.000/.000; restricted WER=.2791/129, .2133/150, .1140/193, .1171/205, .1214/206 reference words. Its L120 call is the same one 90 s audio and score as L90.

### F2 — Timing and edges

On accept6 H1 truth at L30, first 2 s DER=.1186 / 40.7 reference-speech seconds; middle DER=.0734 / 511.8; last 2 s DER=.1547 / 37.4. Whole-turn edge WER pooled over all tested L is first .4762 / 21 words, middle .0992 / 3,076, last .3582 / 67; small edge text denominators limit the conclusion. The median absolute first/last recognized-word offset from the reference **turn** boundary is .093/.100 s over 4,144 matched turns, p90 .526/.439 s. These are not word-timestamp errors against independently timed words; that truth is unavailable.

The fixed shared parser reports timing anomalies in 12/519 window calls (14 clamped words, zero dropped) and 3/34 final calls (2 clamped, 1 dropped). A raw 606.3 s synthetic call contained a word ending at 55,935.6 s: uncorrected DER 105.026, corrected .221. Raw API annotations are retained in shared cache; verdicts use the fixed parser. Raw adjacent-word overlaps appeared in 21/519 window calls (21 pairs).

| Quality-window L (s) | Calls with timing anomaly / all calls | Clamped / dropped words |
|---:|---:|---:|
| 10 | 9 / 161 (5.6%) | 11 / 0 |
| 20 | 1 / 82 (1.2%) | 1 / 0 |
| 30 | 2 / 135 (1.5%) | 2 / 0 |
| 60 | 0 / 69 | 0 / 0 |
| 90 | 0 / 21 | 0 / 0 |
| 120 | 0 / 42 | 0 / 0 |
| 300 | 0 / 9 | 0 / 0 |

### F3 — Whole-clip final pass (D4)

| accept6 clip | Pure Gemini DER | L1 .46 merge DER | Gemini WER | H1 #3 final DER / WER | Gemini labels / true | Gemini clamped/dropped words |
|---|---:|---:|---:|---:|---:|---:|
| Jamie Dimon 180 s | .0638 | .0638 | .0470 | .0768 / .0697 | 3/3 | 0/0 |
| RTFL discussion 90 s | .4143 | .3747 | .0631 | .3449 / .0534 | 4/4 | 0/0 |
| Adam Frank 180 s | .1478 | .0261 | .1318 | .0662 / .1262 | 3/2 | 0/0 |
| Bill Ackman 60 s | .0683 | .0683 | .1648 | .0755 / .1591 | 2/2 | 0/0 |
| Keyu Jin 60 s | .0367 | .0367 | .1295 | .0790 / .0647 | 2/2 | 0/0 |
| Javier intro 50 s | .0200 | .0200 | .0885 | .0178 / .0973 | 1/1 | 0/0 |

On the **same H1 #3 truth and exact final scorer**, pure Gemini macro DER=.125138 / 6 and duration-weighted=.133329, above D6's .110 bar. The L1 .46 acoustic merge reaches macro=.098265 and weighted=.092263, below the DER bar; H1 #3 recorded final is macro=.110022 and weighted=.107954. Gemini merged/pure WER is unchanged at macro=.104123 versus H1's .095074. H1 reference-speech final DER macros are Gemini pure=.113498, merged=.086610, and recorded MOSS=.089845. RTFL's timed reference covers 60.9/90 s, and Gemini text coverage there is .8673, so no-dropped-passages is unproven. Accept6 passing DER after merge is a candidate result; F4's synthetic counterexamples block a general final-merge qualification.

On the 8 synthetic whole clips, K=2 `meet_k2_s0` yields **74 labels for 2 voices**, DER=.4267. The other K2 call yields 3 labels / DER=.1576; K4 calls yield 6 and 4 labels / corrected DER=.2211 and .1590; K6 calls yield 10 and 14 labels / DER=.3904 and .2915. A single 30 min Gemini call succeeded on both long30m clips, at 100.35 and 97.32 s API wall time. The fully labeled Lex Bill Ackman long clip scored DER=.0615, WER=.1464; the Acquired Jamie Dimon long reference labels only 20.8%, so its raw DER=3.784 is not a full-audio quality verdict.

Other whole-clip cases (coverage = fraction of audio with timed reference speech; sparse-reference full DER/WER must not be read as full-audio quality):

| Tier / case | Coverage | Full DER | Supported DER | WER | Gemini/true labels |
|---|---:|---:|---:|---:|---:|
| gold9 acquired_jamie_dimon | .205 | 3.813 | .270 | .856 | 4/3 |
| gold9 acquired_nfl | .881 | .517 | .497 | .025 | 3/3 |
| gold9 acquired_rolex | .852 | .200 | .037 | .050 | 2/2 |
| gold9 lex_bill_ackman | 1.000 | .068 | .068 | .165 | 2/2 |
| gold9 lex_javier_milei | 1.000 | .090 | .090 | .096 | 2/2 |
| gold9 lex_keyu_jin | 1.000 | .037 | .037 | .129 | 2/2 |
| gold9 acquired_jamie_dimon_3min | .994 | .064 | .061 | .047 | 3/3 |
| gold9 lex_adam_frank | 1.000 | .148 | .148 | .132 | 3/2 |
| gold9 lex_shapiro_destiny | .843 | .189 | .017 | .144 | 4/3 |
| bench5m acquired_alphabet | .263 | 2.676 | .151 | .458 | 3/2 |
| bench5m acquired_coca_cola | .259 | 2.729 | .221 | .355 | 2/2 |
| bench5m acquired_jamie_dimon | .117 | 7.038 | .500 | 2.045 | 3/3 |
| bench5m acquired_nfl | .228 | 3.212 | .168 | .709 | 3/2 |
| bench5m acquired_rolex | .304 | 2.556 | .352 | .561 | 3/3 |
| bench5m lex_bill_ackman | 1.000 | .125 | .125 | .118 | 3/2 |
| bench5m lex_javier_milei | 1.000 | .052 | .052 | .086 | 3/2 |
| bench5m lex_keyu_jin | 1.000 | .024 | .024 | .053 | 2/2 |
| rtfl90 (duplicates accept6 RTFL) | .677 | .414 | .310 | .063 | 4/4 |
| synth k2_s0 | .871 | .427 | .404 | — | 74/2 |
| synth k2_s1 | .874 | .158 | .127 | — | 3/2 |
| synth k3_s0 | .882 | .159 | .126 | — | 4/3 |
| synth k3_s1 | .884 | .213 | .186 | — | 7/3 |
| synth k4_s0 | .871 | .221 | .188 | — | 6/4 |
| synth k4_s1 | .888 | .159 | .128 | — | 4/4 |
| synth k6_s0 | .877 | .390 | .364 | — | 10/6 |
| synth k6_s1 | .873 | .291 | .263 | — | 14/6 |
| long30m acquired_jamie_dimon | .208 | 3.784 | .145 | 1.232 | 4/3 |
| long30m lex_bill_ackman | 1.000 | .062 | .062 | .146 | 3/2 |

### F4 — L1-compliant centroid post-merge

This arm imports P61's `embedding_intervals`: only continuous Gemini-attributed speech spans ≥2 s enter the **production ONNX WeSpeaker** embedder. It merges Gemini labels with centroid cosine above the tested threshold; Gemini still owns word times and segmentation. The earlier ≥2 s *aggregate* selector receipts are superseded. No truth speaker label participates in the merge.

| Cosine threshold | accept6 H1-truth final DER macro | accept6 cases merged |
|---:|---:|---:|
| pure, no merge | .125138 | 0 |
| .30 | .156043 | 2 |
| .40–.50 | **.098265** | 2 |
| .60–.70 | .104860 | 1 |
| .80 | .125138 | 0 |

The production voiceprint threshold **.46** merges Adam's two labels (cosine .733), changing his DER .147778→.026111, and merges an RTFL split (.414255→.374685). The H1-exact scorer reproduced these production-score final DER/WER values on all six accept6 cases. The same .46 rule is unsafe across synthetic meetings:

| Synthetic call | True voices | Pure labels / DER | L1-eligible labels | .46 labels / DER |
|---|---:|---:|---:|---:|
| K2 s0 | 2 | 74 / .4267 | 28 | 48 / .2157 |
| K2 s1 | 2 | 3 / .1576 | 3 | **1 / .5859** |
| K4 s0 | 4 | 6 / .2211 | 5 | 4 / .3213 |
| K6 s0 | 6 | 10 / .3904 | 8 | 7 / .4226 |

The 74-label case improves DER but still has 48 IDs for two true voices; another two-voice case merges distinct speakers, and K4/K6 DER rises. Raising the threshold to .60 avoids the K2 s1 collapse but still worsens K4/K6. **Verdict:** centroid merge rescues accept6 over-splits and makes the D6 DER number pass on that set, but this pairwise policy fails the many-speaker generalization check. It is a diagnostic candidate, not a qualified final-pass rule.

### F5 — Scorer and RTFL anatomy

For the **same retained H1 settled intervals**, production DER equals H1 `der_raw` on all six cases to ≤0.000001. H1's ruled settled DER is lower in four because it discounts S00 confusion; final H1 intervals were not retained for same-interval replay. The lead's H1-exact offline scorer at `3d5f61cb` reproduces all eight retained H1 macro metrics; on P53's pure and merged final accept6 surfaces its DER/WER matches `common/score.py` per case exactly. On RTFL, Gemini final DER .414255 = miss .151955 + false alarm .104429 + confusion .157872. Timing miss plus false alarm account for .256384 (62% of total); confusion 38%. The 0–30 / 30–60 / 60–90 s bins have 1.18/4.83/3.24 s missed speech and 4.85/4.76/0 s confusion. Numeric receipts: `scorer-reconciliation.json`, `rtfl-anatomy.json`, `h1_final` JSONL rows.

### F6 — Determinism and anchors

Two **uncached** calls on the same 60 s RTFL window returned exactly the same 139 words, labels, and start/end timestamps (no label permutation, text edits, or timestamp shift); latency was 4.69/3.63 s, with zero timing anomalies. This is one repeated input, not a general guarantee.

Thirty anchor trials used a 30 s main window and earlier 5 s reference speech per present speaker, separated by 0.5 s silence: 10 accept6, 10 covered gold9, 10 synthetic; K=1/2/4/5/6 counts 12/8/6/3/1. The exemplar kept the same label later in the window for **53/73 speaker trials (72.6%)**, and all labels matched in only 17/30 windows. Mean paired DER was .172812 without anchors versus .172509 with them; by tier: accept6 .189593→.155587, gold9 .083079→.103269, synthetic .245762→.258672. Six of 30 windows degraded by >.001 DER. No parser timing anomaly in 30 base or 30 anchored calls. The identity-binding falsifier **is triggered**: anchors are not reliable enough to carry meeting identity.

### F7 — Paired Gemini 3.8 Flash alternative

The requested `MINIMAL` thinking setting returned HTTP 400 `INVALID_ARGUMENT` on three attempted calls. The next setting, `LOW`, was accepted. Of 15 planned identical windows, **13 yielded usable paired outputs**; two 120 s synthetic K4/K6 windows repeatedly produced malformed JSON after three LOW attempts each. Some other LOW outputs escaped the JSON object's quotes one or two layers; the prototype repaired only that observed shape and recorded failures. Flash also varied between phrase and word segments despite a word-level prompt (13 segments on the 139-word Keyu window). The 13 successful pairs are a selected subset; omitted hard cases cannot support a favorable Flash claim.

| Same-window subset | Pairs | 3.5 Transcribe DER | 3.8 Flash DER |
|---|---:|---:|---:|
| accept6, H1 #3 truth | 6 | .1137 | .2003 |
| covered gold9 sample | 2 | .2839 | .1955 |
| complete Lex five-minute clips | 3 | .0689 | .1275 |
| synthetic K4/K6 sample | 2 | .2213 | .3106 |
| **all usable pairs** | **13** | **.1461** | **.1997** |

Flash had lower DER on 3/13 windows, including the near-complete NFL sample (.517→.314) and a Javier intro slice (.067→.006). Pooled WER on fully contained reference turns was .0869 for Transcribe versus .1195 for Flash over 1,841 reference words. Median paired API latency was 6.34 versus 5.73 s. Successful-call cost summed to $.0525 versus $.2123 (Flash 4.04×); early malformed-response Flash calls were not fully metered, so this undercounts Flash cost. Transcribe parser anomalies affected 0/13 usable pairs. **Verdict:** Flash does not beat 3.5 Transcribe as the diarized-window primitive on accept6 quality, output reliability, or cost. It is slightly faster at the sample median.

### F8 — Non-speech failure surface

The lead authorized locally generated non-private audio. Two uncached 30 s calls each on digital silence, low-level white noise, and a gated synthetic chord/rhythm returned: silence **1 hallucinated word (`2`) in each call**; white noise **2 hallucinated words (`好的。`) in each call**; synthetic music-like signal **zero words in both calls**. All six calls succeeded with zero parser timing anomalies. These are generated signals, not a measurement on real room recordings or commercial music. The downstream design needs independent speech evidence before trusting a word in an otherwise non-speech window.

### F9 — Thirty-minute whole call versus overlap stitching

Both public 30-minute clips succeeded as one 1,800 s Gemini call. The stitch arm used three 10-minute cores, 20 s overlaps, and label mapping from word-time overlap. The original stitch receipt incorrectly scored bare word intervals, inflating missed speech; **`stitch_v2` supersedes it** and groups contiguous same-speaker words exactly as the one-pass comparator does.

| Clip and reference scope | One-call DER / WER | Stitched DER / WER | One-call / stitched labels |
|---|---:|---:|---:|
| Lex Bill Ackman, complete 1,800 s | .0615 / .1464 | .1880 / .1405 | 3 / 4 |
| Acquired Jamie Dimon, only 374 s timed; diagnostic | supported .1450 / raw WER 1.2318 | supported .3411 / raw WER 1.2385 | 4 / 6 |

On the complete Lex case, stitched miss=.0164 and speaker confusion=.1715; the latter drives the DER regression. Each 20 s seam contained only one prior speaker, so an absent voice became a new ID in the next chunk. Six chunk calls had zero parser timing anomalies. **Verdict:** simple overlap-time matching does not preserve final-pass speaker identity; the one-call final pass is better supported here.

### F10 — Decisions and limits

**D1 — Live-window candidate: L=30 s, S=10 s, hold=5 s.** L30 has the lowest measured accept6 H1-truth local-window DER (.0938) and covered gold8 supported DER (.0797), with 3.22/3.38 s serial API p50/p90. L20 has higher accept6 DER (.1272); L60 is close in DER (.0961) but slower (4.24/5.76 s serial) and tends to split more labels. S10/hold5 comes from P61's separate offline continuity replay on the same accept6: pure Gemini first-view DER .161872 versus L1 fingerprint linkage .110645 over 62 calls. **This is a candidate, not a live qualification:** P61's K6/E1 speaker-count gates fail, and real-time-paced label latency is unmeasured.

**D2 — Final-pass verdict:** one whole Gemini call is feasible through 30 min and beats simple 10-minute overlap stitching on the complete long Lex case. Pure whole-clip Gemini **fails** D6 final DER ≤.110 on accept6 (H1-exact macro .125138). The predeclared L1 .46 merge **passes accept6 DER** (.098265), chiefly repairing Adam's Lex intro split, but the same rule falsely merges distinct synthetic voices and worsens K4/K6. Keep MOSS H1 #3 final as the recorded comparator; treat Gemini whole-call plus acoustic merge as a prototype candidate requiring a new falsifiable identity policy before production qualification. The final WER remains .104123 for both Gemini arms versus MOSS .095074.

**D3 — Failure boundaries:** raw Gemini word offsets require the shared parser clamp/drop (12/519 quality and 3/34 final calls anomalous); generated silence/noise can produce words; Flash LOW has a 13/15 usable-output rate in this paired sample; simple overlap cannot identify a speaker absent from the seam. No operator/private audio, mic, host, or long-running service was used. The largest accepted audio was 1,800 s PCM16 mono at 16 kHz (57.6 MB raw WAV payload plus header). More than eight true speakers, real music/room recordings, independent word-timestamp truth, and real-time-paced settled/final quality are **unmeasured**. P53 ledger records 577 calls, 3 local SDK client-closed errors retried during quality, and $5.2792 cost; early malformed Flash responses lacked usage receipts, so recorded cost is a lower bound below the $25 lane cap.

## Follow-up structural contract (final identity policy and word gate)

**Structural questions.** A high speaker-embedding cosine can mean one voice split across recording conditions or two different voices that sound similar. Can turn-taking evidence separate those cases without losing the Adam intro repair? Can a local speech detector reject words that Gemini invents in non-speech while retaining words in real speech?

**Minimum primitives.** A Gemini label owns timed words; a production WeSpeaker vector exists only from continuous attributed spans ≥2 s; cosine proposes an identity edge. An alternating A–B–A turn pattern supplies evidence that two labels are distinct. A merge partition maps labels to final IDs. For the word gate, 10 ms WebRTC voiced frames and a word's ±0.2 s interval suffice to decide whether there is speech evidence near it. Reference speaker intervals and text score outcomes but never enter the policy. Removing any primitive loses either candidate similarity, contradiction evidence, the final identity state, or the independent speech signal.

**Invariants.** Every retained word keeps Gemini timing/text. Only eligible acoustic vectors can create merges. Conversational exclusion is symmetric and transitive merge groups must not contain an excluded pair. No truth label or reference text chooses a merge. Tune thresholds/gap only on the stated tune split; freeze before scoring test. Cache-only reads may not trigger a paid provider call. The word gate uses production WebRTC mode 1, 10 ms, 16 kHz and keeps a word when any voiced frame intersects its ±0.2 s neighborhood.

**Assumptions/unknowns.** Turn alternation may also arise when Gemini splits one true person. Repeated speakers may never alternate in a short clip. Centroid recomputation may or may not improve single-link. Gold8 and accept6 include overlapping audio, so the nominated test split is not independent. Reference words lack independent word times; a dropped Gemini word inside a timed reference turn is only a proxy for a real-word false drop. E1 has no timed word truth.

**Falsifiers and tool decisions.** H-A fails if any tune-selected threshold that repairs real splits also falsely merges real speakers. H-B fails if a true-same pair shows its exclusion pattern or a high-cosine true-different pair lacks it. H-C earns a place only if recomputed-centroid agglomeration changes measured outcomes. The VAD gate fails if it drops meaningful real-corpus words or keeps generated silence/noise hallucinations. Use cached whole-clip Gemini words, P61's L1 interval selector, the production ONNX embedder, H1-exact final scorer on accept6, and production WebRTC settings. These tools are necessary to test the actual policy path; no product code changes follow without a tune/test verdict.

### F12 — Non-speech word gate (measured)

The production live VAD uses WebRTC mode 1 at 16 kHz with 10 ms frames. Keep a Gemini word iff at least one voiced frame intersects `[word.start−0.2 s, word.end+0.2 s]`. This check changes neither Gemini's timestamps nor text for retained words.

| Cached population | Gemini word observations | Dropped | DER / WER change |
|---|---:|---:|---|
| accept6, H1 #3 truth | 1,784 | 0 | none on all six clips |
| covered gold8 | 2,495 | 0 | none on all eight clips |
| complete Lex five-minute clips | 2,404 | 0 | none on all three clips |
| generated digital silence | 1 hallucinated word | 1 (`2`) | no reference |
| generated low white noise | 2 hallucinated words | 2 (`好`, `的。`) | no reference |
| generated music-like chord/rhythm | 0 | 0 | no reference |

Thus 0/6,683 returned real-corpus words were removed and 3/3 observed non-speech hallucinated words were removed. Independent word-level truth is unavailable; the no-drop claim is about Gemini output, not verified human words. WebRTC marked all 3,000 music-like frames voiced despite no Gemini words, so this gate alone does not prove music suppression. On the public E1 system fixture, 31 cached S10/L30 windows contained 2,532 repeated word observations and the gate removed zero. E1 has only two WebRTC-unvoiced stretches ≥0.5 s totaling 1.57 s, with no Gemini word midpoint inside them; it supplies no hallucination-removal test or word-level truth. Receipt: `evidence/P53/final-policy-vad.json`.

### F11 — Final-pass identity policy, frozen tune then test

The policy combines **cosine ≥ .65** with a **conversation veto**: labels observed in A–B–A turns with both intervening gaps ≤2 s cannot be merged, even indirectly. Every vector uses the production ONNX WeSpeaker encoder on Gemini-attributed continuous spans ≥2 s. This is a cache-only prototype; no provider calls or product code changes. The test choice was frozen in `evidence/P53/final-policy-selection.json` before test scoring. The threshold sweep used .40/.46/.50/.55/.60/.65/.70/.75/.80 and gap sweep 2/5/10/20/30 s.

| Split / policy | Real clips | Real macro DER | Real false merges / residual splits | Synthetic clips | Synthetic macro DER | Synthetic false merges / residual splits |
|---|---:|---:|---:|---:|---:|---:|
| TUNE pure Gemini | 11 | .137553 | 0 / 4 | 4 s0 | .299211 | 0 / 76 |
| TUNE cosine .65 only | 11 | .100578 | 0 / 0 | 4 s0 | .276970 | 1 / 48 |
| TUNE selected .65 + A–B–A veto | 11 | **.100578** | **0 / 0** | 4 s0 | .283440 | **0 / 51** |
| TEST pure Gemini | 7 distinct real | .119219 | 0 / 2 | 4 s1 | .205365 | 0 / 12 |
| TEST selected | 7 distinct real | **.098561** | **0 / 1** | 4 s1 | **.181057** | **0 / 7** |

Real TUNE = covered gold8 + complete Lex five-minute ×3. Real TEST = accept6 + complete Lex Bill 30-minute; rtfl90 is reported below but excluded from the macro because it duplicates accept6 RTFL audio. False merge diagnostics require each Gemini label to have ≥0.5 s timed truth overlap and ≥70% of that overlap from one truth speaker. Mixed or weak labels are unclassified. Gold NFL/Rolex have small untimed gaps and Shapiro/RTFL have partial timed truth; their raw DER can overstate misses. **The nominated TUNE/TEST split leaks exact PCM:** gold Bill/Keyu 60 s and calibration Jamie/Adam 180 s repeat accept6 clips, while Lex Bill 5-minute is a prefix of the 30-minute test. Only synthetic s1 and the long-clip continuation offer fresh audio evidence; the test macro is not an independent generalization estimate.

Parser anomalies in these cached whole-clip calls: TUNE **1/15 calls (6.7%)**, one clamped word and zero dropped (`synth:meet_k4_s0`); TEST **1/12 calls (8.3%)**, two clamped words and zero dropped (Lex Bill 30-minute). The current Lex Bill 30-minute cache entry is **a later Gemini response** than F3/F9's original: cached latency 133.23 versus 97.32 s and 5,900 versus 5,899 parsed words. Its pure DER .083704 here therefore differs from F9's .061542; both use the complete reference and common scorer. The later response has one in-bounds but implausible `basics` interval (485.4–1486.1 s); removing that one word does not change the reported DER. Do not attribute the long-clip difference to the identity policy or reference revision.

| TEST case / reference | Pure → policy DER | Truth / Gemini → policy IDs | Policy false merges / residual splits | Clamped / dropped words |
|---|---:|---:|---:|---:|
| accept6 Jamie 180 s, H1 #3 | .063795 → .063795 | 3 / 3 → 3 | 0 / 0 | 0 / 0 |
| accept6 RTFL 90 s, H1 #3 partial | .414255 → .414255 | 4 / 4 → 4 | 0 / 1 | 0 / 0 |
| accept6 Adam 180 s, H1 #3 | .147778 → **.026111** | 2 / 3 → 2 | 0 / 0 | 0 / 0 |
| accept6 Bill 60 s, H1 #3 | .068333 → .068333 | 2 / 2 → 2 | 0 / 0 | 0 / 0 |
| accept6 Keyu 60 s, H1 #3 | .036667 → .036667 | 2 / 2 → 2 | 0 / 0 | 0 / 0 |
| accept6 Javier 50 s, H1 #3 | .020000 → .020000 | 1 / 1 → 1 | 0 / 0 | 0 / 0 |
| complete Lex Bill 30 min, common scorer | .083704 → .060764 | 2 / 3 → 2 | 0 / 0* | 2 / 0 |
| rtfl90 duplicate, common scorer | .414255 → .414255 | 4 / 4 → 4 | 0 / 1 | 0 / 0 |
| synth K2 s1, common scorer | .157602 → .157602 | 2 / 3 → 3 | 0 / 1 | 0 / 0 |
| synth K3 s1, common scorer | .213417 → .131871 | 3 / 7 → 4 | 0 / 1 | 0 / 0 |
| synth K4 s1, common scorer | .158978 → .158978 | 4 / 4 → 4 | 0 / 0 | 0 / 0 |
| synth K6 s1, common scorer | .291464 → .275779 | 6 / 14 → 12 | 0 / 5 | 0 / 0 |

**Accept6 decision:** H1-exact final DER macro is pure .125138 versus policy **.104860** (≤.110); H1 #3 recorded MOSS final is .110022. The policy leaves Gemini text intact, so its accept6 final WER stays .104123. The improvement is Adam's Lex voice-over split; RTFL remains a large timing/attribution error (F5). `*`The long Lex Gemini label `spk:2` overlaps 681 s of Bill and 646 s of Lex truth, so its merge with a Lex label is **not classifiable as a clean-label false merge**; zero means zero detected, not proof of pure identities.

The H-A-only synthetic false merge is K4 s0 `spk:2`/`spk:4`, cosine **.741**, distinct dominant truth voices (spk3/spk1). Their labels are themselves contaminated by the other voice (truth-overlap purities 75%/84%), so the high cosine is at least partly a Gemini segmentation artefact; separate real-voice similarity cannot be isolated. One A–B–A motif blocks that merge. **H-B's premise is also falsified:** three tune and two test high-cosine *true-same* synthetic pairs have A–B–A motifs (e.g. K2 s0 cosine .862, K3 s0 .854, K2 s1 .870). The veto leaves those splits; no such high-cosine true-same motif appeared on the real clips. No attributable high-cosine true-different pair lacked a motif in this sample. With the veto, single-link and recomputed-centroid agglomeration had identical real and synthetic scores at .65, so H-C adds no measured value. All tested 2–30 s gaps gave the same selected aggregate; 2 s is the smallest tested.

## POLICY — final-pass prototype handoff

```text
words = Gemini whole-clip words; turns = contiguous same-label words with gap <= 1.5 s
for label: embed each continuous attributed span >= 2 s with production WeSpeaker
for eligible label: centroid = unit(mean(span vectors))
excluded = label pairs in any A-B-A / B-A-B turns with both turn gaps <= 2 s
groups = singleton Gemini labels
for eligible label pair in descending cosine (stable label tie-break):
    if cosine < 0.65: stop
    if groups differ and no cross-group pair is excluded: union groups
remap each word's speaker through its group; keep original text/times
drop a word only if WebRTC mode-1/10-ms at 16 kHz has no voiced frame in [start-.2, end+.2]
```

The word gate can run before or after identity remapping because it uses only audio/times. **Verdict:** the identity policy passes the nominated accept6 DER bound and observed real false-merge check; it is a **candidate** because tune/test overlap, mixed labels, and true-same synthetic converse motifs limit generalization. F12's gate removes the measured silence/noise hallucinations with zero returned-word drops on covered real clips; real music and independent word truth remain unmeasured. Receipts: `evidence/P53/final-policy-{vectors,tune,test,pair-audit,vad}.json`; reproducible offline command: `python prototypes/gemini-live/window/final_policy.py {vectors,tune,test,audit,vad}` (run each stage separately, with `selection.json` frozen before `test`).

## Variance follow-up structural contract (before new measurement)

**Structural question.** Does the selected final-pass policy meet DER ≤.110 across repeated Gemini responses, or did one favorable response create the apparent win? On RTFL, which timed error source causes its .414 DER, and can a general rule repair it without moving error to other cases?

**Minimum primitives.** A fresh response is an independent whole-clip Gemini draw; its raw response and usage form one receipt. The frozen acoustic-vector extraction and turn-veto rules map that response's labels to final IDs. H1 #3 timed reference and exact final scorer yield comparable DER. For RTFL, timed reference speech, its overlap with other reference speakers, hypothesis speech, and the scorer's fixed speaker mapping are the smallest facts needed to attribute missed time, false time, and wrong-speaker time. There is no need for a new model or production component.

**Invariants.** Four uncached responses per accept6 clip and two for complete Lex Bill 30 minutes; the canonical cache remains untouched. Every fresh response uses the same frozen .65/2 s/single-link policy and production ONNX embedder. H1-exact final scoring applies to accept6. Pair draw index only to form four six-case macro samples; also enumerate all 4^6 cross-case recombinations so the pass fraction is not an arbitrary pairing effect. No reference label informs the policy. Stay below $3 new spend and use public corpus audio only.

**Assumptions/unknowns.** Gemini calls may be correlated despite `use_cache=False`; four draws are a small sample, not a probability guarantee. The RTFL reference covers only part of 90 s, and its word times are turn-level rather than independent word truth. The existing cache's Lex Bill response was overwritten, so earlier and current whole-call results are distinct draws. Exact request success, output form, variance, and source of RTFL error are unmeasured until receipts land.

**Falsifiers and tool decisions.** A meaningful stability claim fails if the four paired macros or exact 4^6 combinations often exceed .110, or if a fresh response creates a real false merge. Use `diarize_window(use_cache=False)` with a per-draw raw JSON cache directory because it exercises the actual Gemini path without replacing canonical responses; record usage/cost and stop under cap. Reuse `embedding_intervals`, production WeSpeaker, the frozen merge rule, and `h1_offline.score_case` so any change is response variance, not a scorer or policy rewrite. For RTFL, reproduce production DER decomposition with interval arithmetic; any proposed general adjustment must be scored across all accept6 draws and must not worsen the non-RTFL cases. If evidence cannot separate timing from attribution, report unknown rather than invent a cause.

**One bounded RTFL counterfactual.** Lowering cosine to .55 merges RTFL's true-same labels (cosine .5529), but also merges a Shapiro pair at .6382 and raises its DER .188852→.193443. This may be due to `words_to_segments` extending timing when it merges adjacent words after speaker remapping. Test one structural adjustment: group Gemini words into turns first, then remap only the turn's speaker without changing its start/end/text. Falsifier: RTFL fails to improve, any other covered real clip or synthetic meeting worsens in DER/false merges, or fresh accept6 draws fail the .110 macro bound. This uses only cached responses and production scoring; it does not change the accepted rule unless measured and adopted by the lead.

### F13 — Fresh whole-call variance under the frozen final policy

**Verdict:** the policy's accept6 H1-exact final DER was **.104860 in all four fresh six-case rounds**, below .110 each time. Pure Gemini's four macro scores were .125138/.125138/.110694/.125138, all above .110. The measured win is repeatable on these responses; it is not a statistical guarantee because five of six cases returned identical parsed words, speakers, and times on all four uncached calls. Adam's third draw changed 60/549 speaker labels, 44 word timestamps, and two texts. All 26 calls were billed, SDK-cache `cached=false`, with zero provider error rows and zero parser timing anomalies.

| accept6 case, H1 #3 truth | Pure Gemini DER mean [min, max], 4 draws | Policy DER mean [min, max], 4 draws |
|---|---:|---:|
| Jamie Dimon 180 s | .063795 [.063795, .063795] | .063795 [.063795, .063795] |
| RTFL discussion 90 s, partial timed reference | .414255 [.414255, .414255] | .414255 [.414255, .414255] |
| Adam Frank 180 s | .126111 [.061111, .147778] | **.026111** [.026111, .026111] |
| Bill Ackman 60 s | .068333 [.068333, .068333] | .068333 [.068333, .068333] |
| Keyu Jin 60 s | .036667 [.036667, .036667] | .036667 [.036667, .036667] |
| Javier intro 50 s | .020000 [.020000, .020000] | .020000 [.020000, .020000] |
| **Macro of six** | **.121527** [.110694, .125138] | **.104860** [.104860, .104860] |

The fraction of the **four paired macro draws** at DER ≤.110 is **0/4 pure versus 4/4 policy**. Enumerating all **4⁶=4,096 cross-case recombinations** of these observed draws gives 0/4,096 versus 4,096/4,096; those recombinations are arithmetic, not 4,096 independent model calls. The policy detected zero false-merge groups among truth-attributable labels in 24 accept6 draws; RTFL retains one split in each. Its margin to the .110 bound is only .005140, so unobserved response modes remain material.

Two fresh complete-reference Lex Bill 30-minute calls were identical: pure common-scorer DER **.061542 [.061542, .061542]**, policy **.038603 [.038603, .038603]**, 3→2 speaker labels. The current canonical cache contains a different later response (pure .083704, policy .060764; F11), showing that longer-call outputs can vary even though this pair did not. All raw responses are isolated at `evidence/P53/variance-raw/<case>/draw-N/`; one numeric receipt per draw is in `variance-draws/`, aggregate in `variance-summary.json`. New Gemini spend **$0.304052 for 26/26 successful calls**, below this brief's $3 cap. No operator/private audio or canonical cache write.

### F14 — RTFL 90-second error anatomy and bounded policy check

The H1 #3 RTFL reference times **60.894/90 s (67.7%)**; 29.106 s lacks a timed speaker label. The timed reference and Gemini hypothesis each have **zero annotated overlapping-speaker time**, so overlap contributes no measured DER here; simultaneous voices in the audio without annotation remain unknown. The canonical response and four fresh draws have identical 205 parsed words and identical H1-exact DER **.414255**. The retained MOSS H1 #3 final is **.344855**; its final intervals were not retained for component-by-component attribution. On reference speech alone, Gemini's H1 DER **.378412** exceeds MOSS's **.261404**, so untimed gaps do not explain the whole gap.

| Production-score component | Error seconds / 60.894 timed seconds | Share of 25.226 total error seconds | Interval evidence |
|---|---:|---:|---|
| Missed reference speech | 9.253 / .151955 DER | 36.7% | ENG_A absent 41.80–44.79 s (2.99 s), 73.80–75.40 s (1.60 s); 4.831 s miss in 30–60 s bin |
| False alarm against timed reference | 6.359 / .104429 DER | 25.2% | All in untimed gaps by scorer definition; 5.729 s within 0.5 s of a reference turn edge; 525/638 ten-ms WebRTC frames there voiced |
| Wrong speaker on timed speech | 9.613 / .157872 DER | 38.1% | Fixed mapping BOSS→Gemini spk:2, yet BOSS 24.61–27.15 s was spk:0 (2.54 s); ENG_A→spk:2 2.410 s, ENG_B→spk:0 2.040 s |

Within ±0.5 s of a **reference turn** boundary lie 4.553/9.253 s of miss, 5.729/6.359 s of false alarm, and 5.737/9.613 s of confusion. This is boundary proximity, **not a measured word-timestamp error**: the corpus has turn intervals but no independently timed word truth. Fourteen of 205 Gemini word midpoints fall outside timed reference; 82.3% of WebRTC frames in scored false-alarm zones are voiced, consistent with some missing reference coverage but not proof of who spoke. The wrong-speaker overlap occurs mainly in the first 60 s, while the last 30 s has zero confusion; this is local turn attribution, not a global label permutation. Receipt: `evidence/P53/rtfl-variance-anatomy.json` (atomic and joined error intervals; production component totals reproduce H1 final DER).

**No no-harm general change found.** Lowering cosine .65→.55 with the same A–B–A veto merges RTFL's true-same spk:0/spk:2 (cosine .5529), reducing its DER to .374685; it also merges an unclassified Shapiro pair at higher cosine .6382, worsening covered-gold DER .188852→.193443. A single threshold cannot select RTFL while excluding that pair. Grouping words *before* remapping avoids Shapiro's regression but worsens Adam .026111→.032778, complete Lex five-minute Bill .023→.027 and Javier .032→.036667, Lex Bill 30-minute .060764→.061431, and two synthetic meetings. The existing WebRTC word gate removes zero RTFL words. The group-first hypothesis is falsified; leave the accepted .65 rule unchanged. Receipt: `evidence/P53/rtfl-general-counterfactual.json`.

## Long-final stitch structural contract (before measurement)

**Structural question.** When a single diarization call cannot cover a meeting, how can a speaker absent from the seam retain the same meeting ID in the next chunk? Does production WeSpeaker evidence repair the failure of overlap-only mapping without collapsing distinct voices?

**Minimum primitives.** Each chunk has local Gemini speaker labels and word times; an audio overlap supplies same-time co-occurrence for labels present there. A production WeSpeaker centroid from continuous attributed spans ≥2 s supplies identity evidence for labels absent at the seam. A–B–A turn evidence within a chunk forbids a conflicting merge; a group of local labels is one meeting speaker. A nonoverlapping core chooses exactly one transcription of each time. Without the core, duplicated overlap words contaminate DER; without acoustic evidence, absent speakers receive new IDs; without contradiction evidence, high cosine alone can merge different voices.

**Invariants.** Every call length is ≤ its tested cap (900/600 s proxy; 1800 s product). For requested overlap O, advance core by cap−O, call `[core_start, min(core_start+cap,duration)]`, and retain word midpoints in `[core_start,next_core_start)`; adjacent calls share O seconds when enough audio remains. Overlap matching uses only same-time word interval intersection and one-to-one assignment. The policy arm then applies the frozen `.65` centroid cosine and 2 s A–B–A veto to chunk-local labels, including labels absent in overlap. No reference speaker labels choose a merge. Keep raw Gemini text/times for retained words. Compare pure overlap and overlap+policy on the same call responses.

**Assumptions/unknowns.** Seam overlap may contain only one of several speakers, or no ≥2 s clean span for a returning speaker. A chunk label may mix true speakers; cosine cannot separate the mix. Synthetic s1 meetings have timed gaps and LibriSpeech chapter changes. A 60-minute meeting with positive overlap requires at least three ≤30-minute calls; two calls cannot cover 60 minutes and share audio. Proxy results at 10/15 minutes do not establish 60-minute quality.

**Falsifier and tool decision.** The stitch rule fails if it does not materially improve complete-reference Lex Bill DER and bring output IDs near the two true speakers, if it wrongly merges synthetic voices, or if results depend on reference truth. Use public Lex30m complete reference and synthetic s1 diagnostics, shared Gemini cached call path, P61 continuous ≥2 s intervals, production ONNX WeSpeaker, and the production DER scorer. These are needed to distinguish missing seam evidence from acoustic identity; the $3 cap bounds new provider calls. Record every call's parser anomalies and actual spend, and freeze the smallest measured rule for pane 6.3 without production code edits.

**Observed failure and bounded repair hypothesis.** Lex T=600/O=60 produced DER .500611 overlap-only and .495112 overlap+policy: two seam co-occurrence matches crossed voices, then union made them irreversible. The production cosine of a correct same-voice pair across that seam is about .95, but the initial overlap union blocks it via propagated A–B–A exclusions. Test **evidence order only**, with no new threshold: apply `.65` acoustic candidate edges and the 2 s A–B–A veto first, then add positive one-to-one overlap edges only when their groups remain compatible. Falsifier: O60 remains bad, or a previously good Lex/synthetic case worsens or falsely merges. Reuse the cached Gemini chunks; do not add provider calls for this repair.

**Acoustic-first falsified; final bounded repair hypothesis.** Acoustic-first reduced Lex T600/O60 DER .495112→.180960 and removed its two detected false merges, but its 540–1080 s core itself scores .478526 DER with a best local speaker mapping; identity alone cannot reach the one-call score. It also worsened synthetic K2 O30 .160048→.278435 and O60 .146657→.240661. Test one last small guard on overlap-first: accept a seam co-occurrence edge only when its two eligible WeSpeaker centroids also meet the *existing* .65 threshold; keep overlap-only evidence if either side lacks a ≥2 s vector. Then use the original acoustic edge pass and A–B–A veto. Falsifier: any previously good complete Lex setting degrades, or synthetic false merges remain. This is a zero-send replay, with no new threshold or production edit.

### F15 — Beyond-30-minute final-pass stitch

**Verdict:** the cosine-gated overlap stitch is a **provisional implementation candidate, not qualified long-meeting quality**. It gives the correct two output IDs on all four complete-reference Lex Bill proxy settings and DER .0327/.0325 at the 15-minute cap, but a 10-minute/60-second-overlap setting remains .1810 DER after repair because its 540–1080 s *local chunk* is .4785 DER under its best independent speaker mapping. The synthetic 5-minute-cap diagnostic retains false merges and many extra IDs. There was one response per distinct chunk audio, so chunk-response variance remains unmeasured.

The 1800 s Lex Bill reference is **complete**. The current canonical one-call response scores pure/policy DER .083704/.060764 and 3/2 IDs; two separate fresh whole-call responses from F13 both scored .061542/.038603. The proxy arms below use the **same stitched call responses within each row**, production `common/score.py` time/DER scoring, no reference labels in their merge decisions. Values are DER / output ID count; false merges are truth-dominant diagnostic groups in original-policy / gated arms, not an exhaustive guarantee when a local label is mixed or unattributed.

| Clip and proxy cap/overlap (s) | Calls | Pure overlap | Overlap + frozen `.65` policy | Cosine-gated overlap + same policy | Detected false-merge groups, original/gated | Parser timing anomaly calls |
|---|---:|---:|---:|---:|---:|---:|
| Lex Bill T900/O30 | 3 | .156021 / 5 | .032659 / 2 | .032659 / 2 | 0 / 0 | 0/3 |
| Lex Bill T900/O60 | 3 | .060264 / 4 | .032548 / 2 | .032548 / 2 | 0 / 0 | 0/3 |
| Lex Bill T600/O30 | 4 | .122973 / 5 | .041491 / 2 | .041491 / 2 | 0 / 0 | 0/4 |
| Lex Bill T600/O60 | 4 | .500611 / 5 | .495112 / 2 | .180960 / 2 | 2 / 0 | 0/4 |
| Synth K2 s1 T300/O30 | 3 | .175330 / 9 | .160048 / 6 | .160048 / 6 | 1 / 1 | 0/3 |
| Synth K2 s1 T300/O60 | 3 | .184559 / 6 | .146657 / 4 | .146657 / 4 | 0 / 0 | 0/3 |
| Synth K3 s1 T300/O30 | 3 | .275907 / 13 | .207866 / 7 | .176953 / 8 | 2 / 1 | 0/3 |
| Synth K3 s1 T300/O60 | 3 | .302495 / 9 | .153352 / 5 | .153352 / 5 | 0 / 0 | 0/3 |
| Synth K4 s1 T300/O30 | 3 | .302614 / 13 | .179389 / 9 | .142515 / 10 | 2 / 1 | 0/3 |
| Synth K4 s1 T300/O60 | 3 | .177095 / 12 | .158461 / 11 | .158461 / 11 | 1 / 1 | 0/3 |
| Synth K6 s1 T300/O30 | 3 | .413470 / 23 | .314127 / 17 | .297353 / 18 | 0 / 0 | 0/3 |
| Synth K6 s1 T300/O60 | 3 | .387246 / 40 | .296778 / 25 | .202742 / 27 | 2 / 0 | 0/3 |

**Why the seam fails.** At Lex T900/O30, both seams contain only one prior label, so overlap alone assigns five IDs; acoustic evidence links the absent voice across chunks and yields two. At Lex T600/O60, overlap co-occurrence across 1080–1140 s crosses two voices and forces wrong unions. The existing `.65` cosine gate rejects those weak links, reducing .495112→.180960 DER and detected false merges 2→0. It cannot fix the wrong speaker attribution already inside one Gemini chunk. Applying acoustic edges *before* seam edges also repairs that Lex crossing, but worsens synthetic K2 DER .160048→.278435 (O30) and .146657→.240661 (O60); that order is rejected. Cosine gating has no DER regression across the 12 observed settings but still has detected synthetic false merges in K2/O30, K3/O30, K4/O30, and K4/O60. In K6/O60 it prevents two detected false merges while leaving 27 output IDs for six truth speakers.

The s1 synthetic references have untimed gaps and chapter-dependent voice shifts, so their DER is **diagnostic**; their false-merge counterexamples and output-ID excess still falsify a universal stitch claim. Overlap length is unresolved: O60 reduces some synthetic errors but T600/O60 fails the complete Lex proxy, while O30 costs less overlap and succeeds on both complete Lex O30 settings. Choose O30 as the smaller provisional production overlap; a 60-minute meeting then requires **three** ≤1800 s calls (`[0,1800]`, `[1770,3570]`, `[3540,3600]`), because two capped calls cannot both overlap and cover all 3600 s. This 30-minute-cap schedule itself has not been scored against 60-minute truth.

#### POLICY-LONG — provisional handoff to pane 6.3 (8 pseudocode lines)

```text
T=1800 s; O=30 s; for core_start=0, T-O, ... call Gemini [core_start,min(core_start+T,duration)]
retain a word only if its midpoint is in [core_start,min(core_start+T-O,duration)), except the last core ends at duration
for each chunk-local label, use P61 embedding_intervals and production WeSpeaker; centroid=unit(mean(vectors)) if eligible
exclude within-chunk label pairs in A-B-A turns (turn gap<=1.5 s, both motif gaps<=2 s)
for each adjacent seam, greedily pair labels by descending positive word-time co-occurrence, one-to-one
accept a seam pair if either centroid is absent or cosine>=.65, and no cross-group excluded pair exists
then union remaining eligible label pairs by descending cosine>=.65, subject to the same cross-group veto
emit stable meeting IDs per group; preserve the selected Gemini words' text and times
```

**Decision boundary for 6.3:** implement the stitch as a candidate if needed for the cap, but do not mark beyond-30-minute final diarization qualified. Hold a quality claim until complete long-meeting references show both acceptable DER and no false merges across more than this one real voice pair. Do not silently substitute O60 or acoustic-first: both have measured failure modes. Prototype command: `PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/window/long_final.py` (cached rerun); replay commands replace the filename with `long_final_replay.py` and `long_final_gated.py`. Numeric evidence is in `evidence/P53/longfinal-{calls,results,acoustic-first,gated-overlap}.json`; every one of 38 call slots has `{clamped:0,dropped:0}`, 30 were new billed responses, and total new spend was **$0.495240**, below the $3 cap. No private/operator audio was used.

## Long60 truth-set structural contract (before selection or calls)

**Structural question.** Does the provisional 30-minute chunk stitch preserve a real returning host voice across session boundaries, while assigning distinct guests distinct meeting IDs, on a public recording longer than one Gemini diarization call?

**Minimum primitives.** A source clip with complete timed speaker truth contributes audio and reference intervals. A deterministic concatenation schedule gives every interval one absolute offset, with short explicit silence between clips. A canonical truth identity maps Lex Fridman across sessions to one speaker and each distinct guest to its own speaker. Chunk-local Gemini labels, seam co-occurrence, production WeSpeaker centroids, and the frozen POLICY-LONG mapping produce final words. Production time scoring plus truth-attributed group diagnostics measure DER, output IDs, false merges, and Lex splits. Each primitive supplies either truth custody, global time, or identity evidence; no new model or policy threshold is needed.

**Invariants.** Use only public corpus clips whose timed references cover their whole selected duration; do not fill reference gaps by guessing. Keep source audio and references unchanged within each clip, except deterministic concatenation and speaker-name normalization. Put generated WAV under ignored `prototypes/gemini-live/.cache/long60/`; keep builder and reference under owned `window/long60/`. Reuse 1800 s / 30 s POLICY-LONG and its exact .65/2 s A-B-A rule. Score the stitched and unstitched outputs from the same chunk calls, and compare the first 1800 s to a single call. No truth identity enters Gemini or the stitch decision.

**Assumptions/unknowns.** Exact complete clip population, duplicate source intervals, total duration, and available reference speaker names require inspection. Lex voice may vary across recording sessions; whether WeSpeaker sees it as one identity is unmeasured. Silence affects boundaries and billable audio but carries no speaker truth. A constructed sequence is a stress set, not evidence of natural 60-minute meeting frequency or true conversational transitions.

**Falsifier and tool decision.** POLICY-LONG fails this qualification if it does not reduce fragmentation versus no stitch, if it merges distinct guests, or if Lex remains split across chunks; report DER and counts even on failure. Inspect `common/corpus.py` and reference coverage first; this changes clip selection. Build a deterministic WAV/reference pair and verify total timed coverage; this changes whether the set can be scored. Then call shared cached Gemini diarization for the minimum 1800 s chunks, reuse the production WeSpeaker and scorer, and record per-call anomalies and ledger spend below $3. A one-call first-chunk comparison isolates the added seam error. No production code edit is needed to answer the question.

**Source selection after coverage inspection.** Use, in order, complete `benchmark_30m:lex_bill_ackman` (1800/1800 s), `benchmark_5m:lex_keyu_jin` (300/300), `benchmark_5m:lex_javier_milei` (300/300), and `calibration:lex_adam_frank` (180/180), with 2 s silence between sources: **2586 s / 43 min 06 s**, five true speakers (Lex plus four guests). `calibration:lex_shapiro_destiny` covers only 152.5/180.97 s, so it violates complete-truth selection. The Gold 60 s Bill and Keyu files are exact slices at 105 s and 115 s of their longer files; Javier Gold is the first 60 s of its 5-minute file; Bill 5-minute is the first 300 s of Bill 30-minute. Exclude all of these duplicates. The `long60` directory/tier name is a routing label; the measured WAV duration is 43 min 06 s, not 60 min.

**Qualification measurement definition.** T1800/O30 yields two calls `[0,1800]` and `[1770,2586]`, with retained word cores `[0,1770)` and `[1770,2586]`; the first call also supplies the independent first-30-minute one-call comparator. Unstitched baseline gives each chunk-local label a unique ID; the candidate applies the frozen gated seam and global `.65` acoustic pass to those same chunk results. Score both full outputs against the same complete 2580 s timed reference with `common/score.py`. Count a material Lex split as the number of final IDs whose retained words overlap Lex reference speech by at least 2 s; print each ID's exact overlap seconds to expose the threshold. Also use F15's dominant-node diagnostic to identify merged groups containing distinct guest/host truth identities. The 2 s Lex reporting cutoff matches the existing minimum embedding span and excludes tiny boundary spill; it does not affect the stitch.

### F16 — Complete-truth 43-minute candidate qualification

**Verdict: POLICY-LONG fails this new truth set.** The full output has **4 IDs for 5 true speakers**, with a verified **Bill Ackman–Adam Frank false merge** and **3 material Lex-bearing IDs for one true Lex**. It improves the same-response, chronologically ordered no-stitch DER from **.430050 to .328437** and reduces its 9 IDs/7 Lex-bearing IDs, but neither arm qualifies speaker identity. Do not tune the frozen rule on this one constructed fixture or claim >30-minute final quality. This is one Gemini response for the new second chunk plus a cached first chunk, not a variance study.

| Complete-reference measure | No identity stitch | POLICY-LONG gated stitch | Truth |
|---|---:|---:|---:|
| Full 2586 s audio: production DER on 2580 s timed speech | .430050 | .328437 | 5 speakers |
| Output IDs | 9 | **4** | 5 |
| IDs with ≥2 s union overlap on Lex truth | 7 | **3** | 1 |
| Distinct-truth merged label groups, F15 dominant-node diagnostic | 0 | **1** (Bill + Adam) | 0 |

The **first 1800 s one-call** comparator reuses the first chunk response, **not an extra Gemini call**: chronological pure/policy DER **.413630/.391357**, output IDs **3/2**, truth **2**. The same exact source audio and 73 original Bill reference rows give historical F15 raw-word-order pure/policy DER **.083704/.060764**. Those are **not comparable**: the cached response's 5900 words contain 12 backward timestamp inversions, and `words_to_segments` merges in input order. Raw order creates 78 segments and .083704 DER; chronological order creates 101 segments and .413630 DER on the same pure words. Both full-length arms and the first-1800 s comparator here use chronological word ordering. This production-scorer/order sensitivity is a separate measurement risk for pane 6.3; no scorer was changed in this pane.

**Failure anatomy.** The 1770–1800 s seam supplies 14.2 s co-occurrence for `c0:spk:0`→`c1:spk:0`; both eligible WeSpeaker centroids are from Bill audio and have cosine **.889932**, so the accepted `.65` gate correctly accepts that local seam match. The second chunk later reuses `spk:0` for Adam: its retained words overlap about 14.3 s Bill and 116.4 s Adam truth, while `c0:spk:0` is Bill-dominant. A whole-label union therefore carries Bill's meeting ID into Adam's words. No cross-chunk label-only rule can separate that mixed chunk label without revisiting within-chunk attribution. The Lex-bearing ID count uses the **union** of each ID's word/reference intersections so overlapping Gemini words cannot count the same second twice; the main stitched Lex ID covers 682.1 s of Lex truth, with two further IDs covering 20.7 s and 4.5 s. This count diagnoses output fragmentation; tiny timing spill is excluded by the declared 2 s threshold.

| Call | Audio / parsed words | Parser offset repairs | Cache / new spend |
|---|---:|---:|---:|
| `[0,1800]` s | 1800 s / 5900 | 2 clamped, 0 dropped (2/5900 words) | cached / $0 |
| `[1770,2586]` s | 816 s / 2025 | 1 clamped, 0 dropped (1/2025 words) | new / **$0.040802** |

**Artifact custody.** Deterministic builder `window/long60/build.py` produced 16-kHz mono PCM16 `prototypes/gemini-live/.cache/long60/audio.wav` (ignored, **2586 s**) and tracked `window/long60/reference.jsonl` (**97 rows, 2580 s timed truth + 6 s explicit silence**). The exact absolute paths are in `PANE-5.3-STATUS.md` STEP 3 for the lead to register as `long60` in `common/corpus.py` for panes 6.1/6.4. The `long60` name is a routing label; this public fixture is **43 min 06 s**. Source references were complete and nonduplicate: Bill30m, Keyu5m, Javier5m, Adam3m. Shapiro's incomplete reference and duplicate Gold slices were excluded. One command to rebuild: `PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/window/long60/build.py`. Numeric receipt: `evidence/P53/long60-{calls,results}.json`; ledger `P53-long60` records the one new billed call and **$0.040802**, below the $3 cap. No private/operator audio used.

## Word-timestamp structural contract (before cache inventory or policy sweep)

**Structural question.** Are long Gemini calls returning word timestamps that disagree with their annotation order, and does turn construction need to distrust isolated offsets while preserving the intended speaker sequence? What maximum single-call length avoids an observed timestamp failure without creating worse chunk-identity error?

**Minimum primitives.** A cached call has audio duration, annotation-order words, parsed start/end, and parser clamp/drop counts. Consecutive starts expose backward jumps; duration and local neighbour times expose outliers. A turn builder maps ordered words into speaker intervals; a local timestamp repair may alter only offending times, never speaker/text/order. Complete timed references and H1-exact scoring for accept6 measure diarization error; common production scoring covers other supported clips. A chunk plan plus POLICY-LONG tests the alternate call length. These are sufficient to separate timestamp pathology from speaker-label fragmentation.

**Invariants.** Inventory every shared cached diarization call, not only favorable P53 responses, and stratify by the brief's length buckets. Preserve Gemini annotation order and all words except any explicitly measured drop rule; enforce start<=end and keep repaired times within call audio. Compare raw, sorted, and repaired turns from identical responses. Freeze a repair threshold before scoring held-out populations. Use public audio only, keep new spend < $1, and do not edit common/ or production code.

**Assumptions/unknowns.** Cache metadata may not retain audio duration or parser anomalies for every historical call; derive only from recorded request/usage when possible and mark the rest unknown. A long call may mix speakers regardless of timestamp quality; better timestamps alone may not fix its DER. Previously reported Lex30m .084 used raw annotation order and is not comparable to chronologically sorted .414; whether either matches product rendering is unmeasured until the actual turn path is checked. Synthetic s1 timed truth has gaps and chapter changes. The long60 fixture is 43m06, not 60m.

**Falsifier and tool decision.** Reject a timestamp repair if it worsens H1 accept6 final DER or complete real clips, drops speech, or leaves the long-call pathology; report negative outcome rather than tuning indefinitely. Read shared cache JSON and the production turn path to locate the failure and collect 3 concrete examples. Use a cache-only prototype sweep to select the smallest local rule, with H1-exact accept6 and complete Lex references. Only call Gemini for missing public 10-minute long60 chunks needed to compare the safe-length option; one cached-response comparison is not a stability guarantee. The length recommendation changes only if chunked DER/IDs beat the 30-minute call without a new false merge.

**Predeclared repair candidate R1 (before quality scoring).** Keep annotation order. Treat a word start as an isolated typo only if it differs by **>10 s from both adjacent starts** while those neighbours differ by ≤10 s; move it between the adjacent words and keep at most 1 s duration. Treat a ≤10-word jump-and-return by >10 s in opposite directions as one displaced island; shift its word times together between its unchanged neighbours, preserving internal spacing. Cap any remaining single-word duration >5 s to at most 1 s. Keep every word, speaker, and text; clamp repaired offsets to the call boundary. The 10 s threshold targets the observed +460.6 s five-word island and −999.9 s single-word typo while leaving the 6.2 s backchannel inversion alone. Falsifier: any accept6 H1 final DER regression, poorer complete Lex30m DER, changed word count, or persistent >5 s duration or >10 s short excursion after repair. If R1 fails, allow at most two bounded revisions as in common method; do not retune on all held-out cases.

**Call-length comparison contract (before shorter-chunk scoring).** Compare the repaired 1800 s single-call Lex30m and 1800 s long60 stitch against **900 s and 600 s calls with 30 s overlap**, using the same public complete references, frozen R1, and frozen cosine-gated POLICY-LONG. Reuse shared cached chunks; allow only the missing long60 public calls under this brief's $1 cap. Preserve each chunk's annotation order in its retained core and concatenate cores in start order; do not globally sort words. Score raw and R1 variants from the same call responses, output ID count, dominant-truth false merges, and Lex IDs with ≥2 s union support. A shorter maximum is supported only if it lowers DER without creating a false merge or worse speaker fragmentation on **both** clips. If no tested cap meets that, report no qualified safe maximum rather than choosing by a single rate table.

**One bounded midpoint after the 600/900/1800 measurements.** The 900 s cap beat 1800 s on both complete clips and avoided long60's Bill–Adam false merge, but 1200–1799 s is unmeasured. Run exactly **1200 s / 30 s overlap** on the same two clips and frozen R1/POLICY-LONG. If it retains no false merge and no worse DER/fragmentation, recommend 1200 s as the largest supported cap; otherwise retain 900 s. This is a cap boundary check, not policy retuning, and the $1 spend guard still applies.

**R1 falsifier in cache inventory; bounded R2 before replay.** R1 fixed the six Lex30m target words, but two other public 1800 s cached calls retain >10 s backward jumps. One contains a 1000 s single-word start typo with an implausible 1000 s duration adjacent to a separate four-word shifted island; R1's island-first pass wrongly shifts the legitimate word between them. Another has a **20-word** −1000 s island, beyond R1's 10-word bound. R2 changes only evidence order and island bound: repair isolated/duration-implausible words first, requiring both neighbours to have plausible ≤5 s duration before trusting their starts; then shift jump-return islands of ≤30 words. The 30-word bound covers the observed 20-word block while remaining local. Same >10 s threshold, same word/order/speaker/text invariants. Falsifier: residual >10 s jump-return islands in these calls, any accept6 DER increase or complete Lex30m DER regression, or worse 900 s/1200 s/1800 s chunk verdicts. No new provider calls for this replay.

### F17 — Word offsets, turn construction, and final-call cap

**Verdict.** Gemini word offset corruption is **rare per word but consequential for long-call turns**. A local R2 repair preserves annotation order and fixes the measured gross errors without dropping a word; it passes the H1-exact accept6 no-harm check and improves complete Lex Bill 30-minute final-policy DER **.060764→.038491**. Chronological sorting alone scores **.391357** there. For meetings longer than one call, **900 s / 15 min with 30 s overlap is the largest favorable cap tested** on both complete real fixtures; it is a candidate, not a universal safety guarantee. The 1200 s and 1800 s alternatives fail the predeclared DER/identity comparison.

**Shared-cache snapshot.** All **3,571** available `gemini-3.5-transcribe` response JSON files at the final scan were re-parsed with the current clamp/drop fix: **650,207 returned words**, lengths 2–1800 s. Each file is an audio/config cache key; many are overlapping or repeated-source clips, not independent meetings. A backward event means adjacent annotation-order starts fall by >0.5 s. An outlier call has a parsed word duration >5 s or a start >5 s from both adjacent starts while those neighbours are within 5 s of each other. Counts are **affected calls / calls in bucket**, followed by parser clamped/dropped **word totals** in parentheses. No populated bucket is anomaly-free; 1800 s is especially poorly supported by only five calls. Zero 2586 s calls exist because diarization is capped at 1800 s.

| Call length (s) | Calls / parsed words | Backward calls | Outlier calls | Parser clamped calls (words) | Parser dropped calls (words) |
|---|---:|---:|---:|---:|---:|
| ≤30 | 2,234 / 106,750 | 50/2,234 | 12/2,234 | 129/2,234 (144) | 7/2,234 (4,489) |
| (30,60] | 412 / 70,161 | 61/412 | 6/412 | 12/412 (12) | 1/412 (1) |
| (60,120] | 600 / 200,686 | 90/600 | 9/600 | 14/600 (14) | 2/600 (2) |
| (120,300] | 281 / 160,974 | 98/281 | 12/281 | 6/281 (6) | 1/281 (1) |
| (300,600] | 13 / 20,814 | 5/13 | 1/13 | 1/13 (1) | 0/13 (0) |
| (600,1200] | 26 / 64,101 | 13/26 | 6/26 | 2/26 (2) | 1/26 (1) |
| (1200,1800] | 5 / 26,721 | 4/5 | 2/5 | 2/5 (5) | 0/5 (0) |
| (1800,2586] | 0 / 0 | 0/0 | 0/0 | 0/0 (0) | 0/0 (0) |

The ≤30 s dropped-word total is dominated by **one 30 s cached response with 4,483/4,489 dropped words**; use the 7/2,234 *call* rate rather than treating those 4,489 words as independent failures. This is a provider-response pathology, not a private-audio case. R2 changed **115/650,207 words in 33/3,571 calls**, repaired all **15** observed backward jumps >10 s, and left zero parsed durations >5 s; smaller inversions remain. Parser-dropped words cannot be recovered by a turn repair. Receipts: `evidence/P53/timestamps-inventory.json` and `timestamps-repair-inventory-r2.json`.

**Why sorting fails on the same 30-minute Bill response (three public examples).** Gemini emits words in an annotation sequence; `words_to_segments` joins adjacent same-speaker words in that sequence and extends the turn end. Sorting corrupt offsets relocates words into unrelated turns:

1. Words **3551–3555**, “So, the problem is those,” jump from a preceding **1074.6 s** word to **1535.2–1537.3 s**, then word 3556 “companies” returns to **1076.5 s** (−459.8 s). The reference phrase is at ~1076 s. R2 shifts the five-word island by **−460.4 s**.
2. Word **4887**, “basics,” starts at **485.4 s** and ends at **1486.1 s** (1000.7 s duration) between words near **1485.3** and **1486.4 s**. Sorting makes it a **standalone 1000.7 s turn**, overlapping other turns by ~982.5 s; R2 moves it to **1486.35–1486.4 s**.
3. Word **2507**, “Yes,” starts at **763.1 s** after a **769.3 s** word (−6.2 s), with the next word at **770.7 s**. It may be a delayed backchannel annotation; R2 intentionally leaves sub-10-second jumps alone.

With the frozen final speaker mapping, the same 5900 words make **77 raw-order turns / 100 sorted turns / 76 repaired turns**. Turn-overlap sum is **7.7 / 982.5 / 5.6 s**. The sorted 1000.7 s ghost turn drives the huge DER rise; raw order hides its malformed start by joining it into a plausible surrounding turn. R2 repairs the time without that accidental masking. The legacy .060764 DER should not be read as proof that its word times were valid.

**Same-response final DER (speaker mapping frozen before timestamp variants).** Accept6 uses the **H1 #3 reference set and H1-exact `score_case` final surface**; Lex30m and synthetic use the common production DER scorer (polynomial exact assignment when needed). Long60's first 1800 s is byte-identical to the Lex30m one-call audio/reference and is the *same cached response*, not an independent result. Synthetic s1 references have untimed gaps, so those scores are diagnostic. R2 edits **0 words** in all six accept6 and all four s1 clips.

| Case | Raw order DER | Sorted DER | R2 repaired DER |
|---|---:|---:|---:|
| Jamie 180 s | .063795 | .063795 | .063795 |
| RTFL 90 s (partial timed truth) | .414255 | .414255 | .414255 |
| Adam 180 s | .026111 | .026111 | .026111 |
| Bill 60 s | .068333 | .068333 | .068333 |
| Keyu 60 s | .036667 | .036667 | .036667 |
| Javier 50 s | .020000 | .020000 | .020000 |
| **accept6 final DER macro** | **.104860** | **.104860** | **.104860** |
| Complete Lex Bill 1800 s / long60 first 1800 s | .060764 | **.391357** | **.038491** |
| Synthetic K2 s1 | .157602 | .157602 | .157602 |
| Synthetic K3 s1 | .131871 | .131871 | .131871 |
| Synthetic K4 s1 | .158978 | .158978 | .158978 |
| Synthetic K6 s1 | .275779 | .275779 | .275779 |

**Call-length decision, complete real references, frozen R2 + cosine-gated POLICY-LONG.** Each row reuses the same chunk responses for raw and repaired; retained cores stay in chunk/annotation order and are never globally sorted. The one-call Lex row has no seam. Material Lex IDs mean output IDs with ≥2 s *union* overlap against Lex truth; truth is one Lex. False merges use F15's dominant-node diagnostic. All shorter-cap rows had raw=repaired DER because R2 found no offending word in those calls.

| Clip / max call / overlap | Calls | Raw DER | R2 DER | Output IDs / truth | Lex IDs | False-merge groups |
|---|---:|---:|---:|---:|---:|---:|
| Lex30m / 600 / 30 s | 4 | .041435 | .041435 | 2 / 2 | 2 | 0 |
| Lex30m / **900** / 30 s | 3 | .032382 | **.032382** | 2 / 2 | 2 | 0 |
| Lex30m / 1200 / 30 s | 2 | .106865 | .106865 | 2 / 2 | 2 | 0 |
| Lex30m / 1800 s one-call | 1 | .060764 | .038491 | 2 / 2 | 2 | 0 |
| long60 / 600 / 30 s | 5 | .037281 | .037281 | 6 / 5 | 2 | 0 |
| long60 / **900** / 30 s | 3 | .034568 | **.034568** | 5 / 5 | 2 | 0 |
| long60 / 1200 / 30 s | 3 | .086692 | .086692 | 5 / 5 | 2 | 0 |
| long60 / 1800 / 30 s | 2 | .105488 | .089947 | **4 / 5** | 3 | **1 (Bill + Adam)** |

The 1200 s midpoint is worse than 900 s in both clips despite the same repaired rule; its first 1200 s Bill call also has one parser-dropped word. The 1800 s long60 call retains the within-chunk Bill/Adam label reuse from F16, which word-time repair cannot undo. Thus **15 min is the largest favorable cap among 10/15/20/30 min tested**, not a statistical or all-speaker guarantee; 16–19 and 21–29 min were unmeasured. Lex remains split across two material IDs even at the selected cap, so long-meeting speaker identity remains **unqualified**. The complete long60 reference covers 2580 s speech plus 6 s intended silence in a 2586 s fixture.

Across the **22 chunk call slots**, T600 and T900 had **0 parser repairs/drops in 15 slots**; the two T1200 first-chunk slots reuse one cached response with one dropped word each; T1800's two slots had **2 and 1 clamped** words, no drops. Six new public calls cost **$0.191412** total (ledger `P53-timestamps`, 0 provider errors), below the $1 cap. Numeric receipts: `evidence/P53/timestamps-{quality-r2,chunks-r2,chunk-calls}.json`. No operator/private audio used.

#### POLICY-TIMESTAMPS — candidate handoff to pane 6.3 (7 pseudocode lines)

```text
cap each final Gemini call at 900 s; for longer audio use O=30 s and POLICY-LONG stitch with its T=1800 overridden to 900
parse offsets with existing window clamp/drop; keep surviving words in Gemini annotation order, never sort
first fix an interior word with duration>5 s, or start >10 s from both valid-duration neighbours whose starts differ <=10 s
place that word between neighbour times, cap its new duration at 1 s, clamp to [0,call_duration]
then if opposite >10 s start jumps return within 10 s in <=30 words, shift the intervening words together between anchors
skip a proposed shift if any changed interval leaves [0,call_duration] or end<=start; keep text/speaker/order and every parsed word
run frozen .65 identity policy on repaired words, then build same-speaker turns with <=1.5 s gap; report parser/repair counts
```

**Boundary:** This cap recommendation supersedes only POLICY-LONG's `T=1800`; it keeps the measured 30 s overlap and cosine-gated identity mapping. The >10 s rule intentionally leaves smaller backward starts, and Gemini's own parser may drop impossible offsets before this rule sees them. Pane 6.3 should treat 900 s as a measured candidate cap and retain final identity qualification as open, especially on new speakers/recordings. The prototype command is `PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/window/timestamps.py {quality,chunks,repair_inventory}` (run one mode at a time; no new calls on the retained cache).
