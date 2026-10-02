# R5B-A3 — T4 frontier snapshot ($0)

Contract registered before measurements. Prototype only; product stays at A2 until every gate holds.

## Structural contract

- **Q1 question:** does a preview publication ending before a lane's solid-time frontier prove its words are visible in that lane's solid text? Time ownership and text coverage are distinct; test their equivalence.
- **P1 minimum primitives:** lane (isolation); original turn start and publication end (continuity and temporal eligibility); comparable units with original spans (exact prefix/rendering); actual solid text at a frontier (coverage authority); last eligible publication (snapshot). Removing any loses isolation, eligibility, coverage, or the cut. Pending publications reduce to one snapshot at each frontier, then clear with the turn.
- **I1 invariants:** no additional hidden fresh or omitted-from-solid units; suffix-only rendering; no cross-lane cuts; never show more than A2; unchanged output where snapshot adds nothing; degraded A2 repair preserved; active-turn state bounded; no new flicker.
- **U1 assumptions/unknowns:** publication time bounds audio heard, not accuracy/completeness of the separate rolling transcription. Commit omissions, word straddles, turn splits/merges/restated finals, origin loss through clipping, stale other-lane publications, Stop and lane replacement can invalidate the inference. Lexical absence is not automatically semantic absence; isolated spelling/script substitutions must be reported separately. Real raw stress calls are unavailable; no provider calls authorized.
- **H1 hypothesis:** the unchanged prefix of the last publication whose end is at/before the frontier is already visible in solid; taking max(snapshot cut, full-text A2 cut) hides no additional fresh units. The latter is itself a claim to attack, not an assumed proof.
- **X1 falsifier:** a temporally eligible publication contains speech absent from solid (including a dropped stretch or straddling word), or the cut hides any fresh unit on a recorded/adversarial stream. Such text disappears from both grey and solid until a later repair, if any. Reject T4 when loss cannot be bounded to zero under G3.
- **T1 tool decision:** read-only F1 captured population and original 188s Mandarin/302s English event/window streams audit coverage and rewrites; a throwaway snapshot reducer measures exact-prefix cuts. Production publication-seam controls exercise real clipping, turns, lanes, degraded/Stop behavior. A2 divergence injections test omissions/insertions explicitly as injections. Any loss rejects production work. Re-run F1/A2 product parity to verify the retained partial. Full backend suite is required before final commit. No browser, provider, private recording, port or host needed.

## Frozen gates

- **G1:** injected 22-word solid omission, 11-word preview insertion and 169-character Mandarin insertion: repeated units <= measured latency residue; state residue count.
- **G2:** all 2,749 F1 captured calls unchanged where snapshot adds nothing; never more shown than A2; English/Korean differences listed.
- **G3:** zero additional hidden fresh units on every recorded/adversarial stream; zero words hidden from grey and absent from solid by the premise audit. Repeated chorus, prefix rewrite, final/interim restatement, split/merge, >5-minute turn, many frontiers, script differences, both lanes.
- **G4:** degraded frontier, no-publication frontier, Stop mid-turn and lane replacement retain A2 behavior.
- **G5:** no additional flicker; <=1ms mean per F1 publication; state bounded by publication rate times frontier interval plus one snapshot per active turn.

One command from worktree root:
`PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/mic-speaker-echo/a3/measure.py`

Evidence: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P73/a3/`.

Measured verdict and real-run capture contract are below. Rejected candidate code is absorbed into this audit bench, never production.

## Measured verdict — REJECT T4; keep A2

**F1:** time ownership is not text coverage. The separate rolling model can omit words that the preview contained before the frontier. An exact unchanged-prefix match proves those words were in the older preview, not in the solid transcript. Hiding that prefix then removes the only visible copy. This directly meets the brief's falsifier, without any imperfect turn-key heuristic.

**F2:** through the actual `GeminiLiveRuntime.publish_update` seam, with perfect original-turn keys supplied to the prototype, all three requested divergence shapes remove the repeated prefix but hide known omissions. These are **injections**, not new provider measurements. Text is drawn from the longest recorded English/Mandarin turn; the English solid side loses units 40..61, the preview receives 11 units at position 40, and the Mandarin preview receives 169 characters at position 40. Publication/commit clocks are injected (14/15/20s), not their source recording's timings. The preview-only injected stretches represent speech omitted by the rolling model; no claim they were actually spoken in the source audio.

| Injected shape, each run on both lanes | A2 cut | T4 cut | A2 omitted units hidden | T4 omitted units hidden | Repeated residue after T4 | Allowed latency residue |
|---|---:|---:|---:|---:|---:|---:|
| Solid omits 22 words | 0 | 129 | 0 | 22 | 0 | 0 |
| Preview contains 11 words absent from solid | 0 | 140 | 0 | 11 | 0 | 0 |
| Preview contains 169 Mandarin characters absent from solid | 0 | 362 | 0 | 169 | 0 | 0 |
| Word present in pre-frontier preview but not committed yet | 129 | 130 | 0 | 1 | 0 | 0 |

The fourth injection models a boundary word (known word extent straddles 15s while the earlier preview has already written its full spelling). Its word timing is a stipulated boundary case, not acoustic qualification. Full suffix after the snapshot stays visible in all eight runs; nevertheless the omitted/boundary word disappears from both visible authorities. A2 preserves it in grey. No amount of shorter latency bounds the 22/11/169 losses to zero: all three snapshots precede the frontier by 1s and contain no later suffix.

**F3:** recorded lexical differences are reported separately from known-injection losses. Script folding is used only in the existing F1 scoring metric; candidate prefix comparison is exact existing comparable units, without script folding. Semantic equivalence of every discrepancy is **UNMEASURED**, not classified as a violation solely because spelling differs.

| Original event population | Events | Eligible publications at first covering frontier | Publications with lexical gaps | Uncovered unit-publications | Rewrites within same original start | Furthest rewrite back |
|---|---:|---:|---:|---:|---:|---:|
| Mandarin, 187.89s | 366 | 353 | 141 | 157 | 16 | 106 units |
| English, nominal 302s / loader extent 304s | 575 | 572 | 204 | 437 | 41 | 118 units |
| R5-D recorded system cell | 64 | 48 | 39 | 117 | 15 | 103 units |

Examples retained in full audit: English `becauseby` versus `because by`, NV versus MV, a preview `uh` absent from the solid occurrence; Mandarin 的/得, 八/8 and repeated 对/一切. These range from tokenization/spelling to additional occurrences; they are not all confirmed lost speech. The original audit checks every publication at its first covering frontier, not merely the selected last snapshot. Events beyond the final available commit remain ineligible rather than assumed covered.

The **complete 2,749-call F1 captured population**, both lanes: 22 files, 4,686 raw rows, 2,954 rows with a later same-lane solid extent covering their publication end; 1,737 of those have lexical gaps, totaling 3,905 uncovered unit-publications. These row clocks supply conservative eligibility, not stable original turn identities. Repeated recordings at lag 0/3.5s are distinct frozen calls, not independent audio samples. Full text/gaps, input location and later covering call are in `captured-audit.jsonl`.

## Original-stream best-case snapshot replay

Oracle original starts are recovered from the original recorded event text/end, **not** from clipped runtime row starts. The latest publication with that original start and end <= actual recorded frontier supplies the snapshot. The output cut is max(snapshot exact-prefix cut, retained A2 product cut). Inputs come from the existing captured calls. No T4 product implementation exists.

| Stream | Calls | Changed calls vs A2 | Additional units removed | Additional lexical absence | Additional fresh loss, later-solid proxy | Unmapped rows |
|---|---:|---:|---:|---:|---:|---:|
| Mandarin | 366 | 23 | 46 | 0 | 0 | 0 |
| English | 575 | 0 | 0 | 0 | 0 | 0 |

A2's text cut lies beyond the snapshot cut on 239 Mandarin rows and 437 English rows with a snapshot. Thus “take the furthest cut” does exercise the refinement; it does not prove each cut independently safe on all inputs. The existing F1 rule can already suppress a genuinely repeated phrase above its evidence floor (documented existing limitation); neither this measurement nor A2's remembered cut removes that limitation.

Largest **snapshot-only** residue by the later-solid boundary proxy is 55 Mandarin / 111 English units. This includes rewritten common-prefix failures, not solely latency between publication and frontier, and is not a verified fresh-word clock. After taking the existing text refinement, English is unchanged and Mandarin improves 23 calls. There is no justified universal “about 1s of words” residue claim. `audit_including_scoring_mean_ms` includes lexical alignment and scoring and **is not** G5's production trim timing.

## Turn, lane and lifecycle attack

- **B1 identity:** `_Core._publish` keys source turns by `turn_start`, advances it to sent-audio time on finals, and may revise it on reconnect. `GeminiHybridEngine._on_live_text` retains finals plus interim. Ordered row construction and `LaneGeminiEngine._preview_rows` clip original starts at the frontier and later overlapping rows win. Different original starts can become the same runtime start; `(lane, clipped start)` cannot implement the proposed identity.
- **B2 lane clocks:** `LaneGeminiEngine._on_lane` emits a combined publication at the max of cached lane preview ends; one lane's update may republish stale rows of the other. A real harness must capture the original lane event and its clock before composition, not infer freshness from the combined end. No cross-lane cut is used here.
- **B3 reducer controls:** 11/11 pass, full state printed to evidence: unchanged prefix, other-lane isolation, a new turn repeating the same words after the frontier, complete/partial prefix rewrite, new-key split, new-key merge, a final restated under a new interim key, frontier without a new publication, clear on Stop/replacement, and empty state after clear. These test an **ideal original-key reducer**, not product lifecycle plumbing. A split/merge/new-key restatement loses the snapshot and falls back rather than guessing continuity. Real reconnect/split/merge acoustic correctness remains UNMEASURED.
- **B4 degraded path:** no T4 change is applied after G3 rejection. Re-running the actual retained A2 seam reconstructs c5b: 27/23/23 new solid rows before/prototype/product; `right` 5/1/1; repeated paragraph openings 19/0/0; distinct `Yeah.` replies 2/2/2. Both retained text behavior and genuine nonoverlapping repeats stay unchanged. A degraded time advance cannot justify a T4 coverage inference any more than a rolling time advance can.
- **B5 state:** pending histories reduce to a snapshot when a frontier arrives; explicit clear controls pass. No optimized/bounded product state is built after G3 fails. “Publication rate ×15s” is an assumption while frontiers stall, not a measured universal bound. Production bounded state, Stop and lane replacement integration and complete candidate flicker/cost are UNMEASURED. The retained A2 rule still holds only current removed prefixes/end extents.

## Gates and retained product verification

| Gate | Decision |
|---|---|
| G1 | Injected repeated residue 0, latency residue 0, but achieved by forbidden losses. Real raw stress repair UNMEASURED. |
| G2 | Original best-case replay: English 575/575 unchanged; Mandarin 343/366 unchanged, 23 calls hide 46 additional units, no additional later-solid-proxy loss. Full candidate identity plumbing on other F1 calls UNMEASURED. Retained product unchanged on all 2,749 calls. |
| G3 | **FAIL**: eight production-seam injections lose 22/11/169/1 units per lane, absent from solid. Recorded semantic-absence count UNMEASURED; lexical counts are above. |
| G4 | Retained A2 degraded replay PASS, unchanged. Ideal no-new-publication/clear controls PASS. New T4 lifecycle integration not built. |
| G5 | No candidate certification after G3 failure. Retained A2 no re-shown proven prefix on frozen population. Existing c5b trim remains >1ms; no all-gates PASS claim. |

Regression tests first/production parity are **not applicable to T4**: the explicitly required premise attack failed before authorization to implement. No product code, production tests or old expectations change. Eight injection runs are falsification experiments, not green production regressions.

Retained product checks, with every write redirected into A3 evidence:

`PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/mic-speaker-echo/a3/verify_retained.py`

- F1 final-form/arm-C matrix 2,749/2,749; 575/575 calls without any CJK remain identical to the old rule.
- A2 prototype/product exact output parity 2,749/2,749; 2,749/2,749 unchanged vs the pre-A2 stateless cut on frozen captures.
- Actual publication stream replay: Mandarin 366, English 575, R5-D cell 64 calls; retained baseline/prototype/product exact output parity.
- Stress c2/c4/c5b/c6 re-trim outputs/metrics equal A2 prototype. The separate bounded-tail scorer reproduces the published receipts; these are **post-trim stress captures**, not raw original inputs and not a new repair measurement.
- Full backend suite: **2819 passed, 9 skipped, 2 xfailed, 37 subtests passed**, 27 warnings, 386.75s, exit 0. This verifies the retained build, not an implemented T4 rule. Local commit recorded in status.

## Real-run harness contract for lead (no run or provider call here)

For stress cells **4, 5b and 6**, on public fixtures, summaries off, capture each original lane publication and each base/rolling/degraded frontier in order. The prior stress captures cannot replay D1 because raw preview text and earlier cuts were discarded. A candidate's real run must supply:

| Field | Required meaning |
|---|---|
| Publication sequence, lane, lane instance, original turn start, final/interim kind | Reconstruct actual turns across finals/reconnect/replacement; preserve raw start before clipping. A harness-local instance counter distinguishes replacement, not a new product identity scheme. |
| Lane publication end, combined publication end, accepted audio samples, lane solid frontier, degraded flag | Distinguish original sent-audio clock from stale republished rows and a time advance from successful text coverage. |
| Raw rows/text and comparable-unit count **before** `_trim_committed_preview` | Denominator R for the publication; retain original units/spans. Source-level raw events before echo filtering separately distinguish mic filtering from preview trim. |
| Shown rows/text and comparable-unit count **after** trim | Denominator H (shown grey); record proposed snapshot and existing text cuts if evaluating T4 offline. |
| Same-lane effective solid rows/text and comparable-unit count **at that publication** | Denominator C. Retain rows/lane/times; a count alone cannot determine coverage, repetitions or omissions. Do not use the final saved transcript as contemporaneous solid. |
| Browser-observed grey/solid text, publication version and poll time | Score G1 from the actual page and align it with the server event. Record what DOM text is rendered; server text alone does not prove the screenshot's result. |
| Later solid revisions and final saved rows, same lane | Separate words hidden temporarily, words later repaired and words still absent. Later-solid alignment remains a proxy without word-time/source truth. |

Per publication/lane, emit **raw units R, shown units H, solid units C, removed units R−H, same-lane repeated shown units, fresh shown units**, and known missing/fresh units where recorded word-time or injected truth supplies them. Use the frozen stress helper's bounded-tail comparable-unit repetition metric, unchanged, beside page observations: maximum repeated units and repeated-unit seconds for c4 system, c5b system and c6 **both lanes**; report latency residue, fresh-unit loss and any re-shown removed prefix. Record poll intervals rather than assuming constant rate. Counts alone cannot establish G3; keep ordered texts/boundaries alongside numbers in public-fixture evidence.

This is a capture specification for the lead's already existing helper. No product telemetry, schema, provider call or browser run is added. A future design must preserve or prove coverage of preview-only speech before hiding it; that additional design is outside this rejected candidate.

Provider spend **$0**. No private audio, host/port, frontend, neighbouring engine edit, push/merge/PR. A2 partial remains the production result; D1 is unresolved.
