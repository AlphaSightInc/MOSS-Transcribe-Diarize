# R5B-A2: long-turn frontier trim ($0)

Contract registered before candidate measurements. Throwaway logic replay; extend F1 bench.

Structural question: where does same-lane solid speech end inside a growing, untimed preview when earlier transcription differs?

Minimum primitives: comparable units (existing words/CJK characters); same-lane visible tail (comparison authority); local frontier anchor (existing fuzzy gaps/evidence 25, but whole-head agreement need not hold); witnessed prefix cut (retain only while prefix and overlapping turn support it); original string span (prefix-only removal). Each is necessary to compare, locate, retain, or render the cut. No model/storage changes.

Invariants: preserve fresh speech; suffix-only edits; isolate lanes; never force an old cut across a restarted/rewritten prefix; retain existing short coincidence/evidence floor; do not change successful baseline cells. Degraded preview commits require the same deduplication before becoming solid.

Assumptions/unknowns: no word times or stable original turn ID reach publication (lane composer clips row start to frontier); identical text can be either restated or newly spoken. Text alone cannot resolve that ambiguity. Turn continuity and unchanged prefix are evidence, not proof of word timing. True fresh text in stress snapshots needs later solid witnesses and adversarial known boundaries; unobservable cases remain UNMEASURED.

Falsifier: any additional hidden fresh unit in recorded/adversarial streams rejects a candidate, even if duplication improves. If all candidates fail G3, ship only a measured safe partial rule and report remaining gates.

Tool decisions: public captured snapshots/rows/timeline reconstruct publication at exact observed times; production publish_update seam validates rendering/commit behavior. F1 recorded trim inputs and 188s/302s streams detect regressions. Adversarial sequences distinguish repeated chorus/new turn/rewrite from echo. Timing recorded publications detects cost >1ms. Full backend suite detects integration breakage after a measured rule is implemented. No provider/browser/host necessary.

Candidates: T1 earliest qualifying local tail anchor (also test latest to falsify chorus jump), T2 previously witnessed unchanged-prefix cut during overlapping growing publications, T1+T2 composition; T3 proportional time fallback only as rejected/accepted by known fresh boundaries. Existing evidence >=25, gaps <=8/8 or <=16/1, >=60% locally, same-lane only. No new threshold without a measured margin.

Frozen gates:
- G1 c4,c6 both lanes,c5b: repeated-unit seconds and max repeated units -> approximately zero, exact residue reported.
- G2 F1 every captured cell and 188s Mandarin/302s English: repetition no worse, fresh units no lower; all changed English/Korean outputs listed/judged.
- G3 fresh units never lower (later-solid witness plus known adversarial truth); chorus earliest occurrence, restarting preview, retroactive rewrite, >5min turn, many frontiers, traditional/simplified, 0 cross-lane cuts.
- G4 c5b timeout pattern: paragraph once, microphone Right once; no repeated degraded solid commits.
- G5 unchanged-prefix re-shown units <= baseline; mean publication <=1ms; state bounded to active preview prefixes, no meeting history.

One command (from root): PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/mic-speaker-echo/a2/measure.py
Results/evidence: ~/Documents/Codex/2026-09-28/moss-gemini/evidence/P73/a2/.

## Measured decision (before production)

Choose **safe partial T2**, plus route degraded commits through the same trim. No new frontier heuristic shipped.

Exact rule: first compute today's complete-row cut, then take the maximum of that and a previously witnessed cut when lane agrees, intervals overlap (`new.start < previous.end`), new end has not moved backward, and normalized units through the prior cut are unchanged. A changed prefix, shortened extent, nonoverlapping turn, empty preview, or absent lane discards that memory. Never re-align the shortened suffix (the prototype that did so removed the fresh second 'Revo 128 was a reset' in six publications of the 302s English stream; rejected). Store only cut units and observed extent of currently published rows, not old turns. For degraded commits, allow their end to be clipped at the artificial frontier; after commit the entire input prefix has become solid, and retains the previously observed preview extent. It is not evidence for later independent speech.

Measured: retained-after-alignment candidate equals current product on all 2,749 F1 captured calls (including 302s English, 188s Mandarin); retained-before-alignment candidate differs on six English calls and is rejected. Full raw stress inputs were not captured: snapshots contain already-trimmed publication output. Re-trimming them cannot recover prior cuts. This limitation must be retained in reporting, not promoted to a full-engine repair measurement.

C5b timeout reconstruction, real publish_update seam, initial observed solid state + all 19 observed degraded advances + published previews: 27 new solid rows -> 23, microphone 'right' 5 -> 1; large growing paragraph duplicated head 19 -> 0 after first publication (prototype new system rows 222 characters then 22-33 character suffixes rather than 411-867 character full paragraphs). Genuine later repeated passages in the public audio remain. Two 'Yeah.' rows remain: distinct intervals with no overlapping witnessed preview extent, so not silently deduplicated.

Rejected arms: latest local anchor can swallow an intervening new chorus; earliest fuzzy/global matcher can select an initial match instead of the frontier, leaving large residue, and the split/progress variants have unverified fresh boundaries on recorded text. Time fraction 0.9 on one old unit + 20 fresh units cuts 18 total units and hides 17 fresh units: rejected. G1 is NOT achieved; G5 <=1ms total on c5b is NOT achieved even by baseline (1.45ms on re-trimmed captures; safe partial prototype 2.2ms from double tokenization, production must reuse spans). No unsafe alternative is justified by those failures.

Mic c6 diagnosis: receipt explicitly contains repeated real local turns at 300/862/944s and 480/880s, so entire-history text-overlap counts fresh real repetitions. Separately, at 900s the current local turn's grey head matches the 870-875s solid microphone row only locally: preview omits 'a little bit', and SequenceMatcher prefers an older longer equivalent utterance instead of the current lane tail. The same head-run/tail-placement limitation is reachable; a local-tail-only aggressive fix risks hiding those genuine repetitions. No cross-lane fix proposed.

Regression list: retain a proven head across a >16-word solid omission; retain across a >8-unit preview insertion; unchanged-prefix cuts do not flicker across many frontiers; degraded growing paragraph suffix only; degraded single-word Right once. Controls: new nonoverlap repeat; retroactively changed prefix; lane isolation; traditional/simplified units; >5-minute turn. Existing tests unchanged. All improvement tests must fail before production edit.

## Product verification (2026-10-01, $0)

One command: `PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/mic-speaker-echo/a2/product_check.py`.

Product vs prototype: exact 2,749/2,749 F1 captured outputs, also unchanged vs pre-A2 product. Production publication replay: Mandarin 188s 366 calls, English 302s 575 calls, R5-D recorded cell 64 calls; all prototype/product/baseline outputs identical. English/Korean output differences: 0. Ten recorded cells at lag 0 and 3.5s retain zero repeated unit-polls, fresh output unchanged. The long Mandarin stream retains baseline script/clock residue; not relabeled zero. State bounds verified on every call: one record per active input row, stored cut units <= current raw units; empty publication clears records. No meeting history or fixed time fallback.

| G1 stress cell/lane | Original published max / seconds >=10 | Prototype re-trim max / seconds >=10 | Product re-trim max / seconds >=10 |
|---|---:|---:|---:|
| c4 system | 64 / 24.6s | 64 / 24.6s | 64 / 24.6s |
| c5b system | 745 / 259.2s | 745 / 257.0s | 745 / 257.0s |
| c6 system | 270 / 151.0s | 270 / 151.0s | 270 / 151.0s |
| c6 microphone | 53 / 73.9s | 53 / 73.9s | 53 / 73.9s |
| c2 system / microphone | 0 / 0s; 5 / 0s | identical | identical |

This table exactly reproduces the stress receipt's **server** bounded-tail overlap metric before re-trimming (last 12 same-lane rows, last `2*max(60, 1.25*grey_units+8)` units, script-folded, runs >=5). It differs from page metrics and exploratory whole-history metrics. The latter overcount genuine repetitions, particularly c6 microphone. All prototype/product fresh-unit totals equal in this table. These inputs are already published/trimmed snapshots, NOT raw provider updates; repeated tails remain and G1 is FAIL/UNMEASURED for full service repair. The measured repair is preserving a proven prefix (five recorded-pattern regressions) and D2, not claiming this table reaches zero.

| D2 timeout reconstruction | Baseline | Prototype | Product |
|---|---:|---:|---:|
| new committed rows | 27 | 23 | 23 |
| microphone `right` | 5 | 1 | 1 |
| full growing-paragraph opening in new rows | 19 | 0 | 0 |
| distinct `Yeah.` replies | 2 | 2 | 2 |

No paragraph is committed in full twice: first new system suffix is 222 characters, subsequent suffixes 22-33 characters. Opening was already solid before timeout. Recorded provider rewrites after the fallback are not reconstructed; Stop/saved transcript unchanged by this work.

| Mean trim cost | Prototype | Product |
|---|---:|---:|
| 2,749 F1 calls, weighted | 0.251ms | 0.178ms |
| c2 | 0.259ms | 0.186ms |
| c4 | 0.239ms | 0.146ms |
| c5b | 1.955ms | 1.486ms |
| c6 | 1.033ms | 0.731ms |

Product reuses already computed spans. c5b exceeds G5's 1ms limit; the baseline also exceeds it. No new slowdown claim based on subtraction of unlike runs. Full per-cell numbers and maxima in `evidence/P73/a2/product-check.json`; cost is trim work per publication, not browser latency. Re-shown units on all frozen F1 calls: 0 before/after. Long-gap regression crosses 30 frontiers past 5 minutes, 0 re-shown proven-prefix units.

G2 unchanged: PASS. G3 additional fresh loss on recorded streams: 0; controls (new repeat, chorus, rewrite, lane, long turn) pass; complete physical/fresh-boundary guarantee on raw stress service UNMEASURED. G4 measured timeout replay: PASS. G5 state/flicker: PASS; cost: FAIL on c5b. Safe partial accepted under brief fallback; full frontier estimator remains unqualified.

Tests: five improvement regressions failed on unchanged product with assertion failures, pass prototype and product; four preservation controls pass; original 21 preview tests unchanged. Full backend result and local commit recorded in status/receipt when complete.

No provider calls, private recordings, ports, hosts, frontend edits, pushes, merges, or PRs.

Full backend suite: **2819 passed, 9 skipped, 2 xfailed, 37 subtests passed**, 27 warnings, 394.28s. Command: `MOSS_TEST_REAL_SQLITE=1 PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python -m pytest -q -p no:cacheprovider tests`. No existing test expectation changed.
