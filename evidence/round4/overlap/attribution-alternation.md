# R4 alternation and microphone attribution

**Verdict: final SUPPORTED; pre-terminal UNMEASURED.** All 19 retained final edits are attributable: 12 class-(a), 7 class-(d), 0 class-(b), 0 class-(c). Round 3 retained exact pre-terminal counts but not the 27 edited word rows.

## Denominators and corrected replay

| Surface | Lane | Retained score | Classes | Corrected-reference score |
|---|---|---:|---|---:|
| Pre-terminal alternation | system | 16/106 (2S/6D/8I) | UNMEASURED: 16 rows absent | UNMEASURED |
| Pre-terminal alternation | microphone | 11/53 (1S/4D/6I) | UNMEASURED: 11 rows absent | UNMEASURED |
| Final alternation | system | 9/106 (1S/5D/3I) | a=2, b=0, c=0, d=7 | 5/102 (1S/1D/3I) |
| Final alternation | microphone | 5/53 (0S/0D/5I) | a=5, b=0, c=0, d=0 | 5/53 |
| Final overlap | microphone | 5/53 (0S/0D/5I) | a=5, b=0, c=0, d=0 | 5/53 |

The alternation-system correction removes the seven originally scored class-(d) edits, then exposes three decoder-surface edits the old reference masked (`market's` versus audible `market is`, plus terminal `the`). Together with `you know`, corrected WER is 5/102.

## Per-final-edit evidence

| Case | Lane | # | Edit | Reference -> observed | Class | Cause | Evidence line |
|---|---|---:|---|---|:---:|---|---|
| alternation | system | 1 | omission | `and` -> `empty` | d | reference_leading_overhang | bill-reference-source.jsonl:1; overlap-review second-opinion.md:7-8 |
| alternation | system | 2 | omission | `the` -> `empty` | d | reference_leading_overhang | bill-reference-source.jsonl:1; overlap-review second-opinion.md:7-8 |
| alternation | system | 3 | omission | `key` -> `empty` | d | reference_leading_overhang | bill-reference-source.jsonl:1; overlap-review second-opinion.md:7-8 |
| alternation | system | 4 | omission | `is` -> `empty` | d | reference_leading_overhang | bill-reference-source.jsonl:1; overlap-review second-opinion.md:7-8 |
| alternation | system | 5 | addition | `empty` -> `you` | a | raw_decoder_clean_reference_addition | raw-system-0-29.json:21; retained-acceptance-surfaces.json |
| alternation | system | 6 | addition | `empty` -> `know` | a | raw_decoder_clean_reference_addition | raw-system-0-29.json:21; retained-acceptance-surfaces.json |
| alternation | system | 7 | addition | `empty` -> `you're` | d | reference_omits_audible_sentence_start | overlap-review second-opinion.md:23-25 |
| alternation | system | 8 | substitution | `define` -> `divine` | d | reference_lexical_error | overlap-review second-opinion.md:26,34 |
| alternation | system | 9 | omission | `book` -> `empty` | d | cut_before_reference_tail | overlap-review second-opinion.md:28-33 |
| alternation | microphone | 1 | addition | `empty` -> `uh` | a | raw_decoder_clean_reference_addition | keyu-hf-witness.json: exact acceptance-gain witness; retained-acceptance-surfaces.json |
| alternation | microphone | 2 | addition | `empty` -> `um` | a | raw_decoder_clean_reference_addition | keyu-hf-witness.json: exact acceptance-gain witness; retained-acceptance-surfaces.json |
| alternation | microphone | 3 | addition | `empty` -> `deference` | a | raw_decoder_clean_reference_addition | keyu-hf-witness.json: exact acceptance-gain witness; retained-acceptance-surfaces.json |
| alternation | microphone | 4 | addition | `empty` -> `uh` | a | raw_decoder_clean_reference_addition | keyu-hf-witness.json: exact acceptance-gain witness; retained-acceptance-surfaces.json |
| alternation | microphone | 5 | addition | `empty` -> `uh` | a | raw_decoder_clean_reference_addition | keyu-hf-witness.json: exact acceptance-gain witness; retained-acceptance-surfaces.json |
| overlap | microphone | 1 | addition | `empty` -> `uh` | a | raw_decoder_clean_reference_addition | keyu-hf-witness.json: exact acceptance-gain witness; retained-acceptance-surfaces.json |
| overlap | microphone | 2 | addition | `empty` -> `um` | a | raw_decoder_clean_reference_addition | keyu-hf-witness.json: exact acceptance-gain witness; retained-acceptance-surfaces.json |
| overlap | microphone | 3 | addition | `empty` -> `deference` | a | raw_decoder_clean_reference_addition | keyu-hf-witness.json: exact acceptance-gain witness; retained-acceptance-surfaces.json |
| overlap | microphone | 4 | addition | `empty` -> `uh` | a | raw_decoder_clean_reference_addition | keyu-hf-witness.json: exact acceptance-gain witness; retained-acceptance-surfaces.json |
| overlap | microphone | 5 | addition | `empty` -> `uh` | a | raw_decoder_clean_reference_addition | keyu-hf-witness.json: exact acceptance-gain witness; retained-acceptance-surfaces.json |

## Evidence boundary

- Bill: independent local HF review confirms the 29 s audio begins at `To`, says `market is`, `You're`, and `divine`, and ends before `the book` (`overlap-review/evidence/round4/overlap-review/second-opinion.md:7-11`).
- Keyu: local offline HF at exact gain matches both retained final microphone word streams; the five scored additions are four fillers and repeated `deference` (`keyu-hf-witness.json`).
- Cut: `tests/e2e/verify_demo_lanes.py:60-75` uses the corrected Keyu fixture but the coarse Bill row; correction remains proposal-only.
- Pre-terminal: `738-direct.json` retained scores/operation totals only. SQLite retained terminal documents only. A local replay disagreed (15/106 and 13/53), so its text was rejected. Reproducing the historical run would exceed the 10-request cap (retained run: 59).
- Falsifier: a recovered retained pre-terminal stream permits its 27 rows to be classified and can overturn UNMEASURED; any raw word absent from final publication overturns zero class-(b)/(c).
- GPU follow-on: 0/10 requests, peak 0, retries 0. The existing campaign receipt remains 1/40.
