# M0c — evaluator v2 measures words, not timestamps (2026-08-25)

**Question (plan A0.3).** Can the campaign be scored on a lens that a wider timestamp cannot
move?

**Answer: yes, and the old lens is measurably movable.** Against the trio, a hypothesis that is
one 60-second segment whose only word is `xx` earns **text coverage 1.0000, TBSA .6817, DER
.1722** under the deployed scorer — and **content recall .0000, matched-word speaker accuracy
.0000, WER 1.0000** under evaluator v2. Same audio, same reference, same segment: the deployed
scorer is paying for extent, v2 is paying for words. (Those three deployed numbers reproduce
plan §3.4's `.6817` / `.1722` / `1.0` to four decimals from an independent implementation — the
plan's own artifact claim is now measured, not quoted.)

## What v2 reports

`prototypes/streaming-diarization/live-convergence/evaluator_v2.py` — scoring only, no corpus
layout, no CLI. Six reports, all six required by A0.3:

| report | how it is decided | can a wider timestamp move it? |
|---|---|---|
| `wer` | Levenshtein over words, with sub/del/ins counts | no |
| `content_recall` | LCS(reference, hypothesis) / reference words | no |
| `seam_profile` | WER split by distance to the hypothesis span grid's seams | it *describes* the grid |
| `matched_word_speaker` | speaker of each lexically matched word, mapped by max-weight assignment, over **all** reference words | no |
| `der_reference_speech` | DER scored only inside real reference speech regions | partly — time metrics always are |
| `legacy` | the deployed TBSA + diarization numbers, unchanged, beside | yes — that is the point |

Two design choices worth stating, because both are load-bearing:

- **Matched-word speaker accuracy divides by every reference word, not by the recovered ones.**
  A word the arm never transcribed earns no speaker credit. `speaker_precision_on_matched` is
  reported separately for diagnosis, but it is not the axis: dividing by recovered words would
  reward an arm for transcribing less.
- **Real speech regions come from the deployed live VAD instrument** (webrtcvad mode 1, 10 ms
  frames at 16 kHz — the settings `live_provider_bundle.py` and the emptyspan prototype already
  use), with no smoothing and no padding. An added knob would be an added way to move the number.
  The corpus references are gapless turn intervals, so the deployed DER charges an arm for every
  pause *inside* a turn; restricting to real speech removes exactly that charge and nothing else.

## Gates — all pass

`console.txt` (full run) and `evaluator-v2.json` (full payload).

| gate | result |
|---|---|
| Q1 self-score exactly 1.0 on every axis | 5/5 cases: WER .0, recall 1.0, matched-word speaker 1.0, DER .0, legacy TBSA 1.0 |
| Q2 `"xx"` over the clip earns nothing | 5/5 cases: recall .0000, matched-word speaker .0000, credited words 0 |
| Q3 invariant to same-speaker segment splits | 10/10 arms: every span cut in two, adjacent, same label → all four axes bit-identical |
| Q4 live/file conclusions reproducible | 10/10 legacy recomputations exact to 1e-6 vs the checked-in baseline; 4/4 published means reproduced; 4/4 per-case conclusions hold |

Q4's published-means check is the strongest offline anchor available: the plan §1.3 baselines
(file WER `.1039` / recall `.9506`, live WER `.1999` / recall `.9135`) are reproduced to their
published decimals by a scorer that computes both quantities by a different route than the arm
that produced them.

`Q3` deliberately excludes `seam_profile` from the compared axes. The seam profile is a
*partition* of the same WER — splitting a span adds a seam and moves the partition, which is
what it is for. The scorer asserts the partition stays exact (boundary + interior words = total
words, boundary + interior errors = total errors) and mutation M3 below proves the exclusion is
a real decision, not an oversight.

## Numbers this produced

Trio means (bill / milei / keyu), scored from the checked-in saved hypotheses:

| arm | WER | content recall | matched-word speaker acc | DER (speech regions) |
|---|---:|---:|---:|---:|
| file | .1039 | .9506 | .9506 | .0679 |
| live | .1999 | .9135 | .9059 | .1393 |

Five-minute case (`5m-lex-keyu-jin`): file .0506 / .9726 / .9726 / .0449 vs live .1464 / .9302
/ .8796 / .1113.

**Seam severance reproduces independently.** Pooled over the trio, at the 0.40 s band:

| arm | boundary words | boundary WER | interior words | interior WER | density ratio |
|---|---:|---:|---:|---:|---:|
| file | 111 | .0631 | 329 | .1246 | 0.51 |
| live | 155 | .3290 | 285 | .1404 | **2.34** |

`prototypes/live-file-gap-context/diagnosis.json` reached 2.72 (live) and 0.75 (file) from a
different implementation over a different seam set (span-grid boundaries from the trace, not
hypothesis segment edges). Two implementations, two seam definitions, same conclusion: live
errors concentrate at seams and file errors do not.

**What the speech-region restriction actually removes** (`evaluator-v2-no-vad.json` re-runs the
same DER formulation over reference intervals instead):

| case | arm | DER, speech regions | DER, reference intervals | deployed DER |
|---|---|---:|---:|---:|
| bill | live | .2154 | .2235 | .2235 |
| milei | live | .1116 | .1945 | .1945 |
| keyu | live | .0910 | .1112 | .1112 |
| 5m keyu | live | .1113 | .1315 | .1315 |

The middle column equals the deployed DER exactly on every fully-referenced case — so v2's DER
is the *same measurement*, differing only in where it is scored. Milei's deployed DER was
mostly silence inside gapless turns (.1945 → .1116). Note `acquired_jamie_dimon`: its reference
covers 12.3 s of a 60 s clip, so scoring over full-clip speech regions charges the other 47 s as
false alarm (DER 3.46). That is correct and is why the PRD keeps partial-reference cases
diagnostic-only — the evaluator surfaces the problem instead of hiding it.

## Mutation check — the gates have teeth

`mutation-check.txt`. Control passes before and after each mutation; all five caught:

| mutation | caught by |
|---|---|
| M1 speaker credit also counts substituted words | Q2 ×5 |
| M2 `content_recall` taken from the legacy time-overlap coverage | Q2 ×5, Q4 published means |
| M3 seam boundary WER treated as a score axis | Q3 ×6 |
| M4 DER speaker mapping forced to the first hypothesis label | Q1 ×5 |
| M5 hypothesis loader silently drops the last segment | Q4 legacy recomputation ×6 |

## Reproduce

```bash
# the plan's proposed command (trio + the diagnostic secondary)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_evaluators.py \
  --manifest prototypes/streaming-diarization/data/real/benchmark_diarization_1min/manifest.json \
  --output /tmp/moss-live-evaluator-v2.json
# every case including the 5-minute one (its corpus has no manifest file)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_evaluators.py --output /tmp/v2.json
```

Exit 0 iff every gate passes. No production module was touched by this iteration, so file mode
is unchanged by construction (`git status` shows only new prototype and evidence files).

## What this does not settle

- v2 is a **prototype**, not the production scorer. Nothing in `moss_transcribe_diarize/` reads
  it yet, and the M1–M4 gates still name the deployed metrics. Promotion is a later, separate
  change with its own review.
- Time-based DER is extent-sensitive by nature even restricted to speech regions. The
  non-gameable speaker axis is `matched_word_speaker_accuracy`; M3 must report both (plan §1.3
  G4 already requires both).
- The seam profile's seam set is the hypothesis segment grid. For an arm whose segments are not
  its span grid (file mode, or a future stitcher), "seam" means that arm's own segment edges —
  compare arms by density ratio, not by raw boundary WER.
