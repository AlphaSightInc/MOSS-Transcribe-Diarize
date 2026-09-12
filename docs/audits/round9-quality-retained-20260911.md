# Round 9 retained quality evidence — 2026-09-11

**The immediate-to-settled WER increase is caused by canonical tail commits, not
new rolling revisions or Stop.** Eleven sessions already had rolling revisions at
immediate. Javier pass 1 alone lost rolling to `pcm_evicted`. All twelve settled
captures are active, genuinely drained, before Stop, with zero timeouts.

This closes F3 from [the earlier audit](acceptance-helper-background-settled-20260911.md).
No runtime, collector, bounds or identity changes are made.

## Evidence and method

Archive: `/tmp/moss-round9-stage/result/evidence.tar` (MacStudio-local (not in repo)), candidate **433e67b2**.
Extracted into a temporary directory outside the repo. Read
`raw/pre_admission-collector/artifacts/quality/content-free-metrics.json` and each
`pass-{1,2}/<case>/terminal-diagnostics.json`. All **12** rows are used to reproduce
the reported macro; no pass or case selected away. Derived scores, observations and
relevant events are retained in [the evidence table](round9-quality-retained-20260911.json).
The archive has content-free capture observations, not full transcript snapshots;
word-level substitution/insertion identities cannot be recovered from it.

Structural question: which work changes the scored document between captures?
Minimum primitives: the same session's document revision, immutable audio boundary,
work completion event and lifecycle timestamp. Invariants: compare the same reference
and session; never equate an unchanged counter with absence of earlier rolling;
never count a completion event as an applied revision without checking its outcome.
The falsifiers are an intervening revision, an earlier Stop, an undrained queue or
an unmatched macro. The artifact analysis checks all four directly.

## F1 — Per-case numbers

Each triple is **immediate → settled → final**. WER is word error rate; DER is
speaker diarization error rate. Values are proportions, not percentages. `Revision`
is `text_revision_version`. `Applied` counts successful rolling publications before
settled (all occurred before immediate too). Wait is seconds.

### Pass 1

| Case | WER | DER | Revision | Wait s | Applied |
|---|---|---|---|---:|---:|
| Javier 50 s | 0.168142 → 0.168142 → 0.088496 | 0.181600 → 0.181600 → 0.028000 | 0 → 0 → 1 | 0.009653 | 0 |
| Bill Ackman 60 s | 0.272727 → 0.272727 → 0.147727 | 0.156167 → 0.156167 → 0.060500 | 5 → 5 → 7 | 0.009952 | 5 |
| Keyu Jin 60 s | 0.143885 → 0.143885 → 0.064748 | 0.140833 → 0.140833 → 0.074333 | 5 → 5 → 7 | 0.009242 | 5 |
| Adam Frank 180 s | 0.145009 → 0.131827 → 0.133710 | 0.137722 → 0.123944 → 0.059611 | 17 → 17 → 19 | 0.545182 | 17 |
| Jamie Dimon 180 s | 0.108014 → 0.108014 → 0.069686 | 0.104017 → 0.104017 → 0.071560 | 17 → 17 → 19 | 0.010374 | 17 |
| RTFL 90 s | 0.140777 → 0.169903 → 0.053398 | 0.396200 → 0.405396 → 0.333752 | 8 → 8 → 9 | 0.272473 | 8 |

### Pass 2

| Case | WER | DER | Revision | Wait s | Applied |
|---|---|---|---|---:|---:|
| Javier 50 s | 0.194690 → 0.194690 → 0.088496 | 0.172000 → 0.172000 → 0.028000 | 4 → 4 → 6 | 0.009461 | 4 |
| Bill Ackman 60 s | 0.272727 → 0.272727 → 0.147727 | 0.156167 → 0.156167 → 0.060500 | 5 → 5 → 7 | 0.008988 | 5 |
| Keyu Jin 60 s | 0.143885 → 0.143885 → 0.064748 | 0.140833 → 0.140833 → 0.074333 | 5 → 5 → 7 | 0.008860 | 5 |
| Adam Frank 180 s | 0.145009 → 0.131827 → 0.126177 | 0.137722 → 0.123944 → 0.064556 | 17 → 17 → 19 | 0.799313 | 17 |
| Jamie Dimon 180 s | 0.108014 → 0.108014 → 0.069686 | 0.104017 → 0.104017 → 0.071560 | 17 → 17 → 19 | 0.010948 | 17 |
| RTFL 90 s | 0.135922 → 0.165049 → 0.053398 | 0.397021 → 0.406217 → 0.333752 | 8 → 8 → 9 | 0.537433 | 8 |

Across **all twelve**:

- Immediate and settled: `status=active`, `finalization_status=not_started`.
  Final: `status=closed`, `finalization_status=final`.
- Settled: pending canonical work **0**, pending spans **0**, pending rolling work
  **0**, `drained=true`. **No timeout**; configured settle limit 30 s.
- Adam and RTFL, both passes: immediate pending work/spans **1/1**, settled **0/0**.
  Every other immediate capture is already **0/0**.
- Stop was requested **0.146–0.343 ms after** settled was captured. Capture order and
  active status independently reject a Stop-related settled state change.
- No rolling completion or text revision occurs between immediate and settled.
  Only four `canonical_processed` events occur in those intervals.

## F2 — The exact source of the macro increase

RTFL in each pass completes item **55**, a **0.58-second** canonical span, after
immediate and before settled. Accounted audio moves **1,414,720 → 1,424,000 samples**;
rolling frontier stays **1,280,000 samples (80 s)** and revision stays **8**.
Hypothesis words move **209 → 217** (pass 1), **208 → 216** (pass 2). With 206
reference words, word-edit errors move **29 → 35** and **28 → 34**: **six more
errors per pass**. This is eight additional hypothesis words, not proof of eight
insertions; the text itself is not retained. Content recall stays .922330.

RTFL DER rises **.009196** in each pass, while reference-speech DER is unchanged:
**.325887 → .325887** (pass 1), **.326630 → .326630** (pass 2). This is consistent
with additional non-reference-speech attribution, not evidence of a new identity
split; no speaker-policy conclusion follows from these content-free scores.

Adam in each pass completes item **93**, a **2.5-second** canonical span, during
settle. Accounted audio moves **2,827,360 → 2,867,360 samples**; rolling frontier
stays **2,720,000 samples (170 s)** and revision stays **17**. Hypothesis words
**533 → 542**, edit errors **77 → 70** against 531 reference words: **seven fewer
errors per pass**. All other immediate/settled WER pairs are unchanged.

Therefore the complete macro movement is:

`2 × (6/206 − 7/531) / 12 = +0.00265743` (unrounded edit-count arithmetic).

The retained six-decimal case scores reproduce **.1649000833 → .1675575000**
exactly. There is no unexplained residual requiring a rolling-regression hypothesis.
The macro DER actually improves slightly, **.18535825 → .18459458**; final is
**.10503808**. Its bound failure is distinct from the WER increase.

## F3 — One real rolling loss; eleven sessions already rolled

Javier pass 1 queues its first **0–10 s** rolling window, item **8**, at event
**69**, runtime time **2790655299906629 ns**. Event **121** already reports
`rolling_status=pcm_evicted`. Item 8 is dispatched/completed at event **152**,
**2790671839423632 ns**: **16.539517 s** after admission, with
`outcome=not_awaited`, `applied=false`, `rolling_status=pcm_evicted`, and no decode
result. The terminal plan confirms **zero** rolling windows completed, frontier
**0**, status `pcm_evicted`. This is buffer/scheduling loss, not a bad decoder
answer or an identity rejection.

Mechanism in candidate 433e67b2 (unchanged in current code):

- `live_transcript_convergence.py::_trim` bounds its future-audio ring at two
  10-second windows. Overflow calls `_end_refinement(PCM_EVICTED)`, clears the
  outstanding request and stops further rolling for that session.
- `live_coordinator.py::capture_refinement_item` declines dispatch unless the
  converger is still `ROLLING`. Thus a previously admitted item can finish as
  `not_awaited` without calling the decoder.
- The queued request already owns immutable PCM; it is the subsequent ring overflow
  that ends the converger, not proof that its own ten-second payload disappeared.
- The arbiter prioritizes canonical work above refinement. The trace proves the
  16.54-second wait and eviction, but does not isolate decoder scheduling versus
  cold identity initialization or other service time as the cause of that wait.
  “Cold start” is a hypothesis, not a measured root cause.

The other **11/12** sessions applied rolling successfully before immediate; none
has a refused proposal or failed rolling decode. Javier pass 2 has **four** applied
pre-stop windows and a fifth during Stop. Its settled WER **.194690** is worse than
pass 1's **.168142**, but different sessions/base decodes are not a controlled
base-versus-rolling comparison: do not infer causal degradation from that pair.

Whole-run accounting: **118 completion events = 117 applied + 1 not_awaited**.
**108** revisions applied before settled; **9** additional rolling revisions
applied during Stop, before the twelve final revisions. Healthy full windows that
require the last canonical tail can become eligible only when Stop freezes that
tail. A pre-stop settled capture is not the post-Stop fully rolled/final document.

Two existing production-converger tests confirm the named eviction boundary and
healthy bounded-retention behavior (**2 passed**). No provider calls, host commands,
policy changes, or new runtime machinery used for this diagnosis.

## D1 — Classification and operator decision

The proposed alternatives are not exhaustive:

- **(a): true only for Javier pass 1.** Its revision is zero and the event explicitly
  records eviction. Unchanged versions in the other eleven mean rolling already
  happened, not that it never applied.
- **(b): not the explanation for the immediate→settled increase.** No rolling
  revisions intervene. Canonical tail publication accounts for every changed score.
  Whether prior rolling improved each session over its untouched base remains
  unknown without full text snapshots.
- **(c): rejected for all twelve.** Settled is active/not_started, captured before Stop.

**The current deployed pre-stop path did not reproduce the 2026-08-25 campaign's
achieved settled mean.** Measured **.1675575** exceeds the unchanged **.140442**
bound by **.0271155**, or **19.31%**. The frozen bench's **.126365** is cached-provider
and frozen-identity evidence, not a fresh deployed result. This run does not prove
the target is permanently unattainable or justify loosening it.

Recommendation: retain this as a genuine settled-quality failure for the operator,
with two distinct follow-ups rather than another capture-timing change. First,
measure the demonstrated rolling-admission delay/eviction on the real service path;
a repair must preserve canonical priority, bounded memory and the no-gap rolling
prefix, not silently skip a window or merely enlarge a bound. Second, inspect the
RTFL tail's actual decoded text against its audio/reference before proposing a
text correction. Suppressing a committed tail or scoring post-Stop text as
“pre-stop settled” would hide the measured failure and is not proposed.

Settled DER **.18459458** and reference-speech DER **.15662267** also miss their
unchanged **.161430** and **.134804** bounds. The tables localize the particularly
high RTFL attribution error (including final DER **.333752**), but content-free
artifacts cannot establish its speaker-level cause. Identity policy remains untouched.
