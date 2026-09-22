# P5 — scorer abstention conflict prototype

**Status:** ACTIVE — throwaway logic prototype; 0 decoder requests.

## Structural question

Does `score_lanes` incorrectly count the unresolved/abstention canonical speaker
(`None`, represented as `S00` after normalization) as a speaker appearing in both
lanes, even when no identified canonical speaker spans the lanes?

## Minimum primitives

1. The production `normalize_segment` representation of a speaker.
2. The production `score_lanes` conflict calculation.
3. Retained F1 published layers, plus the read-only L1 receipts when their shape
   retains the required inputs.

## Invariants

- Word WER remains scored in each segment's explicit lane.
- `QUALITY_BOUNDS` and every identity constant remain unchanged.
- A real canonical speaker identifier present in both lanes remains a conflict.
- `None`/`S00` is an abstention, never an identified person.
- Unattributed segments and words stay numerically visible; a wholly anonymous
  surface is marked `identity_unqualified` without changing word/lane `passed`.

## Assumptions and unknowns

- The retained F1 published JSON supplies sufficient production-shaped inputs to
  call `score_lanes`.
- Real L1 `receipt.json` may omit hypotheses or normalized speakers; if so their
  re-score is `UNMEASURED`, not inferred.

## Falsifier

Any identified canonical speaker ID that occurs in both lanes must still produce
`speaker_lane_conflicts > 0` and `passed=False`. If the retained F1 conflicts are
not exclusively abstention (`None`/`S00`), no scorer change is supported.

## Tool decisions

- `run.py` invokes the production scorer against retained layers, so it decides
  whether the bug is in the actual score seam rather than a reconstructed rule.
- Focused pytest controls decide whether the narrow exception preserves identified
  speaker conflicts.
- The prescribed full backend suite decides whether the production change regresses
  the frozen candidate.

## One command

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 \
  /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python \
  prototypes/round5-p5/run.py
```

## Step 1 result

**SUPPORTED.** On the retained 22-segment F1 alternation published layer, the
production scorer returned `speaker_lane_conflicts=1` and `passed=False`; the
three cross-lane segments have `canonical_speaker=None`, which
`normalize_segment` reduces to `""`. Both retained published files are
JSON-equal. No identified canonical speaker spans the two lanes. The retained
surface has a microphone WER above the immediate bound, so this receipt proves
the false conflict but cannot itself become a passing surface after the narrow
change. The F1-shaped unit control below must instead prove that outcome.

## Lead addendum — evidence preservation

The scorer change excludes only normalized `""` and persisted `S00` from the
*named-speaker conflict* count. It also returns `unattributed_segment_count`,
`unattributed_word_count`, and, when every segment is anonymous,
`identity_unqualified=True`. The latter is diagnostic only: `passed` retains
its pre-existing word/lane meaning. The controls cover identified single-lane
success, a shared non-empty ID failure, partial F1-shaped anonymity, and an
otherwise-correct all-anonymous surface.

## Step 2 result

The scoped production change makes the retained F1 conflict count zero while
preserving three unattributed segments and eight unattributed words. Its
`identity_unqualified` value is false because identified segments remain. The
two R5 L1 receipt JSON files retain score summaries but no published segment
text/identity or reference text, so their corrected pre-surface scores are
`UNMEASURED`; the prototype prints that custody boundary without inferring a
new score.
