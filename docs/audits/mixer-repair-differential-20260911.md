# Mixer repair differential — 2026-09-11

**Implemented and measured; the requested per-case quality target is NOT met.**
The six-case candidate fixes both extra emitted identities (Adam 3→2, RTFL 5→4),
but Jamie and RTFL settled DER worsen versus the prior account path. Immediate
WER also worsens by two errors in Adam and one in Jamie. Recommend holding the
behavioral candidate from demo cutover, not relaxing bounds or changing identity
policy. The implementation checkpoint is `905eadbb` on private/auto-mvp-0911.

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

## D1 — Decision

Hold `905eadbb` as a measured repair candidate, not a qualified demo cutover.
It fixes the demonstrated extra identities and tail plumbing, but does not satisfy
all requested quality invariants. Do not call the six-case difference noise or
change identity policy/bounds to accept it. The raw-source speech-boundary choice
has a real ASR/attribution trade-off, documented above for the operator.

## Custody and reproduction

Measurement process loaded local `ef456afb` before its rebase onto peer diagnostics
`cf0dc398`; its runtime/mixer/ingress/contract/replay files are byte-identical to
pushed `905eadbb`. Baseline is the retained current-runtime mono/account differential
from `463b1d66` reported in `987d17dc`, not an asserted historical Phase-1 binary.
Same installed provider/decoder/configuration, existing local tunnel, draft off,
pace 1x, a fresh workspace on the agent-owned 17862 database, no bank enrollment.
No host operations or 17861 database access. Raw captures remain under
`/tmp/moss-mixer-repair/runs`; only content-free scores/counts/timings are committed.

[All per-surface DER/WER/counts and observations](../../prototypes/streaming-diarization/mixer-repair-feasibility/differential-results.json)
and [input proof](../../prototypes/streaming-diarization/mixer-repair-feasibility/input-proof.json).
Commands and the reusable fresh-workspace replay are in the adjacent NOTES.md.
