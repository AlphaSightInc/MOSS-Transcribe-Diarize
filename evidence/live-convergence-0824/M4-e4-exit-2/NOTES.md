# M4 exit, re-scored — the terminal surface IS the file surface, on all five cases

**2026-08-25, iteration 32, branch `ralph/live-convergence-0824`.**
Candidate 8f of `scripts/ralph-live-convergence/context.md`. Same 14 gates, same comparators,
same bounds as `../M4-e4-exit/` — fixed on iteration 22 in
`prototypes/streaming-diarization/live-convergence/PREREGISTRATION-M4.md`. Nothing below moved a
bound. The only difference between the two batches is one production change: the terminal seam
resolution shipped in iteration 31 (`../M4-seam-ship/`, ADR-0005 **D9**).

## What this bundle shows in one line

**12 of 14 gates pass**, up from 11. Terminal finalization now converges to the paired file arm
**exactly — distance `0.000000` on WER for all five cases and on DER for four of them** — and the
fifth case, which the previous batch could not finalize at all, now publishes. The two remaining
failures are that one case measured against its own rolling arm, and they are **D-M4-3**, an
owner ruling recorded before the numbers were seen.

## The batch

| | |
|---|---|
| service | stopped pid 86813 (pre-8e-2 build), launched **pid 37488 at `2026-08-25T15:28:31Z`** on repo HEAD `22dc5b8` with a clean tree, same argv (`passes/restart.txt`) |
| descriptor | **identical field for field**, 62 of 62, across the restart (`passes/restart-{pre,post}.json`) — the seam resolution is finalizer-internal and no declared capability can see it |
| passes | `run_paired_passes.sh` (trio A/B, 5-minute A/B) then `run_paired_case.sh` (3-minute A/B), strictly sequential, each preceded by one discarded warm-up decode |
| sessions | 12 live meetings, `15:29:18Z → 15:55:59Z`; **10 of them are the 5 gated cases** (the trio driver also runs the partially-referenced `acquired_jamie_dimon`, which never enters a denominator) |
| real MOSS traffic | 6 discarded warm-ups + 12 live meetings + 12 file jobs + 12 terminal passes; one in-flight request throughout; 4070 Ti untouched |
| provenance caveat | the live provider manifest was **not** re-finalized, so `descriptor.source_revision` still reads iteration 27's `29681e04…` while the deployed code is `22dc5b8`. No driver reads that field; provenance for this batch is `passes/restart.txt` + the `ps` records beside it |

`trio-A` / `trio-B` exit 1 after writing `results.json`: the trio driver crashes on a sixth,
partially-referenced diagnostic case whose reference has an empty `text` field. Pre-existing
(the M2 and iteration-29 M4 consoles carry the same traceback); no scored case is affected.

## The gate table

| gate | verdict | iter 29 | what it measured |
|---|---|---|---|
| G-M4-0 tape fidelity | **PASS** | PASS | 10/10 sessions: tape samples `==` accepted samples, zero gaps, tape PCM digest `==` corpus WAV digest over `[0, accepted)` |
| G-M4-1 terminal WER within `.010` of file | **PASS** | PASS | **max distance `0.000000`** — and now on a *terminal* arm for all five cases, where iteration 29's `.003766` was a rolling stand-in |
| G-M4-2 terminal DER within `.020` of file | **PASS** | FAIL | max distance `.013000` (`lex_adam_frank`, both runs); the other four at `0.000000` |
| G-M4-3 terminal WER no worse than rolling | **FAIL** | PASS | 8/10 improve (bill `.204545→.159091`, milei `.096000→.088000`, keyu `.093525→.064748`, 5-min `.082079→.050616`); `lex_adam_frank` `.122411→.126177`, delta `+.003766` |
| G-M4-4 v2 recall + matched-word speaker, no regression | **FAIL** | PASS | 8/10 at or above; `lex_adam_frank` `.951036→.949153`, delta `-.001883` |
| G-M4-5 accepted `==` terminal accounted | **PASS** | PASS | 10/10 |
| G-M4-6 async lifecycle `not_started→running→final` | **PASS** | FAIL | **10/10** — iteration 29 was 8/10, `lex_adam_frank` ended `failed` |
| G-M4-7 a failure preserves and exports the rolling surface | **PASS** | PASS | fresh in-memory failure arm (this batch has no real refusal to point at) |
| G-M4-8 cold and warm readiness reported separately | **PASS** | PASS | cold terminal decode `2.1536 s`; warm RTF p50 `.034667` / p95 `.036925` over 9 sessions |
| G-M4-9 terminal replaces the surface exactly once, from sample 0 | **PASS** | FAIL | **10/10** apply exactly one revision `[0, accepted)`; a second proposal is refused |
| G-M4-10 complete-tape retention | **PASS** | PASS | peak `accepted × 2` bytes (max `9 600 000` = the declared capacity), released after the terminal evidence, `0` bytes survive |
| G-M4-11 terminal never enters the capture clock | **PASS** | PASS | max combined RTF `.172669`, depth `≤ 1`, zero refusals/stale/failed windows, terminal starts one seq after `session_closed` in all 10 |
| G-M4-12 file mode byte-identical | **PASS** | PASS | six cases' hypotheses identical to their comparators — and to the iteration-29 batch's own file arms, all 12, byte for byte (`hypothesis-identity.txt`) |
| G-M4-13 no terminal event carries a word of the meeting | **PASS** | PASS | 10/10; the only strings on those events are five PCM digests and `final / finalized / rolling / running` |

Gate-set contract: 14 preregistered, 14 scored, no extras, every bound quoted verbatim from its
own row. `--selftest`: all 14 react (`selftest.txt`).

## Per-case quality, both runs identical

| case | live (terminal) WER | file WER | live DER | file DER | live spk_acc | file spk_acc |
|---|---:|---:|---:|---:|---:|---:|
| lex_bill_ackman | `.159091` | `.159091` | `.075500` | `.075500` | `.924500` | `.924500` |
| lex_javier_milei | `.088000` | `.088000` | `.151833` | `.151833` | `.848167` | `.848167` |
| lex_keyu_jin | `.064748` | `.064748` | `.079000` | `.079000` | `.921000` | `.921000` |
| lex_adam_frank | `.126177` | `.126177` | `.066222` | `.053222` | `.933778` | `.946778` |
| keyu-5m | `.050616` | `.050616` | `.057933` | `.057933` | `.942067` | `.942067` |
| **trio mean** | **`.103946`** | **`.103946`** | **`.102111`** | **`.102111`** | **`.897889`** | **`.897889`** |

Against the campaign's own opening baseline (`prototypes/live-file-gap-baseline-20260824/`):
trio live WER `.1999 → .103946`, trio live DER `.1764 → .102111`, five-minute live WER
`.1464 → .050616`. The live surface is no longer *converging toward* the file surface on the
trio; on every deployed axis, to six decimal places, **it is the file surface**.

## The one case that fails, and why the failure is the fix

`lex_adam_frank` is 180 s, so its terminal window plan is `[0, 150)` + `[120, 180)` and the two
windows both decode the stretch `[131.19, 136.62]`. In iteration 29 that produced two overlapping
segments, the live surface refused them (`segments_out_of_order`), and the meeting kept its
rolling text — three gates failed on one refusal. Iteration 31 shipped the resolution; this batch
is the first time it ran inside the deployed service:

```
terminal_finalization_completed  outcome=finalized  applied=true  segments=37
  seam_merged_segments=1  seam_dropped_segments=0  seam_displaced_samples=0
  generated_tokens=1507  decoded_audio_samples=2880000  decode_elapsed_sec=6.62
```

The published surface is the file arm's 38 segments with the one overlapping pair merged into
their union — **546 words, the file arm's word stream exactly** (`three-minute-surface.txt`).
What it costs is `+.003766` WER and `-.001883` recall against that case's rolling arm: **two words
of 526, and one word**, because the rolling arm happens to be slightly luckier on this case.
What it buys is `-.026667` DER, `+.026667` speaker accuracy, `+.024238` coverage, and a meeting
that finalizes at all. That trade is **D-M4-3**, recorded in `../M4-seam-overlap/NOTES.md` before
these numbers existed.

The `.013000` DER distance in G-M4-2 is **not** a quality gap: `evaluation.calculate_diarization`
credits reference seconds twice when two hypothesis segments both claim them, so the file arm's
`.053222` carries a duplication bonus that the seam-resolved terminal arm gives up. Evaluator v2
unions hypothesis intervals before scoring and reads `.054079` for both (iteration 30, F1).

## The deployment moved exactly where it was supposed to, and nowhere else

`hypothesis-identity.txt` compares every arm of this batch against the same arm of the
iteration-29 batch — same audio, same protocol, one production change between them:

- **12 of 12 file arms byte-identical.** File mode did not move.
- **10 of 12 live arms byte-identical.** The two that moved are `three-minute/adam3m-{A,B}` —
  the only two sessions in the batch whose terminal proposal contained a seam.
- `seam-accounting.txt`: those two sessions report `seam_merged_segments=1`; the other ten report
  `0/0/0`. All 12 applied their revision (`outcome=finalized`, `applied=true`); **no refusal on
  the batch**.

The eight trio sessions are single-window (60 s inside a 150/120 plan), so they have no seam to
resolve at all. The 5-minute case does — three windows, two seams — and its stitched proposal
still contains no overlapping pair, which is why it reports `0/0/0` and its live hypothesis is
byte-identical to the previous batch's. So this is the identity the prototype predicted, now
measured on real audio through the deployed service rather than in a harness.

## Reproduction

```bash
# the batch (needs the RUNNING service, ~27 min; restart first — G-M4-8's clock is
# "cold = the first terminal pass in a fresh process")
prototypes/streaming-diarization/live-convergence/run_paired_passes.sh /tmp/m4-exit-<stamp>
prototypes/streaming-diarization/live-convergence/run_paired_case.sh /tmp/m4-exit-<stamp> \
  adam3m lex_adam_frank \
  prototypes/streaming-diarization/data/real/calibration_diarization_3min/samples/lex_adam_frank
mkdir /tmp/m4-exit-<stamp>/three-minute && \
  mv /tmp/m4-exit-<stamp>/adam3m-{A,B} /tmp/m4-exit-<stamp>/three-minute/
# capture restart-{pre,post}.json (GET /api/runtime), restart-{pre,post}-ps.txt and
# restart-utc.txt into the batch ROOT -- G-M4-8 reads them from there, not from beside it.

# the gates (no GPU, no service, no MOSS request) -- against this bundle's own copy
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_m4_exit.py \
  --fresh-root evidence/live-convergence-0824/M4-e4-exit-2/passes --output /tmp/m4-gates.json

# every gate pushed past its own bound, from a converged fixture
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_m4_exit.py \
  --fresh-root evidence/live-convergence-0824/M4-e4-exit-2/passes --selftest
```

Scoring the checked-in copy reproduces the batch's own `gates.json` field for field (1743
fields), with two exceptions: the three `*_root` paths, and
`G-M4-9.value.already_finalized_tests.tail`, which is the wall time of a pytest run.

## Files

| file | what it is |
|---|---|
| `gates.json` | the scored report: 14 gates, the gate-set contract, the five-case quality table, the batch order, the restart record |
| `console.txt` | the same run's stdout |
| `selftest.txt` | 14 reactions from the converged fixture, and the two gates the scored batch fails |
| `seam-accounting.txt` | the three seam fields on every terminal pass of the batch |
| `hypothesis-identity.txt` | every arm against the iteration-29 batch's own arm |
| `three-minute-surface.txt` | `lex_adam_frank` before/after/file: 56 → 37 vs 38 segments, 546 words throughout, and the merged pair |
| `passes/` | the 12 sessions, traces gzipped, plus `console/` and the restart record the batch was taken behind |
| `pytest-full.txt` | `1157 passed, 2 skipped, 411 subtests` |
