# Mixer repair differential — 2026-09-11

**Operator-approved for round 11 host measurement under the pre-approved 5% band.**
Local settled DER macro .162036 is below .16947 (1.05 × the operator-stated .1614
bound); all six emitted speaker counts match reference, and final WER is unchanged
or better. This supersedes the earlier hold recommendation. The host measurements
decide qualification; this local comparison is not a host pass. The stricter
per-case parity and unchanged-immediate-WER targets remain unmet, as retained below.
The implementation checkpoint is `905eadbb` on private/auto-mvp-0911.

## F1 — What changed, and why the first shortcuts were rejected

Identity-only raw PCM on the old short windows still births identity 3 (.2402
match, versus .1954 mixed and .5925 with original mono windows). The corrected
implementation preserves source-level PCM for both speech boundaries and identity.
Exactly one audible rendered lane uses original level; two audible lanes keep
their coherent mix. No speaker is selected or dropped from overlapping audio.
Decoder, rolling, draft, recording and terminal PCM retain the existing gain.
Analysis retention shares canonical admission/commit boundaries; it has no full
recording tape. The capacity test fills the existing bound, refuses excess audio
without growing analysis retention, then frees capacity on commitment.

The producer now supplies an optional observed exclusive frame-end timestamp.
This releases a completed source frame without guessing its successor timestamp.
The browser uses its audio render clock; the replay client uses audio time. Legacy
frames retain successor sealing. An explicit end cannot later be overlapped, even
after source accounting. Two-lane drift plus interleaved arrival produces exactly
the same mixed bytes as fully observed timestamp-aligned input. Stop already
performed final sealing/draining; that behavior remains. Legitimate unfinished
endpoint tails below a canonical freeze remain until Stop; no mixer lookahead
holds already received source audio from the runtime.

All six input custody checks: analysis PCM equals original source bytes, decoder
PCM equals the prior headroom formula, and all received samples are admitted before
Stop. Largest analysis frame: 16,000 bytes. Numeric identity policy, QUALITY_BOUNDS
and _validate_quality are untouched. Canonical publication/abort fences are unchanged.

## F2 — Settled diarization and speaker counts

DER is diarization error rate (lower is better). Speaker counts are emitted labels
on the settled surface, not registry births. One after pass per case; no statistical
noise band has been measured. A lower macro cannot establish per-case parity.

| Case | Mono DER | Account before | Account after | Mono / before / after / reference speakers |
|---|---:|---:|---:|---:|
| Javier | 0.112600 | 0.172000 | 0.142400 | 1 / 1 / 1 / 1 |
| Ackman | 0.122667 | 0.152500 | 0.106500 | 2 / 2 / 2 / 2 |
| Keyu | 0.089167 | 0.140833 | 0.089667 | 2 / 2 / 2 / 2 |
| Adam | 0.091167 | 0.119889 | 0.097944 | 2 / 3 / 2 / 2 |
| Jamie | 0.094352 | 0.103849 | 0.116474 | 3 / 3 / 3 / 3 |
| RTFL | 0.430644 | 0.406546 | 0.419230 | 4 / 5 / 4 / 4 |

Macro DER: mono **0.156766**, before **0.182603**, after **0.162036**.

Javier remains entirely missed timed coverage: DER/miss .1424, false alarm 0,
speaker confusion 0; one identity throughout. The restored source-level endpoint
boundaries do not make mixed-decoder timestamps identical to mono timestamps.
Jamie still has four births, two admitted, two provisional-only, three emitted;
after repair it has one abstaining span versus zero before. Its after DER contains
.071393 miss, .005307 false alarm and .039774 speaker confusion. A matching visible
speaker count is therefore insufficient. The exact remaining Jamie turn-level
embedding/attribution divergence is unmeasured; do not claim it is explained away.

## F3 — WER: unchanged PCM does not mean unchanged text

Word error rate, lower is better. Each cell is **mono / account before / account
after**. Canonical window changes can change decoder outputs despite identical
per-sample decoder gain. Immediate surfaces also depend on completed work at capture.

| Case | Immediate WER | Settled WER | Final WER |
|---|---:|---:|---:|
| Javier | 0.194690 / 0.194690 / 0.194690 | 0.159292 / 0.194690 / 0.159292 | 0.097345 / 0.088496 / 0.088496 |
| Ackman | 0.272727 / 0.272727 / 0.272727 | 0.204545 / 0.272727 / 0.204545 | 0.159091 / 0.147727 / 0.147727 |
| Keyu | 0.136691 / 0.143885 / 0.143885 | 0.093525 / 0.143885 / 0.100719 | 0.064748 / 0.064748 / 0.064748 |
| Adam | 0.146893 / 0.143126 / 0.146893 | 0.133710 / 0.129944 / 0.133710 | 0.126177 / 0.133710 / 0.126177 |
| Jamie | 0.111498 / 0.106272 / 0.108014 | 0.094077 / 0.106272 / 0.090592 | 0.069686 / 0.069686 / 0.069686 |
| RTFL | 0.135922 / 0.140777 / 0.140777 | 0.135922 / 0.169903 / 0.140777 | 0.053398 / 0.053398 / 0.053398 |

Immediate WER is unchanged versus account before in four cases; Adam adds two
errors over 531 reference words, Jamie adds one over 574. Final WER is unchanged
in five cases; Adam removes four errors and equals mono. Thus literal unchanged
immediate/final WER is not established. No gain policy or score threshold was tuned
to hide these changes.

## F4 — Capture validity and performance limits

All six after sessions reached genuinely final terminal state. Every settled
capture had zero pending canonical/rolling work, no settle timeout, and
finalization not_started. No scoring of failed sessions.

| Case | Settle wait seconds | Pending canonical / rolling | Final state |
|---|---:|---:|---|
| Javier | 0.784643 | 0 / 0 | final |
| Ackman | 1.317816 | 0 / 0 | final |
| Keyu | 1.059910 | 0 / 0 | final |
| Adam | 0.530451 | 0 / 0 | final |
| Jamie | 1.062077 | 0 / 0 | final |
| RTFL | 0.004546 | 0 / 0 | final |

Javier separately failed strict canonical decoder p95 real-time-factor performance
(3.04717 versus bound 1). All three quality captures were valid and are retained;
this is a quality measurement, not a performance or deployed qualification pass.
The other five reported no replay performance failure.

## F5 — Validation and limits

- Product suite after rebase: **1,462 passed + 37 subtests, 2 existing skips**.
- Frontend: **202 passed**; typecheck and bundle build passed.
- Focused mixer/lane/coordinator/replay: 117 passed + 9 subtests before the added
  capacity regression; that regression is included in the final full count.
- No acceptance selectors changed. Existing capture-phase, observer, sequence,
  lane, epoch, Stop, preview/abort and export tests remain green.
- Direct local account_product_regression could NOT be certified. Chrome rejects
  the scratch certificate. A separate functional attempt bypassing that certificate
  stops at `document.visibilityState === 'hidden'`; it never completes the predicate.
  An application-free two-tab control also stays visible after bringing the other
  tab forward, establishing this local Chrome limitation independently of MOSS. No predicate assertion
  was softened or patched to make this pass.
- Repository-root discovery additionally runs historical prototype tests: one
  intentionally source-pinned baseline and two unavailable archived .npz fixtures
  fail there (1,562 passed, three failures). The established product `tests/` suite
  above is green. An isolated pre-existing 2-second Stop-test timeout also reproduces
  on unchanged 88e226a2; it passes in both complete product-suite runs.

## D1 — Operator decision supersedes the earlier hold recommendation

Proceed with round 11 host measurement under the mandate's existing 5% band.
The measured local macro and final WER support that decision; per-case regressions
remain visible, not waived by changing policy or bounds. No numeric bound or
identity-policy value changes. The bounded attribution follow-up below isolates analysis from observed-end release.
No production tweak is added; the accepted implementation remains unchanged.

## Custody and reproduction

Measurement process loaded local `ef456afb` before its rebase onto peer diagnostics
`cf0dc398`; its runtime/mixer/ingress/contract/replay files are byte-identical to
pushed `905eadbb`. Baseline is the retained current-runtime mono/account differential
from `463b1d66` reported in `987d17dc`, not an asserted historical Phase-1 binary.
Same installed provider/decoder/configuration, existing local tunnel, draft off,
pace 1x, a fresh workspace on the agent-owned 17862 database, no bank enrollment.
No host operations or 17861 database access. Raw captures remain under
`/tmp/moss-mixer-repair/runs` (MacStudio-local (not in repo)); only content-free scores/counts/timings are committed.

[All per-surface DER/WER/counts and observations](../../prototypes/streaming-diarization/mixer-repair-feasibility/differential-results.json)
and [input proof](../../prototypes/streaming-diarization/mixer-repair-feasibility/input-proof.json).
Commands and the reusable fresh-workspace replay are in the adjacent NOTES.md.


## F6 — Bounded attribution: source analysis causes the loss; observed ends help

Completed in 11.6 minutes, within the 30-minute limit. Two new isolated account
replays per case, same decoder/configuration and real audio. Production behavior
unchanged; controls exist only in scratch process wrappers. Before/both cells are
the accepted retained measurements, not new qualification runs.

| Case | Before | Observed ends only | Source analysis only | Both (accepted candidate) |
|---|---:|---:|---:|---:|
| Jamie | 0.103849 | 0.091280 | 0.128484 | 0.116474 |
| RTFL | 0.406546 | 0.405396 | 0.419230 | 0.419230 |

For both cases, observed-end-only and before have identical frozen span boundaries;
source-analysis-only and both also have identical boundaries. Source analysis is
what changes those boundaries. Observed ends release the same regularly timed PCM
earlier, improving Jamie's settled coverage; RTFL's analysis-only/both DER is
identical. Thus the observed-frame-end change is not the cause of these losses.

Jamie provides a concrete witness, not a complete allocation of every DER error:
the relevant window shifts from [61.62,64.12) to [61.49,63.99). The decoder emits
local S01 over [0,2.5) and overlapping S02 over [1.91,2.5). Both strongly match the
same existing identity (.872015 and .672648); the unchanged same-span cannot-link
rule correctly abstains. The reference contains one speaker over that span. This
abstention recurs in the source-analysis-only control. It is not weak evidence or
an observed-end-induced boundary change. Local ASR labels and word/timing output
still depend on the canonical window, even when embedding audio is original-level.

No obvious safe bounded tweak was established. Keeping the old endpoint windows
and using original-level embeddings alone already failed the Adam control: .240166
match, still three identities. Disabling source analysis would abandon that fix;
weakening the cannot-link rule would violate policy/invariants. No per-case rule,
new window policy, threshold change or merge is introduced. Leave the accepted
candidate intact for round 11 under the operator's decision.

All four new sessions finalized, and all settled captures drained without timeout.
Full arm scores/counts, frozen boundaries and abstention reasons are retained in
[attribution-results.json](../../prototypes/streaming-diarization/mixer-repair-feasibility/attribution-results.json);
the anonymous [Jamie witness](../../prototypes/streaming-diarization/mixer-repair-feasibility/attribution-witness.json)
contains no text/audio/embeddings. Agent-owned 17862 server stopped; its database
and raw captures preserved. No host operations or 17861 access.
