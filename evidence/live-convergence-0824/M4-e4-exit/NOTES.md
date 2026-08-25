# M4 exit — the 14 preregistered gates, scored on a fresh five-case batch

**2026-08-25, iteration 29, branch `ralph/live-convergence-0824`.**
Candidate 8d of `scripts/ralph-live-convergence/context.md`. Gates and comparators fixed on
iteration 22 in `prototypes/streaming-diarization/live-convergence/PREREGISTRATION-M4.md`;
nothing below moved a bound.

## What this bundle shows in one line

Terminal finalization converges to the paired file arm **exactly — delta `0.000000` on WER and
DER — on four of five cases**, and on the fifth the pass decoded the whole meeting, reproduced
the file arm's 38 segments word for word, and was then **refused publication** because file
mode's own output overlaps itself at a window seam and the live surface forbids overlapping
segments. **11 of 14 gates pass**; the three that fail are that one refusal, counted three
times, on one case.

## The batch

| | |
|---|---|
| service | restarted onto the same build and manifest at `2026-08-25T14:15:08Z` (pid 86813), descriptor **identical** across the restart, field for field (`passes/restart-{pre,post}.json`) |
| why a restart | G-M4-8's clock: "cold = the first terminal pass after a service restart". Every session in the previous batch would have been warm, so the batch was stopped and re-taken behind a restart |
| passes | `run_paired_passes.sh` (trio A/B, 5-minute A/B) then `run_paired_case.sh` (3-minute A/B), strictly sequential, each preceded by one discarded warm-up decode |
| sessions | 12 live meetings, `14:15:20Z → 14:41:57Z`; **10 of them are the 5 gated cases** (the trio driver also runs the partially-referenced `acquired_jamie_dimon`, which never enters a denominator) |
| real MOSS traffic | 6 discarded warm-ups + 12 live meetings + 12 file jobs + 12 terminal passes; one in-flight request throughout; 4070 Ti untouched |
| deployed revision | `29681e04…` + iteration 27's tree, `combined_config_hash 431efb3f…`, `bounds.max_tape_bytes 9600000` |

`trio-A` / `trio-B` exit 1 after writing `results.json`: the trio driver crashes on a sixth,
partially-referenced diagnostic case whose reference has an empty `text` field. That is
pre-existing (the M2 exit's own `console.txt` carries the same traceback) and no scored case is
affected.

## The gate table

| gate | verdict | what it measured |
|---|---|---|
| G-M4-0 tape fidelity | **PASS** | 10/10 sessions: tape samples `==` accepted samples, zero gaps, and the tape's PCM digest equals the corpus WAV's digest over `[0, accepted)` — `0` differing samples |
| G-M4-1 terminal WER within `.010` of file | **PASS** | max distance `.003766` (and see R2 below — on that case the distance is a *rolling* arm's) |
| G-M4-2 terminal DER within `.020` of file | **FAIL** | 8/10 sessions at distance `0.000000`; `lex_adam_frank` at `.026667` / `.027000` |
| G-M4-3 terminal WER no worse than rolling | **PASS** | bill `.204545→.159091`, milei `.096000→.088000`, keyu `.093525→.064748`, 5-min `.082079→.050616`, 3-min unchanged |
| G-M4-4 v2 recall + matched-word speaker, no regression | **PASS** | every case at or above its rolling arm |
| G-M4-5 accepted `==` terminal accounted | **PASS** | 10/10, and the refused pass accounted for its 2 880 000 samples too |
| G-M4-6 async lifecycle `not_started→running→final` | **FAIL** | 8/10; `lex_adam_frank` ends `failed` |
| G-M4-7 a failure preserves and exports the rolling surface | **PASS** | fresh in-memory failure arm; and the scored batch is a *real* instance of it (below) |
| G-M4-8 cold and warm readiness reported separately | **PASS** | cold terminal decode `2.182 s` (RTF `.036`), warm RTF p50 `.035` over 9 sessions |
| G-M4-9 terminal replaces the surface exactly once, from sample 0 | **FAIL** | 8/10 apply exactly one revision `[0, accepted)`; `lex_adam_frank` applies none |
| G-M4-10 complete-tape retention | **PASS** | peak `accepted × 2` bytes (max `9 600 000` = the declared capacity), released after the terminal evidence, `0` bytes survive |
| G-M4-11 terminal never enters the capture clock | **PASS** | max combined RTF `.167161`, depth `≤ 1`, zero refusals / stale / failed windows, terminal starts one sequence number after `session_closed` in all 10 |
| G-M4-12 file mode byte-identical | **PASS** | six cases' hypotheses identical to their comparators; decoder A/B digest still `ad381d8b…` |
| G-M4-13 no terminal event carries a word of the meeting | **PASS** | 10/10; the only strings on those events are five PCM digests and `failed / final / finalized / rolling / running / segments_out_of_order` |

Gate-set contract: 14 preregistered, 14 scored, no extras, and every bound quoted verbatim from
its own row. `--selftest`: all 14 react.

## Per-case quality, both runs

| case | run | terminal WER | file WER | terminal DER | file DER |
|---|---|---:|---:|---:|---:|
| lex_bill_ackman | A/B | `.159091` | `.159091` | `.075500` | `.075500` |
| lex_javier_milei | A/B | `.088000` | `.088000` | `.151833` | `.151833` |
| lex_keyu_jin | A/B | `.064748` | `.064748` | `.079000` | `.079000` |
| lex_adam_frank | A | `.122411` | `.126177` | `.079889` | `.053222` |
| lex_adam_frank | B | `.122411` | `.126177` | `.080222` | `.053222` |
| keyu-5m | A/B | `.050616` | `.050616` | `.057933` | `.057933` |

Prediction P1 — "the terminal-vs-file delta is `0.000000` on every case and every axis, not
merely inside `.010`" — holds on every case that published: four of five, both runs, on all four
deployed axes. P2 holds: trio mean WER `.131357 → .103946`, five-minute `.082079 → .050616`.
The `lex_adam_frank` row is the rolling surface, because that meeting has no published terminal
surface.

## The finding: a terminal pass can reproduce the file arm and still be refused

`lex_adam_frank` is 180 s, so its terminal window plan is `[0, 150)` + `[120, 180)`. The pass
decoded 2 880 000 samples in `6.97 s`, produced **38 segments and 1507 generated tokens — the
file arm's own 38 segments and 1507 tokens** — and the session refused the revision:

```
text_revision_refused   refusal=segments_out_of_order  source=terminal  start=0 end=2880000
terminal_finalization_failed  outcome=finalized  applied=false  refusal=segments_out_of_order
```

`three-minute-seam.txt` names the pair: segment 25 is `[131.19, 136.29]` and segment
26 starts at `133.95` — **2.34 s before its predecessor ends**, at the seam between the two
windows. `LiveSession._text_revision_refusal` refuses any revision whose segments overlap
(`segment.start_sample < previous_end`), so file mode's own output is not admissible as a live
surface.

Three properties of this defect, measured rather than assumed:

1. **It is a publication defect, not a quality defect.** The decode converged; only the
   handover refused. The terminal accounting is complete (`tape_samples 2880000`, `tape_gaps 0`,
   `window_count 2`, `completed_windows 2`, `unattributed_segments 0`).
2. **It is rare and it needs a seam.** Scanning all 12 file arms in this batch: one overlapping
   pair, in the one two-window meeting. The 60 s cases have a single window and cannot have a
   seam; the 300 s case has three windows and no overlap.
3. **The failure path behaved exactly as E4 promised.** `finalization_status=failed`, the
   rolling surface survived intact and was exported (`live-hypothesis.jsonl` scores `.122411`),
   the tape was released after the evidence, the refusal is on the event stream by name, and the
   session still reports `status=succeeded` with exact accounting. This bundle is therefore also
   the first *deployed* instance of G-M4-7, which until now had only the in-memory arm.

## The disposition, and why it is an owner decision rather than a bound

On `lex_adam_frank` **the preregistered gate set cannot be satisfied by any surface**:

| surface published | G-M4-1 (`.010`) | G-M4-2 (`.020`) | G-M4-3 (WER ≤ rolling) | G-M4-4 (v2 ≥ rolling) |
|---|---|---|---|---|
| rolling (today, after the refusal) | pass `.003766` | **fail `.026667`** | pass (identical) | pass (identical) |
| terminal `==` file (had it published) | pass `0.000000` | pass `0.000000` | **fail `.003766`** | **fail `.001883`** |

That is D-M4-2's arithmetic again, on a different case and the other pair of axes: the
convergence bound and the no-regression bound point in opposite directions wherever file mode is
the worse arm on one axis and the better arm on another. Converging this meeting to file costs
**two words of 526** on WER and one word on content recall, and buys **`.026667` DER**
(`.079889 → .053222`), `+.026667` speaker accuracy, `+.024238` coverage, and `-.012130`
speech-region DER on the extent-free scorer. Every one of those seven numbers is published here
together, per D-M4-2's rule, and none of them is a reason to move a bound.

So the M4 exit reports, per PREREGISTRATION-M4 §8.4:

- **What is provably correct ships and is recorded**: 11 of 14 gates, four of five cases
  converged to `0.000000`, the tape/accounting/lifecycle/retention/leak/RTF/file-mode gates green
  on all 10 sessions.
- **The plan §18 E4 row stays UNSIGNED**, with this bundle as its evidence — the disposition
  M0(d) G2, M1 G-M1-1, M2 G-M2-4 and M3 D-M3-2 all received.
- **Two things are owed to the morning review**, and they are different in kind:
  **(a)** the seam refusal is a defect with a fix worth measuring (make the terminal proposal
  admissible without inventing timestamps — the campaign has never authorized padding, and
  §3.4's extent trap is the reason);
  **(b)** the `lex_adam_frank` gate collision is an owner ruling on which bound governs a case
  where file mode is worse on text and much better on speakers.
- **No plan §15 stop condition fired**: file mode unchanged, accounting exact, scorer self-tests
  green, no truth read during reconciliation, real time sustained, terminal audio available on
  every session. `.stop` is not warranted (§8.5).

## Readiness, cold and warm (G-M4-8)

| | terminal decode | decode RTF | stop → final |
|---|---:|---:|---:|
| cold (session 1 of the fresh process, `lex_bill_ackman/A`) | `2.182 s` | `.036372` | `2.613 s` |
| warm (9 sessions) | — | p50 `.035081`, p95 `.038011` | p50 `2.614 s`, max `11.011 s` |

P8 predicted cold would exceed warm "by the model-load time only". On this deployment there is
no model to load locally — the decoder is the remote vLLM endpoint and the file-mode runner is
built at process start — so cold sits **inside** the warm distribution. The cold session's own
pass decoded its file arm first (`arm_order = [file, live]`), which is the deployment's real
ordering, and is reported rather than engineered away.

## Reproduction

```bash
# the batch (needs the RUNNING service; ~27 min; restart first if a cold reading is wanted)
prototypes/streaming-diarization/live-convergence/run_paired_passes.sh /tmp/m4-exit-<stamp>
prototypes/streaming-diarization/live-convergence/run_paired_case.sh /tmp/m4-exit-<stamp> \
  adam3m lex_adam_frank \
  prototypes/streaming-diarization/data/real/calibration_diarization_3min/samples/lex_adam_frank
mkdir /tmp/m4-exit-<stamp>/three-minute && \
  mv /tmp/m4-exit-<stamp>/adam3m-{A,B} /tmp/m4-exit-<stamp>/three-minute/

# the gates (no GPU, no service, no MOSS request) -- against this bundle's own copy
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_m4_exit.py \
  --fresh-root evidence/live-convergence-0824/M4-e4-exit/passes --output /tmp/m4-gates.json

# every gate pushed past its own bound, from a converged fixture
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_m4_exit.py \
  --fresh-root evidence/live-convergence-0824/M4-e4-exit/passes --selftest
```

Scoring the checked-in copy reproduces the batch's own `gates.json` field for field, with one
exception: `G-M4-9.value.already_finalized_tests.tail`, which is the wall time of a pytest run.

## Files

| file | what it is |
|---|---|
| `gates.json` | the scored report: 14 gates, the gate-set contract, the five-case quality table, the batch order, the restart record |
| `console.txt` | the same run's stdout |
| `selftest.txt` | 14 reactions from the converged fixture, and the three gates the scored batch fails |
| `three-minute-seam.txt` | the overlapping pair, and every file arm in the batch scanned for it |
| `passes/` | the ten sessions, traces gzipped, plus `console/` and the restart record the batch was taken behind |
| `pytest-full.txt` | `1147 passed, 2 skipped, 396 subtests` |
| `file-mode-worktree.json` / `file-mode-hash.txt` | the decoder A/B probe against a HEAD worktree: `ad381d8b…`, unmoved across fourteen production changes |
