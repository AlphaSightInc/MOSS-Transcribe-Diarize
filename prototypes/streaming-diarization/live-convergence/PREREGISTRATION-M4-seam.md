# Preregistration - P-M4-C, the seam refusal (candidate 8e)

Fixed **before** any number below was computed. Iteration 30 of run
`20260825-042645-70858`, campaign branch `ralph/live-convergence-0824`.

## The defect this answers

Iteration 29 (`evidence/live-convergence-0824/M4-e4-exit/`) measured the M4 exit at
**11 of 14 gates**. All three failures are one refused publication on one case:

- `lex_adam_frank` (180 s) is the only meeting in the gated corpus long enough for file
  mode to plan two windows (`[0,150)` and `[120,180)`, `WindowedRunner` 150/120).
- `_stitch_segments` keeps a decoded segment when its **midpoint** falls inside the
  window's ownership interval. Window 0 owns midpoints `< 135.0`, window 1 owns
  midpoints `>= 135.0`. `[131.19,136.29]` (midpoint 133.74) and `[133.95,136.62]`
  (midpoint 135.285) therefore both survive, and they **overlap by 2.34 s** - two
  decodings of the same audio, carrying the same words twice.
- The terminal pass reproduces that file arm exactly, and
  `LiveSession._text_revision_refusal` refuses it `segments_out_of_order`
  (`segment.start_sample < previous_end`). The meeting keeps its rolling surface and
  reports `finalization_status=failed`.

File mode must not change (PRD: file-mode outputs byte-identical). So the question is what
the **terminal finalizer**, as a producer, should send instead.

## The question

**Q.** Which resolution turns a terminal proposal that overlaps at a window seam into one
the session admits, and what does each cost on the axes M4 gates?

No MOSS traffic answers this: the terminal proposal IS the paired file arm (measured at
`0.000000` on five axes, iterations 25/27/29), so every policy can be applied offline to
the 12 file arms the iteration-29 batch already produced and scored.

## Arms

Segments are `(local_speaker, start_sample, end_sample, text)`, ordered by
`(start_sample, end_sample)` with a stable tie-break on parse order.

| id | policy | rule |
|---|---|---|
| A0 | `refuse` | today: no proposal at all, the meeting keeps its rolling surface |
| A1 | `admit` | **reference point, not a candidate** - the surface holds the overlap verbatim, i.e. what file mode itself publishes |
| A2 | `clip_later_start` | the later segment's `start` advances to the running frontier; a segment left not advancing is dropped |
| A3 | `clip_earlier_end` | the earlier segment's `end` retreats to the later segment's `start`; an earlier segment that cannot be trimmed without inverting is dropped |
| A4 | `merge_overlapping` | overlapping segments of the **same local speaker** become one segment over the union of their extents with their texts joined in order; across different speakers, fall back to A2 |
| A5 | `drop_later` | the later overlapping segment is discarded whole |

A1 is scored but excluded from selection **by construction**: it is not a finalizer policy,
it is a change to `_text_revision_refusal`, which every producer on the live surface is
bound by and on which ADR-0005 D4 ("one owner per interval") rests. It is here to price the
candidates against what file mode publishes.

## Gates (pass/fail, fixed now)

| id | gate | bound |
|---|---|---|
| G-S1 | **Admissible**: for A2-A5, every file arm in the iteration-29 batch and every synthetic shape yields a proposal the **production** `LiveSession._text_revision_refusal` accepts | refusal is `None`, every case |
| G-S2 | **Identity off the seam**: on every file arm with no overlapping pair, A2-A5 return the input unchanged, text byte-identical | equality, 10 of 12 arms |
| G-S3 | **No invented boundary**: every `start`/`end` an arm emits is a member of the input's boundary set (plan §3.4 - the campaign never invents a timestamp) | set membership, every arm |
| G-S4 | **Total and sorted**: on every synthetic shape, A2-A5 emit segments that are sorted, strictly advancing, pairwise non-overlapping and inside `[0, end_sample]` | every shape, no exception raised |
| G-S5 | **Clock identity**: A1 reproduces the shipped batch's own recorded file-arm scores (`wer`, `der`, `text_coverage`, `speaker_accuracy`) | equality at 6 dp, every arm with a recorded score |
| G-S6 | **Word conservation**: A2, A3 and A4 lose zero words on every file arm in the batch | `words_out == words_in` |

A5 is expected to fail G-S6; that is its measured cost, not a bug in the harness.

## Selection rule (fixed now, before the numbers)

Among A2-A5, keep those passing G-S1..G-S4, then order by:

1. **words lost** (G-S6), ascending - a resolution that deletes the meeting's words is
   worse than one that moves a boundary;
2. **displaced seconds**, ascending - the total segment extent an arm removes from
   segments it keeps. This is plan §3.4's concern stated as a quantity: a segment whose
   extent no longer covers the audio its words came from is a claim the audio does not
   support;
3. **max |Δ| against the paired file arm**, ascending, over `{wer, der, v2 content_recall,
   v2 matched_word_speaker_accuracy}`;
4. **simplicity**, fewest branches in the rule.

If the winner's `max |Δ|` exceeds a gate bound it would have to satisfy
(`G-M4-1 .010` on WER, `G-M4-2 .020` on DER), the finding is a **hard** one and the
disposition returns to the owner rather than to a moved bound.

## Reported beside the gates, not gated

- The M4 gate arithmetic for `lex_adam_frank` under each arm: `G-M4-1` `abs(wer - file)
  <= .010`, `G-M4-2` `abs(der - file) <= .020`, `G-M4-3` `wer <= .122411` (that pass's own
  rolling arm), `G-M4-4` `v2 content_recall >= .951036` and
  `matched_word_speaker_accuracy >= .951036`.
- Iteration 29's F3 already measured that this case's gate set is unsatisfiable in **both**
  directions. Nothing here moves a bound; the disposition is an owner ruling recorded in
  the bundle (PRD: preregistered gates are immutable mid-run).
- How the deployed DER reacts to an overlapping hypothesis at all, since
  `calculate_diarization` sums segment durations rather than their union.

## What this prototype does NOT do

- It does not touch production. Shipping the selected policy is the next iteration's one
  logical change, and re-scoring M4 needs a fresh paired batch on the deployed service.
- It does not re-run any decode. Every input is a file arm already on disk under
  `evidence/live-convergence-0824/`.
