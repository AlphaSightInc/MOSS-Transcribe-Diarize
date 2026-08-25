# Preregistration — M2 step 2, plan §10.2–§10.4 rolling-convergence grid

Written **before** `compare_rolling_grid.py` issued its first decode (2026-08-25, campaign run
20260825-042645-70858, iteration 10). Throwaway prototype under
`prototypes/streaming-diarization/live-convergence/`; its verdict selects the arm that plan
§10.5 then implements in production, governed by `docs/adr/0005-live-text-finalization-authority.md`.

## Question

Plan §10.1: **which window/stride and truth-blind stitch policy preserve the rolling gain with
the fewest joins and least GPU work?**

The deployed live lane publishes a provisional transcript from independent ~2.5 s spans. A
rolling converger re-decodes longer overlapping windows behind the live edge and replaces the
words in the region each window owns. `prototypes/live-file-gap-context/` measured one such arm
(`a2`: 10 s window, 5 s stride, central ownership) at trio WER `.1289` against a live baseline of
`.1999`. That arm costs `1.833` added decode-audio-seconds per audio-second. The grid asks
whether a cheaper arm keeps the gain.

## Grid (fixed now; no arm may be added after the first decode)

Plan §10.2, in full. Twelve arms — four window/stride pairs × three stitch policies:

| window | stride | overlap | windows per 60 s | added decode-audio s / audio s | purpose (plan §10.2) |
|---:|---:|---:|---:|---:|---|
| 10 s | 5 s | 5 s | 11 | 1.833 | measured quality reference |
| 10 s | 10 s | 0 s | 6 | 1.000 | half the witness audio work; fewer joins |
| 15 s | 7.5 s | 7.5 s | 7 | 1.750 | more context with 2× overlap |
| 15 s | 10 s | 5 s | 6 | 1.500 | proposed quality/cost compromise |

Windows tile `[0, duration]`: starts are `k · stride` for `k = 0 … ceil((duration − window)/stride)`,
each clamped so the last window ends exactly at `duration`.

### The three stitch policies

All three answer one question — **which decode owns each word** — and none may read reference
truth (below). Each produces a word sequence with times; `rows_to_segments` + `normalise` then
regroup words into segments exactly as the existing bench does, so the policies differ only in
ownership and in word-time interpolation.

- **`char` — character-proportional central ownership.** A decoded segment's words receive time
  slices proportional to their character length inside the segment. Window `i` keeps the words
  whose midpoint falls in its central ownership region `[lo + (L−S)/2, lo + (L+S)/2)`, clamped to
  the clip at the first and last window. This is `proto_context_arms.py`'s `word_rows` +
  `a2` reconciliation verbatim, so **the 10/5 `char` arm is the reproduction control for the
  published `.1289`**.
- **`uniform` — uniform token-time central ownership.** Identical, except every token in a
  segment receives an equal share of the segment's duration.
- **`lexical` — lexical overlap alignment with central ownership.** The cut between consecutive
  windows is decided by aligning text, not by an interpolated clock: the words already committed
  inside the overlap are aligned semi-globally against the head of the fresh window's words
  (`proto_context_arms.trim_prefix_by_text`, the same DP the prefix-audio arms use), and the
  fresh window contributes everything after the alignment ends. Word times are
  character-proportional, as in `char`, because the alignment decides ownership and the times only
  place the words.

**Recorded plan ambiguity, resolved before measuring.** Plan §10.2 names the *lexical* policy as
"the reference candidate … its working implementation is `proto_context_arms.py` (arm `a2`)", but
`a2` in that file cuts by word midpoint against a central region and interpolates word times by
character count — that is the `char` policy as defined above, not a lexical alignment. The `.1289`
number therefore belongs to `char` at 10/5. This preregistration keeps the plan's three *names*
and its measured *number*, and attaches the number to the arm that produced it. If the plan's
naming is later corrected, the arm identities here do not move.

## Truth-blindness (plan §10.2: "the reconciler sees no reference")

Enforced structurally, not asserted: an arm is produced by functions that receive only decoded
text, window bounds, and the recorded span grid. While an arm is being produced the driver
replaces `proto_context_arms.load_reference` with a raiser, so a reference read from anywhere
inside the reconciler aborts the run instead of silently scoring itself. Truth enters only in
`score()`, after the hypothesis exists.

## Corpus

The fully referenced primary trio only: `lex_bill_ackman`, `lex_javier_milei`, `lex_keyu_jin`
(60 s each). `acquired_*` samples carry partial references and are never scored (PRD constraint).
The 5-minute case is **not** in this grid: PRD M2 gates it separately and iteration 8 measured it
as the only case with a real pass-to-pass spread, so it belongs to M2's soak, not to arm
selection.

The provisional base is the recorded live span grid from the frozen
`prototypes/live-file-gap-baseline-20260824/trio-60s/<case>/live/run-001/trace.jsonl`, each span
decoded alone at the canonical token cap — the same base `a0` used, so the base control is
comparable to the published live means.

Identity is held fixed exactly as `preregistration-context-arms-v1.json` fixes it: every arm's
segments are relabelled from one shared speaker timeline built from the baseline live
hypothesis. No arm can be credited or penalised for diarization; `wer` and `content_recall` are
label-free and unaffected.

## Decoding

`http://127.0.0.1:18000/v1`, greedy, **one in-flight request**, model discovered from the
endpoint, `DEFAULT_PROMPT` unchanged, `canonical_decode_token_cap(sample_count)` for every
request including the windows. Decodes are cached on disk keyed by
`(audio, sample range, model, token cap, prompt, run index)`, so the three stitch policies share
one decode of each window and a re-invocation re-uses the run's decodes exactly.

`--runs 3` (plan §10.3): runs 1 and 2 re-decode with a distinct cache key, so the spread across
runs is the grid's own noise floor rather than a cache echo.

## Gates (immutable; from PRD M2 and plan §1.3)

Ranked on the trio mean over the runs, with per-run values reported:

| code | gate | threshold | source |
|---|---|---:|---|
| G1 | trio mean rolling WER | `<= 0.150` | plan §1.3 G1 / PRD M2 |
| G2 | per-case rolling WER below current live | bill `< .261364`, milei `< .144`, keyu `< .194245` | plan §1.3 G2 / PRD M2 |
| G3 | trio mean content recall | `>= 0.940` | plan §1.3 G3 / PRD M2 |

Comparators are read from `prototypes/live-file-gap-baseline-20260824/trio-60s/results.json` at
full precision, with a round-trip assertion against the 4-dp values the PRD prints. Reported but
**not selecting**: TBSA, coverage, DER, segment extents (plan §3.4 extent artifact; plan D8).

### Selection rule (plan §10.4, fixed now)

Choose the **least expensive arm passing G1, G2 and G3**, expense measured as added
decode-audio-seconds per audio-second, ties broken by fewer joins then by lower WER. Never
select by TBSA. **If no arm passes, no rolling production code is written** and M2 stops with
that finding.

### Reported beside the gates, because §10.3 requires it

Every decode window, its ownership region, every selected and dropped word, the join duplicate
check, per-decode latency, decoded-audio work, the rolling-PCM high-water mark, and the request
counter delta.

**Structural correction-age bound (the G6 input this grid can honestly produce).** Plan §1.3 G6
requires rolling correction p95 `<= 6.0 s` after provisional publication, measured in production
under §10.6 pacing. Offline, the grid reports the *floor* that arm geometry imposes, from
measured decode latencies and the recorded span grid: a word owned by window `[lo, hi]` cannot be
corrected before `hi + decode(window)`, and it was published provisionally at
`span_end + decode(span)`, so its correction age is at least the difference. p50/p95/max over
**changed** owned regions only, matching G6's definition. This is a lower bound and is labelled
one; it does not pass or fail an arm, but an arm whose floor already exceeds 6.0 s cannot pass G6
in production at full-window granularity, and that is a finding M2 step 3 must design around.

## Predictions on record (falsifiable, written before the first decode)

- **P1 — bench validity.** The base control reproduces the published live trio means within
  `.005` WER of `.19987` and `.005` recall of `.91349`. A larger miss invalidates the grid and no
  arm is reported as a verdict.
- **P2 — reproduction control.** The 10/5 `char` arm lands within `.005` of the published `a2`
  WER `.128926` and recall `.948477`.
- **P3 — structural identity at zero overlap.** At 10/10 there is no overlap, so ownership is the
  whole window under all three policies and no alignment cut exists. The three 10/10 arms must
  produce **identical word sequences** — identical WER and identical content recall to the last
  digit — differing only in extent-derived metrics (TBSA, coverage, DER, mean segment seconds).
  A difference means one of the three stitchers is not implemented as specified.
- **P4 — all four geometries pass G1/G3.** Every window/stride pair passes WER `<= .150` and
  recall `>= .940` on at least one stitcher; the gain is a property of longer context, not of a
  particular join policy.
- **P5 — the cheapest arm wins.** The selected arm is 10/10 (added `1.000`), not the measured
  reference 10/5 (added `1.833`).
- **P6 — the latency floor bites the cheap arms.** The structural correction-age p95 exceeds
  6.0 s for every arm, and is smallest at 10/5 (`≈ 5–7.5 s`) and largest at 15/10 (`≈ 10–12.5 s`).
  Cost and latency therefore rank the geometries in opposite orders, and the selection rule above
  — which ranks on cost — is applied unchanged.

## Stop rule

A gate failure that survives attribution (the campaign protocol fixed in
`evidence/live-convergence-0824/M1-salvage-production/PREREGISTRATION.md`: attribute a delta to a
named span or decode before calling it a regression) is reported as a failure. Specifically: if
no arm passes G1–G3, that is plan §10.4's "do not implement rolling production code" and it ends
E2 with a recorded finding — not a licence to widen the grid, add an arm, or move a threshold.
