# P-M4-C - the seam refusal, measured (candidate 8e, iteration 30)

**Verdict: ship `merge_overlapping`.** It is the only resolution that costs the meeting
nothing it can be shown to have lost - zero words dropped, zero seconds of segment extent
displaced, and zero movement on every extent-free axis. Its entire cost on the deployed
DER (`.053222 -> .066222`) is the removal of a **double count**, not a loss of quality.

Preregistration: `prototypes/streaming-diarization/live-convergence/PREREGISTRATION-M4-seam.md`
(fixed before any number here). Instrument: `measure_seam_overlap.py`. Record: `gates.json`,
`console.txt`, `selftest.txt`. **No production code changed this iteration; no MOSS request,
no service, no GPU** - every input is a file arm already on disk under
`evidence/live-convergence-0824/M4-e4-exit/passes`.

## What was refused, and why it is not rare-by-luck

`lex_adam_frank` (180 s) is the only meeting in the gated corpus long enough for file mode
to plan two windows. `_stitch_segments` keeps a decoded segment when its **midpoint** falls
in the window's ownership interval; window 0 owns midpoints `< 135.0` s and window 1 owns
midpoints `>= 135.0` s. Both windows decoded the audio around the seam, so:

- `[131.19, 136.29]` "…and then material was gravitationally squeezed"  (midpoint 133.74 -> window 0)
- `[133.95, 136.62]` "and then material was gravitationally squeezed out."  (midpoint 135.285 -> window 1)

survive together. They overlap by **2.34 s** and carry the same seven words twice. The
terminal pass reproduces that file arm exactly, and `LiveSession._text_revision_refusal`
answers `segments_out_of_order`. Measured over all twelve file arms of the batch: **2 of 12
overlap, both of them this case, both runs, at the identical pair.** The other ten are clean
(`console.txt`, "WHERE THE OVERLAP IS").

## What each arm costs, on the arm that overlaps

`lex_adam_frank/A`, 546 words in, identical on run B:

| arm | segs | words lost | displaced s | WER | DER | v2 recall | v2 mw-spk | v2 DER | refusal |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `admit` (reference) | 38 | 0 | 0.00 | .126177 | .053222 | .949153 | .949153 | .054079 | **segments_out_of_order** |
| `merge_overlapping` | 37 | 0 | 0.00 | .126177 | .066222 | .949153 | .949153 | .054079 | none |
| `clip_later_start` | 38 | 0 | 2.34 | .126177 | .066222 | .949153 | .949153 | .054079 | none |
| `clip_earlier_end` | 38 | 0 | 2.34 | .126177 | .066222 | .949153 | .949153 | .054079 | none |
| `drop_later` | 37 | 7 | 2.67 | .116761 | .068056 | .947269 | .947269 | .055949 | none |

`admit` is priced, never selected: it is not a finalizer policy but a change to
`_text_revision_refusal`, which every producer on the live surface is bound by and on which
ADR-0005 D4 ("one owner per interval") rests.

## Three findings

**F1 - THE DEPLOYED DER PAYS A BONUS FOR PUBLISHING THE SAME AUDIO TWICE.** The entire
`.053222 -> .066222` difference is `miss` (`.048833 -> .061833`, exactly `2.34 / 180`).
`evaluation.calculate_diarization` computes `overlapped_by_reference` by summing the overlap
of every (reference, hypothesis) pair, so 2.34 s of reference that two hypothesis segments
both claim is credited **twice** and 2.34 s of real miss disappears. Evaluator v2, which
unions hypothesis intervals before it scores, does not move at all: `der_reference_speech`
is `.054079` for `admit`, `merge_overlapping`, `clip_later_start` and `clip_earlier_end`
alike. This is the plan §3.4 extent artifact in a shape the campaign had not yet met - not
padding, duplication - and it means **the cost of resolving the seam is a metric correction,
not a quality regression.** `text_coverage` carries the same artifact (`.952260 -> .939511`).

**F2 - THREE RESOLUTIONS TIE ON EVERY SCORED AXIS, AND THE TIE-BREAK IS WHAT THE EXTENT
CLAIMS.** `merge_overlapping`, `clip_later_start` and `clip_earlier_end` produce identical
WER, DER, coverage, speaker accuracy and all four v2 axes - because all three preserve the
union `[131.19, 136.62]` and the word stream, and the scorer reads the union and the stream.
They are separated only by the preregistered second criterion, **displaced seconds**: how
much extent an arm removes from segments it keeps.

- `clip_later_start` publishes 8 words over `[136.29, 136.62]` - 0.33 s.
- `clip_earlier_end` publishes 12 words over `[131.19, 133.95]` and claims the tail was
  silent when the decoder said it was not.
- `merge_overlapping` says the words were spoken over `[131.19, 136.62]`, which is what both
  windows reported. It displaces nothing and asserts nothing the decoder did not.

`drop_later` is the only arm that changes the words, and it is the only arm that would pass
`G-M4-3` on this case (`.116761 <= .122411`) - by deleting seven of the meeting's words. It
fails `G-M4-4` anyway (`.947269 < .951036`), so it buys the campaign nothing and costs it a
deletion the audio does not support.

**F3 - THE RULE IS TOTAL, AND THE CORPUS COULD NOT HAVE SHOWN THAT.** The corpus holds one
overlapping pair: same speaker, later-ends-later. Twelve synthetic shapes cover what a seam
can produce in general - containment, identical extents, chains of three, a later segment
that ends earlier, unsorted input, and the cross-speaker cases the corpus never shows. All
four candidate arms are total on all twelve (`G-S4`), and all four leave every non-
overlapping arm byte-identical (`G-S2`, 10 of 12 arms). Where `merge_overlapping` meets two
different speakers over one interval it falls back to `clip_later_start`, because the
surface has no way to say two people spoke at once - a limitation of the contract, recorded
here rather than hidden.

## Gates (preregistered, 6 of 6 pass)

| id | gate | result |
|---|---|---|
| G-S1 | every candidate yields a proposal the **production** refusal rule accepts | PASS - 48 file arms + 48 synthetic, none refused |
| G-S2 | on a file arm with no overlap every candidate is the identity | PASS - 10 clean arms, none changed |
| G-S3 | no arm emits a boundary the input never claimed | PASS - none, all five arms |
| G-S4 | every candidate is total: sorted, advancing, non-overlapping, in-meeting | PASS - 12 shapes x 4 arms, no fault |
| G-S5 | the reference arm reproduces the batch's own recorded file-arm scores | PASS - 48 axis comparisons at 6 dp |
| G-S6 | the word-conserving candidates lose no word | PASS - `clip_earlier_end`, `clip_later_start`, `merge_overlapping` |

`--selftest`: four mutations, each caught by the gate that names its defect and by no other
(`invented boundary -> G-S3`, `touches a clean arm -> G-S2`, `loses words -> G-S6`); the one
deliberate two-gate reaction is `no resolution at all -> G-S1 + G-S4`, because the production
rule and the harness's own structural reading are both correct about it.

## Selection

Preregistered order (words lost, displaced seconds, max |Δ| vs file, simplicity):

| arm | eligible | words lost | displaced s | max abs delta vs file |
|---|---|---:|---:|---:|
| **`merge_overlapping`** | yes | 0 | 0.00 | .013000 |
| `clip_later_start` | yes | 0 | 4.68 | .013000 |
| `clip_earlier_end` | yes | 0 | 4.68 | .013000 |
| `drop_later` | yes | 14 | 5.34 | .014834 |

**Selected: `merge_overlapping`.** Its max |Δ| against the paired file arm is `.013000` on
DER, inside `G-M4-2`'s `.020`, and `0.000000` on WER, inside `G-M4-1`'s `.010`.

## D-M4-3 - what shipping this does to the M4 gate table (an owner decision)

The four M4 rows this case is currently failing, under each arm (`console.txt`):

| arm | WER | DER | G-M4-1 `<=.010` of file | G-M4-2 `<=.020` of file | G-M4-3 `<=.122411` | G-M4-4 `>=.951036` |
|---|---:|---:|---|---|---|---|
| `refuse` (today) | .122411 | - | PASS | **FAIL** | PASS | PASS |
| `merge_overlapping` | .126177 | .066222 | PASS | PASS | **FAIL** | **FAIL** |
| `drop_later` | .116761 | .068056 | PASS | PASS | PASS | **FAIL** |

Shipping the selected arm moves `lex_adam_frank` from *no terminal surface at all* to *a
terminal surface that is the paired file arm* - and moves the failures from `G-M4-2 / G-M4-6
/ G-M4-9` (three rows, one meeting that never finalizes) to `G-M4-3 / G-M4-4` (two rows, a
terminal surface `.003766` WER and `.001883` recall behind the rolling one it replaced: two
words of 526). Expected M4 score after the fix: **12 of 14**, up from 11.

This is iteration 29's D-M4-2 arithmetic on the same case and it is **unsatisfiable in both
directions** - which is why it is an owner ruling recorded here and not a moved bound (PRD:
preregistered gates are immutable mid-run). The recommendation is to take it: the milestone's
subject is terminal convergence, `G-M4-1`'s convergence bound is honoured exactly
(`0.000000`), and a meeting that cannot finalize at all is the worse of the two outcomes.

## What the ship iteration must do (next)

1. Put the rule in `TerminalTranscriptFinalizer._segments_of`, on `placed` - i.e. on the
   **local** speakers, before `terminal_speaker_mapping`. Merging is defined on the decoder's
   own speaker labels; doing it after the mapping would merge two local speakers that happen
   to map to one canonical person, which is a different rule than the one measured here.
2. **Check, do not assume, that the mapping is unaffected.** The only merge in this corpus is
   same-local-speaker, so `local_speakers` cannot change - but the merged segment's overlap
   weight against the base surface becomes the union rather than the sum, and
   `terminal_speaker_mapping` votes on those weights. A named test on this case's seam.
3. Table-driven tests from the twelve synthetic shapes, plus a regression that a
   non-overlapping proposal is returned unchanged.
4. Re-score M4 on a fresh paired batch of all five cases (`verify_m4_exit.py --fresh-root`),
   expecting 12 of 14 with `G-M4-3` / `G-M4-4` failing on `lex_adam_frank` only.
5. File-mode outputs must stay byte-identical: the fix is in a live-path module and
   `_stitch_segments` is untouched.
