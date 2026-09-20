# R4-6 same-stream interruption attribution

**Verdict: SUPPORTED.** The measured failure is 3 raw decoder additions plus 10 reference/cut defects in the 29 s acceptance arm; no word disappears in lane convergence or publication. The −10 dB diagnostic adds a 24 s input / 29 s reference population mismatch.

## Denominators

| Case | System ordered WER | Microphone ordered WER | Ladder-reported total | Classes (system) |
|---|---:|---:|---:|---|
| `demo_overlap_gain_0.03` | 13/106 (2S/6D/5I) | 5/53 | n/a | {'a': 3, 'd': 10} |
| `overlap@1` | 35/106 (2S/29D/4I) | 2/53 | 142 | {'a': 2, 'd': 33} |
| `overlap@0.316` | 35/106 (2S/29D/4I) | 2/53 | 142 | {'a': 2, 'd': 33} |

The ladder also reports 86 words for `speaker-0001` and 56 for `speaker-0002`; its splitter differs from `lane_word_oracle.words`, which counts 81 system and 53 microphone words.

## Per-system-edit attribution

Reference intervals are the only supplied timing authority: one coarse Bill Ackman record `[0.0, 29.0]`; word timing is unmeasured.

| Case | Lane | # | Edit | Reference → observed | Class | Cause | Evidence |
|---|---|---:|---|---|:---:|---|---|
| `demo_overlap_gain_0.03` | `system` | 1 | omission | `and` → `∅` | d | `reference_leading_overhang` | `bill-reference-source.jsonl:1; prior-full-audio-post-stop.jsonl:1` |
| `demo_overlap_gain_0.03` | `system` | 2 | omission | `the` → `∅` | d | `reference_leading_overhang` | `bill-reference-source.jsonl:1; prior-full-audio-post-stop.jsonl:1` |
| `demo_overlap_gain_0.03` | `system` | 3 | omission | `key` → `∅` | d | `reference_leading_overhang` | `bill-reference-source.jsonl:1; prior-full-audio-post-stop.jsonl:1` |
| `demo_overlap_gain_0.03` | `system` | 4 | omission | `is` → `∅` | d | `reference_leading_overhang` | `bill-reference-source.jsonl:1; prior-full-audio-post-stop.jsonl:1` |
| `demo_overlap_gain_0.03` | `system` | 5 | addition | `∅` → `you` | a | `raw_decoder_addition` | `raw-system-0-29.json:23` |
| `demo_overlap_gain_0.03` | `system` | 6 | addition | `∅` → `know` | a | `raw_decoder_addition` | `raw-system-0-29.json:23` |
| `demo_overlap_gain_0.03` | `system` | 7 | addition | `∅` → `market` | d | `reference_lexical_or_tokenization_mismatch` | `bill-reference-source.jsonl:1; raw-system-0-29.json:23; prior-full-audio-post-stop.jsonl:4` |
| `demo_overlap_gain_0.03` | `system` | 8 | substitution | `market's` → `is` | d | `reference_lexical_or_tokenization_mismatch` | `bill-reference-source.jsonl:1; raw-system-0-29.json:23; prior-full-audio-post-stop.jsonl:4` |
| `demo_overlap_gain_0.03` | `system` | 9 | addition | `∅` → `you're` | d | `reference_lexical_or_tokenization_mismatch` | `bill-reference-source.jsonl:1; raw-system-0-29.json:23; prior-full-audio-post-stop.jsonl:4` |
| `demo_overlap_gain_0.03` | `system` | 10 | substitution | `define` → `divine` | d | `reference_lexical_or_tokenization_mismatch` | `bill-reference-source.jsonl:1; raw-system-0-29.json:23; prior-full-audio-post-stop.jsonl:4` |
| `demo_overlap_gain_0.03` | `system` | 11 | addition | `∅` → `to` | a | `raw_decoder_addition` | `raw-system-0-29.json:23` |
| `demo_overlap_gain_0.03` | `system` | 12 | omission | `the` → `∅` | d | `cut_before_reference_tail` | `raw-system-0-29.json:23; prior-full-audio-post-stop.jsonl:9` |
| `demo_overlap_gain_0.03` | `system` | 13 | omission | `book` → `∅` | d | `cut_before_reference_tail` | `raw-system-0-29.json:23; prior-full-audio-post-stop.jsonl:9` |
| `overlap@1` | `system` | 1 | omission | `and` → `∅` | d | `reference_leading_overhang` | `bill-reference-source.jsonl:1; prior-full-audio-post-stop.jsonl:1` |
| `overlap@1` | `system` | 2 | omission | `the` → `∅` | d | `reference_leading_overhang` | `bill-reference-source.jsonl:1; prior-full-audio-post-stop.jsonl:1` |
| `overlap@1` | `system` | 3 | omission | `key` → `∅` | d | `reference_leading_overhang` | `bill-reference-source.jsonl:1; prior-full-audio-post-stop.jsonl:1` |
| `overlap@1` | `system` | 4 | omission | `is` → `∅` | d | `reference_leading_overhang` | `bill-reference-source.jsonl:1; prior-full-audio-post-stop.jsonl:1` |
| `overlap@1` | `system` | 5 | addition | `∅` → `you` | a | `raw_decoder_addition` | `raw-system-0-29.json:23` |
| `overlap@1` | `system` | 6 | addition | `∅` → `know` | a | `raw_decoder_addition` | `raw-system-0-29.json:23` |
| `overlap@1` | `system` | 7 | addition | `∅` → `market` | d | `reference_lexical_or_tokenization_mismatch` | `bill-reference-source.jsonl:1; raw-system-0-29.json:23; prior-full-audio-post-stop.jsonl:4` |
| `overlap@1` | `system` | 8 | substitution | `market's` → `is` | d | `reference_lexical_or_tokenization_mismatch` | `bill-reference-source.jsonl:1; raw-system-0-29.json:23; prior-full-audio-post-stop.jsonl:4` |
| `overlap@1` | `system` | 9 | addition | `∅` → `you're` | d | `reference_lexical_or_tokenization_mismatch` | `bill-reference-source.jsonl:1; raw-system-0-29.json:23; prior-full-audio-post-stop.jsonl:4` |
| `overlap@1` | `system` | 10 | substitution | `define` → `divine` | d | `reference_lexical_or_tokenization_mismatch` | `bill-reference-source.jsonl:1; raw-system-0-29.json:23; prior-full-audio-post-stop.jsonl:4` |
| `overlap@1` | `system` | 11 | omission | `then` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 12 | omission | `you` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 13 | omission | `can` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 14 | omission | `really` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 15 | omission | `take` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 16 | omission | `advantage` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 17 | omission | `of` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 18 | omission | `the` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 19 | omission | `market` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 20 | omission | `because` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 21 | omission | `it's` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 22 | omission | `really` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 23 | omission | `here` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 24 | omission | `to` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 25 | omission | `help` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 26 | omission | `you` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 27 | omission | `and` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 28 | omission | `that's` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 29 | omission | `kind` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 30 | omission | `of` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 31 | omission | `the` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 32 | omission | `message` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 33 | omission | `of` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 34 | omission | `the` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@1` | `system` | 35 | omission | `book` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 1 | omission | `and` → `∅` | d | `reference_leading_overhang` | `bill-reference-source.jsonl:1; prior-full-audio-post-stop.jsonl:1` |
| `overlap@0.316` | `system` | 2 | omission | `the` → `∅` | d | `reference_leading_overhang` | `bill-reference-source.jsonl:1; prior-full-audio-post-stop.jsonl:1` |
| `overlap@0.316` | `system` | 3 | omission | `key` → `∅` | d | `reference_leading_overhang` | `bill-reference-source.jsonl:1; prior-full-audio-post-stop.jsonl:1` |
| `overlap@0.316` | `system` | 4 | omission | `is` → `∅` | d | `reference_leading_overhang` | `bill-reference-source.jsonl:1; prior-full-audio-post-stop.jsonl:1` |
| `overlap@0.316` | `system` | 5 | addition | `∅` → `you` | a | `raw_decoder_addition` | `raw-system-0-29.json:23` |
| `overlap@0.316` | `system` | 6 | addition | `∅` → `know` | a | `raw_decoder_addition` | `raw-system-0-29.json:23` |
| `overlap@0.316` | `system` | 7 | addition | `∅` → `market` | d | `reference_lexical_or_tokenization_mismatch` | `bill-reference-source.jsonl:1; raw-system-0-29.json:23; prior-full-audio-post-stop.jsonl:4` |
| `overlap@0.316` | `system` | 8 | substitution | `market's` → `is` | d | `reference_lexical_or_tokenization_mismatch` | `bill-reference-source.jsonl:1; raw-system-0-29.json:23; prior-full-audio-post-stop.jsonl:4` |
| `overlap@0.316` | `system` | 9 | addition | `∅` → `you're` | d | `reference_lexical_or_tokenization_mismatch` | `bill-reference-source.jsonl:1; raw-system-0-29.json:23; prior-full-audio-post-stop.jsonl:4` |
| `overlap@0.316` | `system` | 10 | substitution | `define` → `divine` | d | `reference_lexical_or_tokenization_mismatch` | `bill-reference-source.jsonl:1; raw-system-0-29.json:23; prior-full-audio-post-stop.jsonl:4` |
| `overlap@0.316` | `system` | 11 | omission | `then` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 12 | omission | `you` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 13 | omission | `can` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 14 | omission | `really` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 15 | omission | `take` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 16 | omission | `advantage` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 17 | omission | `of` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 18 | omission | `the` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 19 | omission | `market` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 20 | omission | `because` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 21 | omission | `it's` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 22 | omission | `really` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 23 | omission | `here` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 24 | omission | `to` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 25 | omission | `help` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 26 | omission | `you` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 27 | omission | `and` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 28 | omission | `that's` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 29 | omission | `kind` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 30 | omission | `of` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 31 | omission | `the` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 32 | omission | `message` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 33 | omission | `of` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 34 | omission | `the` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |
| `overlap@0.316` | `system` | 35 | omission | `book` → `∅` | d | `24s_input_vs_29s_reference` | `ladder-duration-evidence.json:5; bill-reference-source.jsonl:1` |

## Layer proof and seams

- Raw: `raw-system-0-29.json:23`; one exact production `VllmRunner` call, 464,000 samples, greedy, no retry.
- Canonical/publication: raw and retained published word streams are byte-token equal. `_transcript_document` copies canonical `segment.text` unchanged (`moss_transcribe_diarize/app/phase2_live.py:1312-1338`); terminal settlement persists that document (`:663-677`, `:748-859`).
- Reference/cut: source record is `bill-reference-source.jsonl:1`; full-audio prior output ends `the book` at 29.25 s (`prior-full-audio-post-stop.jsonl:9`), after the demo's 29.0 s cut. Both ladder meetings retain exactly 24,000 ms (`ladder-duration-evidence.json:5-18`).
- Qualification seam only: `tests/e2e/verify_demo_lanes.py:60-75` couples audio cut to the coarse reference row. No `live_transcript_convergence.py` or `live_lane_decode.py` product change is supported.
- Later falsifier: corrected reference/cut must reduce only class-(d) edits; the three class-(a) additions must remain visible. Any raw word absent from canonical or published text falsifies this diagnosis.
