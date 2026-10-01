# R5-F1: the grey preview repeats text that is already solid, for scripts written without spaces

Throwaway prototype (logic branch) of the fix for defect F1 found by R5-D
(`../NOTES.md`, "S1 - H1a confirmed"). No product code or test is edited in this phase; the
candidate is patched in-process inside the prototype. Evidence:
`~/Documents/Codex/2026-09-28/moss-gemini/evidence/P72/f1/`. Base: `gemini/r4-ui` @ 9a1ca171 + R5-D.

This section (contract, arms, gates) was written and committed before any candidate was measured.
Only R5-D's own numbers were re-derived first (1,982 repeated system unit-polls and 2,151 fresh
per cell on `rp-short-aec40`, from its saved snapshots).

## Contract

**Structural question.** A lane's grey row is the instant-word model's (W3) text of a turn that
began before the commit frontier. The lane's solid rows are a different model's text of the same
audio up to the frontier. The two share no word clock (W3 text has no word times). In which
unit must the two texts be compared so that "the head of the preview the reader already sees
solid" is found in every script the product transcribes, and do the run thresholds that were
calibrated on English words still hold in that unit?

**Minimum primitives** (none is new; the change replaces one private tokenizer by the unit the
project already has).
- *Comparable unit* - the smallest text atom two models write the same way for the same speech.
  A word where the script marks word boundaries; a character where it does not (no boundary
  both models agree on exists inside a Chinese clause). Defined once already:
  `gemini_lane_engine._preview_units` (one per CJK/kana/Hangul character, other letter or digit
  runs whole, casefolded, number words as digits). Cannot be removed: a comparison needs an atom.
  Cannot be a whole whitespace run: that is the defect.
- *Lane tail* - the last N units the reader sees in that lane (solid rows, then preview rows
  kept so far). Exists.
- *Repeated head* - one in-order alignment anchored at the preview's head and at the tail's
  end (`_repeated_head`). Exists; its thresholds are counts of units.
- *Cut* - the position in the original string after the last repeated unit, then leading
  punctuation dropped. Exists; the punctuation set must include unspaced-script punctuation.

**Invariants.**
- INV1 repair: in any script, the grey row of a lane does not show a run of >= 5 units that
  the lane's solid text already ends with.
- INV2 identity: for text with no CJK/kana/Hangul character the units are today's tokens, so
  the output is byte-identical to today's.
- INV3 prefix only: the output text is a suffix of the input text (leading punctuation
  dropped); a row that repeats nothing comes back byte-identical; nothing is removed from the
  middle of a row.
- INV4 same lane: a row is compared only with rows of its own `source_lane`.
- INV5 stateless: a pure function of the current preview rows and the current solid rows; no
  memory between publications, so nothing can accumulate across frontiers.
- INV6 solid and saved text are never touched (the trim edits provisional rows only).

**Assumptions and unknowns.**
- A1 W3 and the rolling model write the same Han character for the same syllable often enough
  to align (R5-D: 60-75 of 93-115 preview units sit in runs >= 5). Homophones, a different
  Latin name, and simplified-vs-traditional answers break the alignment locally; how often on
  a multi-minute stream is `unmeasured` until this prototype.
- A2 the run thresholds (>= 5 matched, gaps 8/8 and 16/1, start within 8, reach within 8,
  60 %) were calibrated on 19 English streams in words. A character is roughly 0.6 of a word of
  speech (the echo rule's 5 characters = 3 words). Whether the thresholds hold in characters
  is the question; they are not assumed.
- U1 how Gemini writes Japanese and Korean (word split, spacing variance between its two
  models): `unmeasured`; no recorded stream exists. Japanese/Korean cells here are synthetic text.
- U2 unspaced scripts outside the unit rule (Thai, Lao, Khmer, Burmese): `unmeasured`, not covered.
- U3 the user's own meeting is not opened; "fixed for the user" is only as good as R5-D's
  reproduction (10 of 10 streams, same picture as the user's screenshot).

**Falsifier.** The design "same rule, unit swapped" is rejected if, on recorded streams, any of
G1-G6 below fails for the plain arm A and no single-parameter variant passes all six.

**Tool decision.**
- T1 `$0` S1 seam replay (R5-D's `s1_trim_replay.py` cases through the production
  `GeminiLiveRuntime.publish_update`, candidate patched in-process): decides G1/G2 on the five
  script cells and carries the adversarial G3/G4 cases. Needed because it is the production
  publication path with exact control of both texts.
- T2 `$0` production-engine replay of R5-D's 9 recorded cells + the silent-microphone case
  (R5-D's `replay.py` method), with every call to the trim captured (inputs) so that all arms are
  scored on identical inputs; one end-to-end candidate run per cell confirms the offline score.
  The recorded provider answer is released 3.5 s of audio after its request (measured in the
  real-time recordings: frontier 15 s published at 18.5 s), because the `$0` replay otherwise
  publishes the frontier with zero lag and under-states how long a repeat stays on screen.
- T3 `$0` function-level stream bench on the 302 s English E1 pair (recorded W3 + recorded
  rolling words, R4-C's `mic-preview-echo/sim.py` method): G2 identity, G5 baseline flicker, G6 cost.
- T4 paid, <= $0.08 planned (cap $0.10): one ~3.5 min synthetic-Mandarin W3 stream plus
  word-timed batch answers of the same audio. Needed because the longest recorded Chinese is one
  19 s turn crossed by one frontier; G5 (a turn crossed by several frontiers, real model
  variance over minutes) cannot be measured from it. A result that changes the decision:
  repeats that persist across frontiers, or re-shown units beyond the gate, mean the thresholds
  must scale for characters or the design is rejected.
- T5 `$0` sensitivity: the same streams with the minimum run 5-10 and the gap/reach limits
  scaled, plus fresh-text and repeated-head trials cut from the recorded Chinese text, to give
  every parameter a measured margin.

## Arms (fixed before measuring)

- **base** - today's `_trim_committed_preview` (9a1ca171).
- **A units** - the same function with `_PREVIEW_WORD` tokens replaced by `_preview_units`; all
  thresholds unchanged; `，。；：！？、` added to the punctuation dropped after the cut.
- **B units, Hangul whole** - A, but a Hangul run stays one unit (the `join_text` notion of
  "unspaced": Han, kana, bopomofo; Korean has spaces). Byte-identical to today for Korean by construction.
- **C weighted minimum** - A, but the minimum evidence is 25 where a word weighs 5 and a CJK
  character 3 (the echo rule's weights): 5 words or 9 characters.
- **D sweeps** - A with minimum 5..10 characters, and with gap/start/reach limits x 5/3.

Choice rule: the simplest arm that passes every gate. A is preferred; B only if A changes Korean
output for the worse; C/D only if A drops fresh units that C/D keep without re-showing solid text.

## Gates (numbers fixed before measuring)

Metric definitions. *Unit* = `_preview_units`. *Repeated* = units of a lane's grey text inside an
in-order matching block of >= 5 units with the same lane's solid text (script-folded for the
fixture characters, as R5-D's `e2e_analyze.py`). *Fresh* = grey units that are not repeated.
*Unit-poll* = one unit in one snapshot/publication. *Re-shown* = within one W3 turn, the cut
(units removed from the row's head) decreases between two consecutive publications while the
frontier did not move back and the removed head text is unchanged: units that were grey, were
removed as solid, and are grey again.

| Gate | Pass condition |
|---|---|
| G1 repair | S1 cells zh+Latin, zh, ja, mic-lane zh: grey units repeating solid = 0 (base 75/60/56/60). Each of the 9 recorded cells, the silent-microphone case and the real-Chrome run: system-lane repeated unit-polls <= 2 % of base, and seconds with >= 10 repeated units <= 0.5 s (base 12.5-16.5 s). |
| G2 no regression | S1 `en control` and `ko control`: shown text byte-identical to base. Every captured trim call whose rows hold no CJK/kana/Hangul character (9 cells x 2 lanes, silent mic, E1 302 s system and microphone): output byte-identical, 0 differing calls. Token identity on every recorded English W3 update string in P52 (units == today's tokens, same spans): 0 differing strings. Any difference is listed and judged. |
| G3 fresh kept | Per cell, fresh unit-polls >= base. Adversarial cases (genuine repetition 对对对 / yes yes yes / a repeated name; preview head equal to the committed tail by coincidence; previews of 1-6 units; digit and punctuation runs; same audio worded differently: 逼近/比进, 视频/视讯, another Latin name; simplified vs traditional): for each, the units removed are stated; a fresh unit may be removed only where the English-word equivalent is removed by today's rule under the same shape (>= 5 units identical to the tail's end). |
| G4 same lane | A microphone preview equal to the system lane's solid text, and the reverse: 0 units trimmed. |
| G5 many frontiers | On a >= 3 min Chinese stream with >= 8 frontiers: repeated units per publication do not grow with the frontier index (last third <= first third + 1 unit); re-shown units <= 1 % of removed unit-polls and not above today's rule's re-shown rate on the 302 s English stream by more than 0.5 percentage points. Both rates reported before/after. |
| G6 cost | Added time per preview publication on the longest recorded stream: mean <= 1 ms and max <= 20 ms (the echo strip already costs 0.3-0.5 ms mean, 14 ms worst; publications run <= ~4 per second per lane). |

Unexercised = UNMEASURED, never "pass".

## Results (2026-10-01; spend $0.0586 of $0.10; key scan 0 occurrences in 232 files)

**Verdict: works, with arm C.** Comparing in the lane composer's units removes the repeated grey text on
every recorded unspaced/mixed stream and changes nothing for English. The plain arm A passes G1, G2, G4,
G5 (re-show) and G6 but fails G3: with five *characters* as the minimum it removes fresh speech where the
English rule (five *words*) would not. Arm C keeps every threshold and asks for the same evidence in both
scripts, using the echo rule's existing weights (a word 5, a CJK character 3, at least 25: five words or
nine characters). C equals A on every recorded stream and passes G3. One gate is missed as written (G5
accumulation, by 0.5 unit) for a measured reason that is not accumulation: the provider answers some
rolling windows in traditional characters.

### One command each ($0; `PY=../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python`, `W=prototypes/gemini-live/mic-speaker-echo/f1`, `PYTHONDONTWRITEBYTECODE=1`)

```sh
$PY $W/s1.py              # T1: script cells + 36 adversarial cases + cross-lane, production publication seam (5 s)
$PY $W/cells.py           # T2: 9 recorded cells + silent microphone through the production engine, base/A/C; real-Chrome run (1 min cached, 15 min --force)
$PY $W/stream.py          # T3/T4: 188 s Mandarin and 302 s English streams, all arms, margins, by-frontier table (90 s)
$PY $W/sweep.py           # T5: minimum-run trials at every position of the recorded text (40 s)
$PY $W/tokens.py          # G2: units == today's tokens on every recorded English preview string
$PY $W/cost.py            # G6: time per call by preview size
$PY $W/existing_tests.py  # the product's 118 preview/lane/runtime tests with arm C patched in
$PY $W/final_check.py     # the production-form code of the design section == arm C on all 2,749 captured calls
$PY $W/build_zh.py; ../with_key.sh $PY $W/record_zh.py   # the Mandarin fixture and its (already recorded) provider answers
```

Logs of the runs reported here: `P72/f1/logs/*.txt`; machine-readable: `P72/f1/{s1,cells,stream,sweep,cost,tokens}.json`.

### Reproduction of R5-D before any change

- `s1_trim_replay.py` unpatched prints R5-D's recorded table (9 rows identical).
- My engine replay unpatched, answer lag 0, gives snapshots with the same numbers as R5-D's saved replay
  runs for all four cells R5-D kept in replay mode (1,982 repeated system unit-polls; 2,151 / 2,169 /
  2,113 fresh; 15.0 s), including the silent-microphone case.
- The parametrized copy of `_repeated_head` equals production on 3,662 real (tail, head) pairs.
- The stream bench's copy of the engine's preview bookkeeping hands the trim the same system-lane rows
  as the real engine in 63 of 64 distinct publications of a recorded cell (the one difference is the
  order of a preview and a commit inside the same 0.5 s frame).

### New recording (the only spend): a 188 s Mandarin lane

`fixtures/zh-long.wav` (macOS `say`, two voices, text written here), the production instant-word source
in real time, and one production batch request (30 s window) per 15 s tick. What it showed that the 19 s
recorded passage could not:
- instant-word turns run 25.5 / 43.5 / 50.0 / 36.5 s (7 finals in 188 s): a turn is crossed by up to 3
  commit frontiers;
- the instant-word model writes interim text with spaces between Chinese words and ASCII commas
  ("对方的 技术 团队 开了两次 视频 会议, 对方说"), and rewrites it without them when the turn ends;
- **4 of 12 rolling windows came back in traditional characters** (45-60, 135-150, 150-165, 165-180 s;
  12-21 traditional characters per window) while the preview was always simplified;
- 2 of 11 inner frontiers commit one character twice (入职。|職， and 下週三|三之前): R5-D's side-finding.

Today's rule on it: 144.5 of 188 s show at least 10 grey units that are already solid; worst 177 units.

### Gate table (candidate = arm C; A shown where it differs)

| Gate | Result | Numbers |
|---|---|---|
| G1 repair | **pass** | S1 cells: grey units repeating solid 75/60/56/60 -> 0/0/0/0 (zh+Latin, zh, ja simulated, mic-lane zh); the grey row is exactly the not-yet-solid suffix (37/33/24/33 units). 9 recorded cells + silent microphone, production engine, answer lag 3.5 s: system repeated unit-polls 2,003-2,039 -> 0 in 10 of 10; seconds with >= 10 repeated 15.0 -> 0; worst 70-71 -> 0; microphone-lane Mandarin (zhlong) 377 -> 0. Lag 0: 1,982-2,046 -> 0. Real-Chrome run: 2,749 -> 0, 15.5 s -> 0, rows with >= 5 solid units left 42 of 110 -> 0. New 188 s stream: rows with >= 5 solid units left 282 of 354 -> 0; solid units left 18,538 -> 229. |
| G2 no regression | **pass**, two judged differences | S1 `en control`, `ko control`: identical. Rows without CJK in the 10 engine captures: 820, 0 differ. English 302 s stream: 575 publications, 739 rows, 0 differ. Units == today's tokens (same spans) on 16,269 recorded strings without CJK (590,110 units): 0 differ. The product's 118 preview/lane/runtime tests pass with C patched in. Differences: see below. |
| G3 fresh kept | **pass for C; fail for A** | Fresh units shown, by the later-committed text: cells 37,283 = 37,283; the 27 (188 s stream) and 42 (Chrome) "lost" units are one unit per row, the character the commit rule had already made solid twice (side-finding), not fresh speech. Fresh-position trials on the recorded Mandarin text: A removes fresh speech at 21 of 661 positions (3.18 %, 177 units), C at 0 of 661 (3 of 673 on the instant-word model's text: an answer that repeats nine characters of the question); English today 0 of 843. Adversarial table below. |
| G4 same lane | **pass** | 20 cross-lane cases (5 script cells x 2 directions x with/without the other lane's preview): 0 units trimmed, every arm. |
| G5 many frontiers | **re-show pass; accumulation criterion missed by 0.5 unit** | 188 s, 12 frontiers, 366 publications, a 50 s turn crossed by 3 frontiers: re-shown units 0 (today's rule on 302 s English, 31 frontiers: 0). Solid units left in the first row per publication, by frontier: 0 0 0 1.0 0 0 0 0 0 3.0 4.0 0. Non-zero only after traditional-script windows; first third 0.25, last third 1.75 (gate: <= first + 1). With the prototype fold: 0 at all 12. Today's English at single frontiers: up to 5.0. |
| G6 cost | **pass** | Added per preview publication: English 302 s stream mean +154 us (135 -> 289), p99 0.52 -> 1.03 ms, max 0.54 -> 1.12 ms; Mandarin 188 s mean +175 us (63 -> 239), max 0.13 -> 0.74 ms. By size: 230-unit Mandarin turn +0.31 ms, 1,200 units +2.3 ms; 1,200 English words +1.7 ms. Gate: mean <= 1 ms, max <= 20 ms. |

G1 on the 188 s stream by R5-D's block metric reads 18,929 -> 656 repeated unit-polls and 144.5 -> 7.0 s.
All 656 sit in five blocks, each speech that genuinely repeats earlier words (the answer 预算大概还剩 after
the question; 测试的覆盖率; the closing summary's 移动端的新版本 and 第三方支付的, first said 150 s before).
That metric cannot tell a speaker's repetition from a re-shown row, which is why the later-committed
text is the measure above.

G2 differences, judged:
1. A letter whose casefold is longer than itself (German ß) before the cut: today's rule computes the cut
   on the casefolded string and slices the original, so with three ß it shows `ir fahren herum.`; the
   unit rule shows `Wir fahren herum.`. Improvement.
2. Korean is identical on the four synthetic Korean cases, not by construction: Hangul is one unit per
   syllable in `_preview_units` and weighs 3. A real repeat of three or four Korean words would now be
   trimmed (today needs five words); gaps are counted in syllables. Real Korean: `unmeasured`.

### Adversarial cases (S1 seam; units removed, of which fresh)

| Case | today | A | C |
|---|---|---|---|
| 对对对 said again (3) | 0 | 0 | 0 |
| 对 x6 said again | 0 | 6 fresh | 0 |
| yes x3 / yes x6 said again | 0 / 6 fresh | 0 / 6 fresh | 0 / 6 fresh |
| 3-character name said again / 6-character name | 0 / 0 | 0 / 6 fresh | 0 / 0 |
| "Grace Hopper" said again | 0 | 0 | 0 |
| new sentence opens with the 5 characters the solid text holds (我们的这个) | 0 | 5 fresh | 0 |
| new sentence = last 4 / 5 / 9 characters of the solid text | 0 / 0 / 0 | 0 / 5 / 9 fresh | 0 / 0 / 9 fresh |
| new sentence = last 4 / 5 English words | 0 / 5 fresh | 0 / 5 fresh | 0 / 5 fresh |
| preview of 1, 2, 4 characters (equal to the tail) | 0 | 0 | 0 |
| preview of 7 units that is all repeat | 0 (7 left) | 7 | 0 (7 left) |
| fresh short reply 好的，没问题。 | 0 | 0 | 0 |
| 30万 solid, 三十万 in the preview, then fresh | 0 (10 left) | 15, 0 fresh | 15, 0 fresh |
| repeated phone number then fresh; fresh digits after digits | 10 / 0 | 10 / 0 | 10 / 0 |
| punctuation-only preview; heavy punctuation over a repeat | 0 / 0 (24 left) | 0 / 24 | 0 / 24 |
| homophones inside the repeat (视讯/视频, 问提/问题, 逼近/比进) | 0 (23 left) | 30, 0 fresh | 30, 0 fresh |
| another Latin name for the same audio; name missing in the preview | 0 / 0 | 16 / 12, 0 fresh | 16 / 12, 0 fresh |
| solid traditional + preview simplified, and the reverse (recorded density) | 0 (17 left) | 40, 0 fresh | 40, 0 fresh |
| solid traditional, every character a variant | 0 | 0 (repeat stays) | 0 (repeat stays) |
| Korean: spacing differs; short reply; next sentence opens with 2 solid words | 31 / 0 / 0 | 31 / 0 / 6 fresh | 31 / 0 / 0 |
| Japanese kana + kanji repeat then fresh | 0 (38 left) | 38, 0 fresh | 38, 0 fresh |

Simplified vs traditional, exactly: the rule compares characters as written, so 这 and 這 differ. A variant is
a one-unit gap inside the run. At the recorded density (29-32 % of a window's characters) the run still
holds: lowest matched share 0.706 on the 188 s stream and 0.742 on the cells against the 0.6 threshold,
widest gap 6 against 8. Cost: 1-4 solid characters left at the frontier after a traditional window (the
run may not end on a lone character after a gap), 229 unit-polls in 188 s. If variants plus mis-heard
characters pass 40 % of the head, the cut fails and that row repeats as today until the next frontier.
A fold was measured with a prototype table: share 0.97, gaps <= 2, 0 units left. It is not in the design
(decision D2): the same script flip also mixes scripts in the solid text itself, which a trim-only fold
would not touch.

### Margin of every parameter (accepted cuts: 354 CJK on the cells, 332 CJK on the 188 s stream, 493 English)

| Parameter | Value | Measured | Evidence for the value |
|---|---|---|---|
| minimum evidence | 25 (word 5, CJK character 3) = 5 words or 9 characters | smallest real CJK cut matched 12 units; 0 of 686 CJK cuts were 5-8 units; 42 of 493 English cuts were 5-8 words | at every position of the recorded Mandarin text: minimum 5 -> 3.18 % false trims, 7 -> 1.66 %, 8 -> 0.76 %, 9 -> 0; a real repeat of k characters is removed at k >= 9 in 100 % of positions (k = 8: 12 %) |
| matched share | >= 0.6 | CJK min 0.706 / 0.742 (traditional windows), median 0.99 (simplified); English min 0.833 | 0.7 gives identical output; 0.8 leaves 2,597 solid units on the 188 s stream and 23,276 on the cells |
| run starts within | 8 units | max 0 (English 1) | not exercised near the limit |
| run reaches within | 8 units of the tail's end | max 5 / 4 (English 2) | not exercised beyond 5 |
| join gap, both sides | <= 8 | max 6 / 4 (English 7) | limits 5/10/5/5 ("tight" arm) leave 4,690 repeated unit-polls on the cells (a gap of 6 is needed); x 5/3 ("scaled" arm) gives identical output on every stream |
| one-sided skip | <= 16 shown, <= 1 preview, block >= 2 | not used by any CJK cut | unchanged, unmeasured for CJK |
| compared window | max(60, 1.25 x preview units + 8) units | covers every recorded head | unchanged |
| punctuation dropped after the cut | today's ` \t\r\n,.;:!?` + `，。；：！？、` | 916 trimmed rows on the recorded streams, 0 start with a mark or a space | - |

### Implementation-ready design

One rule: *a preview row loses the head that the reader already sees in its lane, compared in the lane
composer's units; a head counts as repeated only with at least as much evidence as five words.*

1. `moss_transcribe_diarize/app/gemini_live_runtime.py`
   - Move `_CJK` and `_preview_units` here from `gemini_lane_engine.py`, unchanged (the lane engine already
     imports from this module; the reverse import would be a cycle). Add
     `_unit_weight(unit) -> 3 if len(unit) == 1 and unicodedata.name(unit, "").startswith(_CJK) else 5`.
   - `_trim_committed_preview(segments, committed)`: same structure; every `_PREVIEW_WORD.findall/finditer`
     over casefolded text becomes `_preview_units(text)` (units and spans over the original string):
     `lane_units` per lane; `limit = max(60, lane_units[lane] * 5 // 4 + 8)`; tail = units of the kept
     preview rows of the lane, then of its committed rows newest first, until `limit`; `[-limit:]`;
     `cut = _repeated_head(tail, units of the row)`;
     `text = segment.text[spans[cut - 1][2]:].lstrip(" \t\r\n,.;:!?，。；：！？、")`.
     Exact body below (`make_trim()` in `trim.py` is the measured copy; `final_check.py` holds this text
     verbatim and returns arm C's output on all 2,749 captured calls, and today's output on the 575
     calls with no CJK at all).
   - `_repeated_head(tail, words)`: one line changes. `matched >= 5` becomes
     `sum(_unit_weight(u) for block in run for u in words[block.b:block.b + block.size]) >= 25`.
     Everything else (gaps 8/8 and 16/1 into a block >= 2, start <= 8, no lone last unit, share >= 0.6,
     reach 8 or whole chunk) is unchanged. For text without CJK this is the same function as today.
   - `_PREVIEW_WORD` has no other reader: `_preview_units` holds the same pattern.

```python
def _trim_committed_preview(segments, committed):
    spans_of = [_preview_units(segment.text) for segment in segments]
    lane_units: dict[str | None, int] = {}
    for segment, spans in zip(segments, spans_of):
        lane_units[segment.source_lane] = lane_units.get(segment.source_lane, 0) + len(spans)
    kept: list[tuple[GeminiSegment, list[str]]] = []
    for segment, spans in zip(segments, spans_of):
        lane = segment.source_lane
        limit = max(60, lane_units[lane] * 5 // 4 + 8)
        parts = [units for row, units in reversed(kept) if row.source_lane == lane]
        count = sum(len(part) for part in parts)
        for row in reversed(committed):
            if count >= limit:
                break
            if row.source_lane == lane:
                parts.append([unit for unit, _, _ in _preview_units(row.text)])
                count += len(parts[-1])
        tail = [unit for part in reversed(parts) for unit in part][-limit:]
        cut = _repeated_head(tail, [unit for unit, _, _ in spans])
        text = (segment.text[spans[cut - 1][2]:].lstrip(" \t\r\n,.;:!?，。；：！？、") if cut else segment.text)
        if text:
            kept.append((replace(segment, text=text), [unit for unit, _, _ in spans[cut:]]))
    return tuple(row for row, _ in kept)

# in _repeated_head, the acceptance test:
        evidence = sum(_unit_weight(unit) for block in run for unit in words[block.b:block.b + block.size])
        if (evidence >= 25 and matched >= 0.6 * end
                and (run[-1].a + run[-1].size >= len(tail) - 8 or end >= len(words) - 1)):
            return end
```
2. `moss_transcribe_diarize/app/gemini_lane_engine.py`: import `_preview_units`, `_unit_weight` from the
   runtime module; `_repeated_units` uses `_unit_weight` instead of its inline `3 if ... else 5`
   (line 67). No behaviour change in the echo strip.
3. `docs/design-gemini-live.md` (the paragraph "At the commit frontier..."): tokens -> units, "five tokens"
   -> "five words or nine CJK characters", add the measured limits below. `CONTEXT.md` if it defines the unit.
4. Frontend: no change. The browser has no preview-vs-solid text comparison
   (`frontend/src/components/TranscriptPane.tsx:124-127` swaps the server's preview rows in whole;
   `frontend/src/lib/tentative.ts:78-98` only joins; `frontend/src/lib/transcriptCards.ts:83-99` places
   them). `mergeTurnText` (`frontend/src/lib/mergeTranscript.ts:351-391`) does trim a 4-32 token overlap
   on `split(" ")`, with the same whitespace assumption, but only between rows of the same state
   (`:173-193`), never preview against solid, and Gemini live previews bypass it.

Where it sits: `gemini_live_runtime.py` lines 1290-1380 and `gemini_lane_engine.py` lines 27-43 and 67.
F2's defect sits at `gemini_lane_engine.py:427-462` and `gemini_hybrid_engine.py:39-64`, F3's at
`gemini_live_runtime.py:1138-1144` and the provider/coverage modules (R5-D); rule W edits
`gemini_long_final.py` / `gemini_final_policy.py`. No shared lines; any merge order works. The trim reads
committed rows and never writes them, so none of those changes alters its inputs' shape.

### Regression tests to add (`tests/gemini/test_gemini_preview_duplication.py`, the file's `_runtime/_commit/_preview` helpers; texts from the recordings)

| Test | Asserts |
|---|---|
| `test_preview_trims_committed_head_in_chinese` | solid = rolling text joined by `join_text` (recorded cell, 60 units); preview = the instant-word string with commas; shown == the 33-unit suffix, starts with no punctuation |
| `test_preview_trims_chinese_head_with_latin_names` | recorded zh+Latin cell: shown == `10 月初上架的专访，他从头讲那次会议，...` (37 units), "Media Lab" appears 0 times |
| `test_preview_trims_head_written_with_spaces_between_chinese_words` | recorded interim `对方的 技术 团队 开了两次 视频 会议, 对方说...` against unspaced solid text: shown == fresh suffix |
| `test_preview_trim_holds_when_committed_window_is_traditional` | recorded 45-60 s window (traditional) + simplified preview: the head is removed; at most 4 solid units remain |
| `test_chinese_turn_crossed_by_three_frontiers_never_reshows` | the recorded 50 s turn at its three frontiers (frontier 90/105/120): each shown text starts after the solid tail; units removed never decrease |
| `test_interim_restating_a_chinese_final_is_shown_once` | recorded publication at 70 s (final + interim that restates it): the restated stretch appears once |
| `test_short_chinese_repetition_is_kept` | 对 x6, a 6-character name, `我们的这个...`, a 5- and an 8-character coincidence at the tail: preview unchanged |
| `test_nine_character_repeat_is_trimmed_eight_is_not` | the boundary of the minimum, same sentence cut at 8 and 9 |
| `test_preview_is_trimmed_only_against_its_own_lane` | microphone preview equal to system solid text, and the reverse, with and without the other lane's preview: unchanged |
| `test_homophones_and_a_different_latin_name_do_not_stop_the_trim` | 视讯/视频, 问提/问题, Computerphile/Computer File inside the repeat: shown == fresh suffix |
| `test_number_words_and_digits_align_in_chinese` | solid 30万, preview 三十万: shown == fresh suffix |
| `test_cut_position_with_letters_whose_casefold_is_longer` | three ß before the cut: shown == `Wir fahren herum.` |
| `test_japanese_and_korean_heads` | the synthetic ja and ko cells: shown == their fresh suffixes (ko equal to today's) |
| `test_units_are_todays_tokens_without_cjk` (unit level) | `_preview_units` == the old tokens and spans on a table of recorded English strings (apostrophes, `x.Y` glue, digits) |
| existing 7 tests | unchanged, pass (run here with C patched in) |

### What it cannot do

1. Traditional solid text under a simplified preview (4 of 12 windows here): 1-4 solid characters stay
   at that frontier; beyond about 40 % differing characters the head is not removed at all (today's behaviour).
2. A repeated head shorter than nine characters (five words) stays until the next frontier or the
   turn's end. None occurred in 686 recorded CJK cuts; English has the same floor at five words.
3. A new turn that really repeats at least nine characters (five words) of the last visible text of its
   lane is hidden in grey until it is committed (0-0.45 % of positions in the trials; the solid text shows it).
4. Japanese, Korean: synthetic text only. Thai, Lao, Khmer, Burmese: a run without spaces is still one
   unit (the unit rule does not cover them); `unmeasured`.
5. Between a commit and the next instant-word event the old grey row stands as published; unchanged.
6. The solid text itself: mixed scripts and the character committed twice at a frontier are untouched.

### Stress matrix

| Cell | Status |
|---|---|
| Chinese + Latin names, Chinese only, microphone-lane Chinese (S1 seam) | ran |
| Japanese, Korean (S1 seam, synthetic text) | ran; real provider output not run |
| English control, 302 s English stream, 16,269 English preview strings | ran |
| 9 recorded cells + silent microphone x {lag 0, lag 3.5 s} x {base, A, C}, production engine | ran (60 runs) |
| real-Chrome run (R5-D's page snapshots, arms applied on top) | ran offline; not re-run in a browser |
| 188 s Mandarin, 12 frontiers, turns to 50 s, 4 traditional windows | ran (recorded once, $0.0586) |
| genuine repetition, coincidence at the tail, short previews, digits, punctuation, homophones, other Latin name, traditional/simplified, ß | ran (36 cases x 2 lanes) |
| cross-lane, both directions | ran (20 cases) |
| minimum 3-10, share 0.5-0.8, limits x 0.6 and x 5/3, fold | ran offline on all captures |
| cost to 1,200 units | ran |
| a meeting longer than 5 min; 60 min | not run (the rule is stateless and its window is bounded by the preview, not the meeting) |
| real human Mandarin (spontaneous, overlapping) | not run: no public recording on disk; the fixture is synthetic speech |
| Cantonese, Japanese, Korean, Thai provider output | not run |
| the product UI in a browser with the candidate | not run (no product code is changed in this phase) |
| degraded lag fallback (`GeminiBase(degraded=True)` commits preview rows) with Chinese | not run; the existing English test passes with C |

### Side-finding: one character committed twice at a window frontier

Not the trim. `GeminiHybridEngine._publish_window` (`gemini_hybrid_engine.py:466`) gives a rolling window
the words with `old < w.end_sample <= frontier`. Window A's audio stops at the frontier, so the word being
spoken is clamped to end there and A commits it; window B hears the whole word, times its end after the
frontier and commits it again (recorded: 议。14.8-14.9 in A, 14.9-15.1 in B; here 职。134.8-135.0 and
職，134.8-135.4; 2 of 11 frontiers of the 188 s stream, 2 of 2 of R5-D's samples). The trim only edits grey
rows and reads solid rows, so this change neither causes nor cures it; it shows up here as one "lost"
unit per row in the later-committed-text metric. Fix requirement: *a rolling window commits only words
that begin at or after the previous frontier (`old <= w.start_sample < frontier`)*; the pinned test
`tests/gemini/test_gemini_hybrid_engine.py:511` encodes the end rule and would change. Not prototyped.

### Decisions for the lead / user

- D1 minimum for unspaced scripts. O1 nine characters, the same evidence as five words (arm C;
  recommended: 0 false trims in 661 trials, nothing re-shown on any recorded stream). O2 five characters
  (arm A: also removes 5-8 character repeats, none of which occurred, and removes fresh speech at 3.2 % of positions).
- D2 traditional vs simplified. O1 ship without a fold (recommended: 1-4 characters left after a
  traditional window, measured; and report the provider's script flip, 4 of 12 rolling windows, as its
  own defect of the solid text). O2 add a traditional->simplified comparison table (about 2,600 pairs,
  data file, no runtime dependency): removes the residue and widens the margin 0.71 -> 0.97.
- D3 Korean. O1 one unit rule, Hangul per syllable (recommended; identical on the four synthetic cases;
  robust to spacing differences between the two models; real Korean unmeasured). O2 keep Hangul runs
  whole (arm B: byte-identical to today by construction, a second unit definition).
- D4 the frontier duplicate: separate change (above).
