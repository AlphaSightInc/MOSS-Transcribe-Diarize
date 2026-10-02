# R5B-A7 — tail-anchor experiment (throwaway; frozen before measurement)

## Contract
1. Structural question: does locating the confirmed tail identify the old occurrence after a grey rewrite, or only an equal phrase?
2. Minimum primitives: lane (no borrowing), original-turn key/lifecycle (previous cut), comparable-unit spans (prefix cut), solid row end clock (latest speech), confirmed frontier (guard). Removing any loses isolation, continuity, text position or temporal authority.
3. Invariants: prefix-only cuts; C0 is minimum; no added fresh loss; clear state on missing/ambiguous key, finished turn, frontier retreat or shrink below remembered cut. C1 lifecycle unchanged from a6. No product/test changes.
4. Unknowns: text equality does not identify an occurrence. Grey has no word clocks. Stress sources contain published suffixes, not raw turns, original keys or finished flags. Their same-turn continuity and seeded hidden counts remain conditional. Proxy flags are not acoustic loss.
5. Falsifier: any known fresh unit hidden rejects a candidate. Additional later-solid flags fail conservative screening. Zero flags on incomplete evidence cannot qualify safety.
6. Tools: reuse a6 production capture, loaders, aggregate and truth scorer unchanged. Offline attack controls supply known occurrence clocks. Full state in own evidence. Full backend per COMMON catches any imported-base regression before local commit; failure blocks delivery until explained. No calls/audio playback/servers.

## Frozen candidates (2026-10-02, before executing a7)
C0 current product; C1 exact a6 Floor. Primary anchor source: same-lane solid row with greatest END (tie: greatest start, last input index). Alternative J: join same-lane rows sorted by START, then take tail; measured separately for A4 overlap attack.
Anchor K: shortest suffix whose deployed `_unit_weight` sum >=25 (five ordinary words, nine CJK characters, mixed scripts vary). If whole source weighs <25, no anchor. No folding in candidate.
Tolerance: reuse deployed `_repeated_head(anchor, local_grey)` unchanged, on windows of K+8 units. Search windows in increasing start order at/after that candidate's previous cut, starting only on an anchor unit. Existing evidence>=25, 60% density, gap8/8 or16/1 into>=2, lone-end rejection and end reach apply. No global grey-head agreement required. First accepted local window = hit; cut is its match end. No threshold sweep.
C3: max(C0, hit end), miss -> C0. Search starts at previous C3 cut. C4: max(C0, C1 floor, previous valid C4 cut, hit end); miss retains valid previous cut. Reset semantics above apply. Initial previous cut=0, previous frontier=0; stress remembered hidden prefixes shift search/render indices but are never reconstructed.
G: reject an anchor advance above prior cut when advance > max(0, confirmed-frontier delta seconds)*rate. Initial delta uses frontier from zero (not guessed original time). C0/C1 components remain unchanged; G cannot make a count floor rewrite-safe.
Rate per population/lane: twice the maximum comparable units/second of any nonempty positive-duration solid row in that population, from the frozen source rows (including revisions). Twofold headroom is deliberately generous; measured maximum and selected rate printed. No outcome-dependent rate tuning. This is same-lane row-average evidence, not an acoustic instantaneous bound. No lane rows -> rate0, no anchor.

## Populations, seams, scoring (unchanged a6)
Complete production capture: A4 Mandarin366, English575, R5-D64. Published-row conditional repair: c6s478, c6868. Repeat whole-history/bounded-tail unit-seconds; additional later-solid fresh proxy flags; changes where C0 already correct. Exact known fresh units on constructed controls separate. No pooling/synthetic frequency claims.
A1 diagnose c6s24-unit gap vs exact latest-END tail at collapse; count observations until later tail first hits again (report first current hit too).
A2 replay recorded repeated-line material in public stress cells2–4; controls from F1/A2 later-chorus and A4 new-turn-chorus.
A3 short/common anchors, nine/eight CJK, mixed and traditional/simplified at frontier.
A4 latest-END vs joined-START tails on all rows and known overlapping-speaker control.
A5 exact a6 head-delete15/append20 known-clock control, unchanged snippets/clock construction.

One command from root:
`PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python prototypes/gemini-live/mic-speaker-echo/a7/run.py`
Receipts: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-A7/`.

## Results
Complete: measured rejection; details below. Frozen design retained. No production design-doc edit authorized by A7; verdict captured here and external status.

## Supplementary attack registration (before executing these controls)
Core candidates/scorers remain frozen. Initial results show inherited C0 loss on some short-prefix controls, obscuring A3/A4 comparisons. Add long unmatched-prefix controls (ordinary fresh speech longer than existing eight-unit head allowance) for five common words, mixed script and stale overlapping-speaker tail. Retain the short-prefix results as inherited losses.
For each recorded cell2–4, audit the recorded `Is it you` chorus at its actual row boundaries, then construct a second occurrence using that exact public recorded row after a long fresh lead-in. Assign explicit old/new clocks only in the composition; do not assert those clocks were observed for an actual W3 event. This distinguishes recorded lyric provenance from measured service frequency. Cell4's final transcript omits the second chorus; actual fresh-chorus retention there is UNMEASURED.
These additions attack missed dimensions; no candidate, guard rate or negative result is retuned. Initial receipts retained. Corrected two mislabeled eight/nine-character controls and audio duration metadata; five core reports exactly equal before/after pure scorer caching.

## Measured verdict

**D1 retain C0; reject C1/C3/C4, including G.** Tail equality locates words, not the occurrence that became solid. C4 improves the visible duplicate but inherits C1's rewrite loss; C3 avoids that floor loss but cuts a genuine later chorus. These independent known-clock failures decide the recommendation, regardless of imperfect stress proxies. Product/test changes NONE; recommended product size0 lines.

### F1 — unchanged populations and score definitions

Complete capture uses the actual product hybrid→lane→runtime path; candidates are offline overlays on those captured inputs, not shipped implementations. Stress and cells2–4 repair already-published suffixes using overlap-conditioned keys and captured hidden-count seeds where present. A6 aggregation and boundary scorer are unchanged; pure-input caching produces exact equality of all five initial/final core reports. No negative candidate was tuned.

Repeat unit-seconds count matching same-lane runs≥5, including genuine later repetitions. Added loss is a later-solid proxy in unit-observations, not unique speech units or acoustic truth. Correct-output changes require C0 zero repeat/zero proxy loss and a verifiable boundary. Unknown boundary rows Mandarin77/English81/R5-D21/c6s107/c6 445 remain unknown.

| Population / seam | Candidate | Repeat unit-seconds | Added fresh proxy flags | Already-correct changes | Changed observations |
|---|---|---:|---:|---:|---:|
|zh-188s (366)|C0|328.00|0|0|0|
|zh-188s (366)|C1|327.00|0|0|1|
|zh-188s (366)|C3|328.00|0|0|0|
|zh-188s (366)|C3G|328.00|0|0|0|
|zh-188s (366)|C4|327.00|0|0|1|
|zh-188s (366)|C4G|327.00|0|0|1|
|en-302s (575)|C0|38.50|0|0|0|
|en-302s (575)|C1|38.50|0|0|0|
|en-302s (575)|C3|38.50|0|0|0|
|en-302s (575)|C3G|38.50|0|0|0|
|en-302s (575)|C4|38.50|0|0|0|
|en-302s (575)|C4G|38.50|0|0|0|
|r5d-cell (64)|C0|0.00|0|0|0|
|r5d-cell (64)|C1|0.00|0|0|0|
|r5d-cell (64)|C3|0.00|0|0|0|
|r5d-cell (64)|C3G|0.00|0|0|0|
|r5d-cell (64)|C4|0.00|0|0|0|
|r5d-cell (64)|C4G|0.00|0|0|0|
|c6s (478)|C0|18868.27|0|0|0|
|c6s (478)|C1|1730.19|0|0|36|
|c6s (478)|C3|9524.11|0|0|18|
|c6s (478)|C3G|18326.83|0|0|1|
|c6s (478)|C4|314.28|0|0|36|
|c6s (478)|C4G|523.23|0|0|36|
|c6 (868)|C0|73988.68|0|0|0|
|c6 (868)|C1|73988.68|0|0|0|
|c6 (868)|C3|46328.26|93|0|55|
|c6 (868)|C3G|69817.89|15|0|8|
|c6 (868)|C4|11852.33|5295|0|118|
|c6 (868)|C4G|11872.67|5295|0|115|

Bounded-tail repeat unit-seconds, C0/C1/C3/C3G/C4/C4G:

- zh-188s: 197.5/196.5/197.5/197.5/196.5/196.5.
- en-302s: 38.5/38.5/38.5/38.5/38.5/38.5.
- r5d-cell: 0.0/0.0/0.0/0.0/0.0/0.0.
- c6s: 6264.06/1637.69/3222.42/6073.98/221.78/430.73.
- c6: 34295.42/34295.42/21624.15/32375.96/6901.15/6921.49.

C6 C3/C3G flag19/3 row-observations; C4/C4G flag49 each. Some flags are provably false alignments: `good friends` is already in current solid. Keep all93/15/5295/5295 as conservative flags; do not claim those words were acoustically lost. Known controls below independently establish rejection.

### F2 — A1: the24-unit omission is not the tail

At255.10s the gap is `large david it s a it s a 30 billion market cap bank city group where you just had been before was a 200`. There are425 solid units from the next matching block to the tail. Latest-END tail is `thought it might be overvalued`; it already matches the exposed grey text at collapse. The minimal anchor is present: C3/C4 total cut822 versus C0 1/C1 801. Previous candidate cut801/frontier239.9s, so G budget0 rejects the21-unit advance. C3 then falls back to1; C4 retains801. First changed later solid tail that also matches arrives16 active publications /9.95s later, at265.05s: `shareholders i wanted to know`, with grey insertion `them` tolerated. This does not require waiting for the omitted24 words to reappear. Full state: A1-collapse.json.

Without a floor, C3 alternates between an anchor advance and fallback: the same old hit is before the previous cut on the next publication. C4 prevents that flicker by retaining a numeric position, which is exactly the unsafe ownership assumption exposed by A5. Finished flags unavailable in stress; these are conditional repair observations, not exact original runtime replay.

### F3 — A2/A3/A4/A5 controls: counts and exact hidden units

Controls use explicit old/fresh occurrence clocks. Recorded chorus compositions reuse exact public cell2–4 text; their second-occurrence clocks are constructed, not measured service/acoustic timing. Short-prefix controls show inherited C0 loss separately. Each record in constructed-controls.json contains all raw/solid inputs, state, hits, cuts, shown text and exact hidden fresh units.

| Control | C0 | C1 | C3 | C3G | C4 | C4G | C3J/C4J |
|---|---:|---:|---:|---:|---:|---:|---:|
|A5-known-clock-rewrite|0|15|0|0|15|15|0/15|
|A2-F1-A2-later-chorus|0|0|25|25|25|25|25/25|
|A2-A4-new-turn-chorus|9|9|9|9|9|9|9/9|
|A2-same-turn-missing-old-anchor|0|6|19|19|19|19|19/19|
|A3-short-common-four|0|0|0|0|0|0|0/0|
|A3-common-five|8|8|8|8|8|8|8/8|
|A3-CJK-eight|0|0|0|0|0|0|0/0|
|A3-CJK-nine|0|0|0|0|0|0|0/0|
|A3-mixed-script|15|15|15|15|15|15|15/15|
|A3-traditional-simplified|0|0|0|0|0|0|0/0|
|A4-latest-end|0|0|0|0|0|0|0/0|
|A4-stale-tail-in-fresh|13|13|13|13|13|13|13/13|
|A4-long-fresh-stale-tail|0|0|0|0|0|0|23/23|
|A3-long-prefix-common-five|0|0|20|20|20|20|20/20|
|A3-long-prefix-mixed-script|0|0|26|26|26|26|26/26|
|A2-recorded-c2-chorus-composition|0|0|29|29|29|29|29/29|
|A2-recorded-c3-chorus-composition|0|0|29|29|29|29|29/29|
|A2-recorded-c4-chorus-composition|0|0|29|29|29|29|29/29|

Exact fresh units hidden (grouped only when candidates hide the identical list; all initial/event state remains in receipts):

**A5-known-clock-rewrite**
- Event1: none.
- Event2, C1,C4,C4G,C4J: `["我", "们", "的", "这", "个", "推", "广", "方", "案", "我", "看", "过", "了", "写", "得"]`.
**A2-F1-A2-later-chorus**
- Event1, C3,C3G,C4,C4G,C3J,C4J: `["unrevised", "speech", "has", "never", "been", "committed", "and", "this", "completely", "different", "lengthy", "passage", "belongs", "to", "the", "new", "chorus", "occurrence", "today", "then", "finish", "with", "a", "chorus", "now"]`.
**A2-A4-new-turn-chorus**
- Event1, C0,C1,C3,C3G,C4,C4G,C3J,C4J: `["1", "settled", "introduction", "with", "several", "words", "before", "the", "frontier"]`.
**A2-same-turn-missing-old-anchor**
- Event1: none.
- Event2, C1: `["fresh", "unrevised", "speech", "has", "never", "been"]`.
- Event2, C3,C3G,C4,C4G,C3J,C4J: `["fresh", "unrevised", "speech", "has", "never", "been", "committed", "and", "belongs", "to", "a", "later", "occurrence", "then", "finish", "with", "a", "chorus", "now"]`.
**A3-short-common-four**
- Event1: none.
**A3-common-five**
- Event1, C0,C1,C3,C3G,C4,C4G,C3J,C4J: `["different", "fresh", "words", "yes", "we", "can", "agree", "now"]`.
**A3-CJK-eight**
- Event1: none.
**A3-CJK-nine**
- Event1: none.
**A3-mixed-script**
- Event1, C0,C1,C3,C3G,C4,C4G,C3J,C4J: `["新", "的", "語", "句", "今", "天", "gemini", "模", "型", "需", "要", "新", "的", "計", "畫"]`.
**A3-traditional-simplified**
- Event1: none.
**A4-latest-end**
- Event1: none.
**A4-stale-tail-in-fresh**
- Event1, C0,C1,C3,C3G,C4,C4G,C3J,C4J: `["new", "speech", "from", "this", "moment", "the", "overlapping", "speaker", "repeats", "this", "familiar", "chorus", "again"]`.
**A4-long-fresh-stale-tail**
- Event1, C3J,C4J: `["new", "speech", "from", "this", "moment", "belongs", "to", "a", "separate", "entirely", "fresh", "overlapping", "speaker", "occurrence", "today", "the", "overlapping", "speaker", "repeats", "this", "familiar", "chorus", "again"]`.
**A3-long-prefix-common-five**
- Event1, C3,C3G,C4,C4G,C3J,C4J: `["new", "speech", "from", "this", "moment", "belongs", "to", "a", "separate", "entirely", "fresh", "overlapping", "speaker", "occurrence", "today", "yes", "we", "can", "agree", "now"]`.
**A3-long-prefix-mixed-script**
- Event1, C3,C3G,C4,C4G,C3J,C4J: `["new", "speech", "from", "this", "moment", "belongs", "to", "a", "separate", "entirely", "fresh", "overlapping", "speaker", "occurrence", "today", "今", "天", "gemini", "模", "型", "需", "要", "新", "的", "計", "畫"]`.
**A2-recorded-c2-chorus-composition**
- Event1, C3,C3G,C4,C4G,C3J,C4J: `["new", "speech", "from", "this", "moment", "belongs", "to", "a", "separate", "entirely", "fresh", "overlapping", "speaker", "occurrence", "today", "is", "it", "you", "is", "it", "you", "is", "it", "you", "who", "got", "the", "truth", "now"]`.
**A2-recorded-c3-chorus-composition**
- Event1, C3,C3G,C4,C4G,C3J,C4J: `["new", "speech", "from", "this", "moment", "belongs", "to", "a", "separate", "entirely", "fresh", "overlapping", "speaker", "occurrence", "today", "is", "it", "you", "is", "it", "you", "is", "it", "you", "who", "got", "the", "truth", "now"]`.
**A2-recorded-c4-chorus-composition**
- Event1, C3,C3G,C4,C4G,C3J,C4J: `["new", "speech", "from", "this", "moment", "belongs", "to", "a", "separate", "entirely", "fresh", "overlapping", "speaker", "occurrence", "today", "is", "it", "you", "is", "it", "you", "is", "it", "you", "who", "got", "the", "truth", "now"]`.

Eight-character source produces no anchor/cut; nine characters qualifies and retains the four-unit fresh suffix. Traditional/simplified frontier has no candidate fold: anchor misses and residue remains. A3 long-prefix five common words hides20 fresh units; mixed script hides26. Thus evidence25 is an evidence bar, not an occurrence guard.

### F4 — recorded cells2–4, chorus attacks separate from core denominators

| Recorded attack / tape duration | Publications | C0/C1/C3/C3G/C4/C4G repeat | Added fresh proxy / already-correct changes | Chorus rows / later repeated-row pairs |
|---|---:|---|---|---|
|cell2, 95.0s|230|74.8/74.8/74.8/74.8/74.8/74.8|0/0/0/0/0/0 / 0/0/0/0/0/0|2 / 1|
|cell3, 81.0s|195|0.0/0.0/0.0/0.0/0.0/0.0|0/0/0/0/0/0 / 0/0/0/0/0/0|2 / 1|
|cell4, 81.0s|200|959.52/959.52/596.52/929.76/0.0/0.0|0/0/0/0/0/0 / 0/0/0/0/0/0|1 / 0|

Cells2/3 have two canonically recorded `Is it you?` chorus rows and one≥25-weight repeated block pair. Their nine repeated units occur after the earlier row ends. Original earlier-row suffix (`who got the truth now`) is absent in the later line, so a tail miss is expected. Candidate repair changes0 outputs on these captures. Cell4 has only one canonical chorus row: absence of the second row cannot establish fresh-chorus safety. It has58 exact-tail grey row-observations, no multiple exact-anchor hits within any one observed grey row. Full recorded snapshots are measured, but actual fresh-chorus word retention remains UNMEASURED. Separate compositions using each cell's exact earlier chorus remove29 known fresh units under C3/C4/G, vs0 C0/C1.

### D2 — latest END is necessary, insufficient

Latest-END and joined-START anchor sources differ on83 Mandarin/74 English/18 R5-D/0 c6s/60 c6 row-observations. Joined candidates produce identical aggregate core scores here, not proof the ordering is safe. Constructed overlapping speakers: row A starts0s/ends20s; row B starts10s/ends18s. Fresh speech restates B after a15-word new lead-in. Latest-END C3/C4 hide0; joined-START C3J/C4J hide23 known fresh units. Selecting latest END removes this stale-source error; it does not distinguish a later occurrence of the latest speaker's phrase.

### D3 — G is not the minimum safe guard

Frozen G uses2×the lane's measured maximum row-average units/s, generous headroom without tuning. Rates/witnesses:

- zh-188s/system: max7.500, G rate15.000; witness2872000–2878400 samples, `沒有了`.
- en-302s/system: max18666.667, G rate37333.333; witness3116800–3116806 samples, `And you're running out of money.`.
- r5d-cell/system: max6.250, G rate12.500; witness240000–355200 samples, `议。这是科技频道Computerphile 10月初上架的专访。他从头讲那次会议，也讲学术界为什么开始不愿公开自己的研究问题。`.
- c6s/system: max16000.000, G rate32000.000; witness633600–633602 samples, `Yeah, yeah.`.
- c6s/microphone: max6.250, G rate12.500; witness2934400–2947200 samples, `Can you elaborate on that?`.
- c6/system: max17600.000, G rate35200.000; witness10284800–10284810 samples, `What a what an alternate universe we'd be living in.`.
- c6/microphone: max6.250, G rate12.500; witness6454400–6467200 samples, `Can you elaborate on that?`.

English/c6s/c6 system clocks include2–3-sample word rows: rates37333.333/32000/35200 are not acoustic bounds. These rows are real reachable product data, not hypothetical edge cases. Do not silently exclude them or tune a denominator. G still rejects34/16 C3/C4 hits on c6s and89/3 on c6 because unchanged frontier gives zero advance budget. English rejects one hit in each guarded candidate without output change; Mandarin/R5-D reject0. G changes stress outputs, substantially worsening C3 recovery; it leaves A5 floor loss and later-chorus loss intact. Even the recorded-chorus compositions use their ordinary row-duration rates, and G still hides29 known fresh units.

No measured safe guard set exists for the proposed text-only rule. Latest-END selection plus lane isolation, normal state resets and the existing evidence bar are necessary hygiene; occurrence ownership remains unresolved. Recommend neither G nor unguarded anchoring for production.

## Recommendation, size, limits and verification

**Retain C0.** C3 is better than C1 on the known rewrite control, worse on the later chorus and c6 proxy screen. C4 is better on repeat residue but does not repair C1's fresh-loss invariant. Reject both; do not trade fresh speech for fewer duplicates. Hypothetical mechanical product size approximately50–100 runtime lines (tail selection/search, per-turn previous position, composition/resets; G roughly10 extra), not a safe design estimate. Actual recommended change0 lines.

UNMEASURED: original stress raw/origin/final/snapshot history; true acoustic per-unit clocks and fresh loss; physical-device behavior; future provider variance; safe occurrence evidence. No provider calls, ports, hosts, private audio, product/test edits, frontend build, push or deployment. Only a7 run.py/NOTES.md are locally added relative to099b1fde. Product tests added/changed NONE; fail-before/pass-after and product-vs-candidate implementation parity N/A.

Frozen design/negative results remain beside the absorbed shared bench. User specifically requires this prototype and local commit; no premature deletion/production absorption. COMMON full backend: **2897 passed,9 skipped,2 xfailed,37 subtests passed,27 warnings in404.59s; exit0**. Command: `MOSS_TEST_REAL_SQLITE=1 PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python -m pytest -q -p no:cacheprovider tests`. Receipt: own `full-backend.log`. One-command final measurement exited0; replay-parity.json records exact initial/final core equality. No blockers or product implementation required; lead decision is to retain C0.
