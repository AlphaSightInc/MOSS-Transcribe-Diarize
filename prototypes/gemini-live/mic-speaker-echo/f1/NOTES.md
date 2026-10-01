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

## Results

(filled after measurement)
