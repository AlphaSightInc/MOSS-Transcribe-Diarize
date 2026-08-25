# M4 candidate 8e-2 — the seam resolution SHIPS

Iteration 31 of run `20260825-042645-70858`, campaign branch `ralph/live-convergence-0824`,
2026-08-25. **No MOSS traffic, no GPU, no service restart**: every input is a decode already on
disk (the iteration-29 batch's file arms) or a stub.

## What shipped

`resolve_terminal_overlaps` in `moss_transcribe_diarize/app/live_transcript_convergence.py`,
called from `TerminalTranscriptFinalizer._segments_of` on the decoder's LOCAL speakers and
**before** `terminal_speaker_mapping`. The rule is the arm iteration 30 selected on six
preregistered gates (`../M4-seam-overlap/`): one local speaker's overlapping decodings become
one segment over the union of their extents with their texts joined in order; two different
local speakers over one interval leave the later one whatever the earlier one does not own.
Three accounting fields (`seam_merged_segments`, `seam_dropped_segments`,
`seam_displaced_samples`) put the price on the plan §7.4 terminal events. Decision recorded as
the **2026-08-25 addendum to ADR-0005 (D9)**.

Nothing else moved: one production file, and file mode's `_stitch_segments` is untouched.

## The defect it closes

`lex_adam_frank` (180 s) is the only meeting in the gated corpus long enough for file mode to
plan two windows. Its file arm publishes `[131.19,136.29]` and `[133.95,136.62]` — one stretch
of audio decoded twice, because `_stitch_segments` keeps a segment whose *midpoint* its window
owns. The terminal pass reproduces that arm exactly, and `LiveSession._text_revision_refusal`
refuses the whole proposal `segments_out_of_order`. Iteration 29 measured the cost: the meeting
finalized `failed`, kept its rolling surface, and the M4 exit scored **11 of 14**.

## Validation

| what | command | result |
|---|---|---|
| production == the arm that was measured | `measure_seam_overlap.py --verify-production` | **IDENTICAL** on 24 inputs (12 file arms + 12 synthetic shapes), segments and counts |
| identity off the seam, on real audio | `verify_terminal_finalizer.py` | **PASS**, 9 gates; trio terminal surface still equals the paired file arm at `0.000000` on WER/DER/speaker accuracy/coverage |
| the seam, end to end through the real session | `pytest tests/test_live_terminal_finalizer.py` | 27 passed, 19 subtests; the corpus seam is refused as decoded and published once resolved |
| the whole suite | `pytest tests/ -q` | **1157 passed, 2 skipped, 411 subtests** (was 1147/2/396 — 10 new tests, 15 new subtests) |
| the tests bite | `mutate_terminal_seam.sh mutations/` | 5 mutants, each caught by the test that names its defect; controls green before and after |
| the record is still verbatim | `verify_adr_text_finalization.py` | **PASS** (D1–D7 unchanged; D9 is an addendum) |
| the selection stands | `measure_seam_overlap.py` / `--selftest` | 6 of 6 gates, `merge_overlapping` selected; 4 of 4 mutation reactions |

### The mutation sweep (`mutations/summary.txt`)

| mutant | an otherwise working resolution that… | caught by |
|---|---|---|
| M1 no resolution at all | publishes the proposal as decoded | the session test (`segments_out_of_order`) + 8 shape subtests + 5 others |
| M2 merge ignores who spoke | joins two people into one segment | the two cross-speaker tests, and nothing else |
| M3 split at an invented boundary | resolves at the overlap's midpoint | the no-invented-boundary property (`{0,140} ⊄ {0,120,160,200}`) + the cross-speaker tests |
| M4 drop the later decoding | deletes the meeting's words to become admissible | word conservation on 5 same-speaker shapes + the corpus seam + the session test |
| M5 name the speakers first | lets a stretch decoded twice vote twice | exactly one test, the one that names it |

M1 is the "does nothing" mutant and is expected to break broadly; M2 and M5 each break exactly
the tests that state their property, which is what makes those reactions evidence rather than
noise.

## What this does NOT claim

- It does not re-score M4. That is candidate 8f: a fresh paired batch on the redeployed service
  (`verify_m4_exit.py --fresh-root`), expected **12 of 14** — `G-M4-2` / `G-M4-6` / `G-M4-9`
  recover and `lex_adam_frank` fails `G-M4-3` (`.126177` vs rolling `.122411`, two words of 526)
  and `G-M4-4` (`.949153` vs `.951036`) instead. That trade is **D-M4-3**, the owner ruling
  recorded in `../M4-seam-overlap/NOTES.md`; no bound moves (PRD: gates immutable mid-run).
- It does not deploy. The running `web_cli` still serves the pre-8e-2 build; 8f restarts it.
- It does not touch the refusal rule. Admitting overlapping segments was priced and excluded by
  construction, and the DER it "wins" is a double count (ADR-0005 D9, and `../M4-seam-overlap/`).

## Files

- `production.diff` — the whole production change.
- `production-vs-selected-arm.txt` — the shipped rule against the measured arm, 24 inputs.
- `verify-terminal-finalizer.{txt,json}` — the corpus verifier on the trio, through production.
- `pytest-terminal-finalizer.txt`, `pytest-full.txt` — the test evidence.
- `mutations/` — the sweep: `summary.txt` plus every mutant's pytest output.
