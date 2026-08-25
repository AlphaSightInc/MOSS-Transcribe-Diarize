# Preregistration - M4 (plan E4 rescoped): terminal file-quality convergence

Written 2026-08-25, campaign iteration 22, **before any terminal finalizer exists**. Everything
below is fixed: no bound, comparator, clock or case may be re-decided once a number is seen. The
PRD's rule is verbatim - *"Preregistered gates are immutable mid-run: no tuning thresholds to
pass, no adding arms beyond the grid."*

Scope: plan §12.3 steps 1-7, gated on trio + `lex_adam_frank` (3 min) + `benchmark_5m/lex_keyu_jin`
(5 min) per Appendix B's §12.2 rescope. The 30/60-minute matrix and the two-session concurrency arm
are deferred by Appendix B and are **not** in this milestone.

---

## 1. Why the comparator is the paired file arm, and what it already is

M4 is the only milestone in this campaign whose gates name a **target surface** rather than a
no-regression bound. Plan G8 and the owner-directed prerelease companion both read
*"within X absolute of the paired file arm"*, and "paired" is load-bearing: the comparator is the
file arm the deployed service produced **in the same pass, from identical audio bytes**, not the
pre-campaign baseline and not the rolling surface.

That comparator is stable. The file arm measured at the M2 exit (iteration 18) is identical to the
file arm measured pre-campaign on all four scored axes (WER, DER, speaker accuracy, coverage) and
on all four cases that have a pass: `file_arm_stable_since_precampaign = True` for
`lex_bill_ackman`, `lex_javier_milei`, `lex_keyu_jin`, `keyu-5m`. The campaign has shipped eight
production changes over that span and the file surface has not moved (G-M2-8, and the decoder A/B
digest `ad381d8b…`).

The table M4 is preregistered against, from `measure_m4_baseline.py` over
`evidence/live-convergence-0824/M2-e2-exit/passes/` (two passes per case, `runs_agree = True` on
all four):

| case | arm | WER | DER | speaker_accuracy | coverage | v2 recall | v2 matched-word |
|---|---|---|---|---|---|---|---|
| lex_bill_ackman | file | `.159091` | `.075500` | `.924500` | `.952215` | `.931818` | `.931818` |
| lex_bill_ackman | rolling | `.204545` | `.127333` | `.872667` | `.916587` | `.926136` | `.920455` |
| lex_javier_milei | file | `.088000` | `.151833` | `.848167` | `.870992` | `.920000` | `.920000` |
| lex_javier_milei | rolling | `.096000` | `.117333` | `.882667` | `.907061` | `.920000` | `.920000` |
| lex_keyu_jin | file | `.064748` | `.079000` | `.921000` | `.936387` | `1.000000` | `1.000000` |
| lex_keyu_jin | rolling | `.093525` | `.089167` | `.910833` | `.925500` | `.985612` | `.985612` |
| **trio mean** | file | **`.103946`** | **`.102111`** | **`.897889`** | `.919865` | - | - |
| **trio mean** | rolling | **`.131357`** | **`.111278`** | **`.888722`** | `.916383` | - | - |
| keyu-5m | file | `.050616` | `.057933` | `.942067` | `.952109` | `.972640` | `.972640` |
| keyu-5m | rolling | `.082079` | `.088600` | `.911400` | `.918924` | `.957592` | `.954856` |
| **lex_adam_frank** | **-** | **NO LIVE PASS IN THIS CAMPAIGN** | | | | | |

`v2 recall` and `v2 matched-word` are `evaluator_v2.score_v2` over WebRTC VAD speech regions
(`webrtcvad_mode1_10ms`) - the extent-free axes plan §3.4 exists to introduce.

## 2. What terminal can reach, and what it costs, measured before it is built

**The prize, on text.** Terminal replaces the rolling surface with a 150/120 pass over the same
audio. If it lands on its comparator, trio mean WER goes `.131357 -> .103946` (`-.027411`) and the
five-minute case `.082079 -> .050616` (`-.031463`). That is the largest single text move available
in this campaign and it is the whole reason E4 is on the ladder.

**Two gates cannot see a terminal pass at all.** `measure_m4_baseline.py` scores each convergence
bound against the surface shipped **today**, and two are already inside:

| case | axis | rolling | file | distance | tolerance | reading |
|---|---|---|---|---|---|---|
| lex_javier_milei | WER | `.096000` | `.088000` | `+.008000` | `.010` | **ALREADY INSIDE** |
| lex_keyu_jin | DER | `.089167` | `.079000` | `+.010167` | `.020` | **ALREADY INSIDE** |
| lex_bill_ackman | WER | `.204545` | `.159091` | `+.045454` | `.010` | must move |
| lex_bill_ackman | DER | `.127333` | `.075500` | `+.051833` | `.020` | must move |
| lex_keyu_jin | WER | `.093525` | `.064748` | `+.028777` | `.010` | must move |
| lex_javier_milei | DER | `.117333` | `.151833` | `-.034500` | `.020` | must move (see below) |
| keyu-5m | WER | `.082079` | `.050616` | `+.031463` | `.010` | must move |
| keyu-5m | DER | `.088600` | `.057933` | `+.030667` | `.020` | must move |

A build that ships nothing passes `G-M4-1` on `lex_javier_milei` and `G-M4-2` on `lex_keyu_jin`.
That is the same honesty clause M3's disposition carried, arrived at from the other direction, and
the M4 report must repeat it beside the verdicts.

**Converging to file is a REGRESSION on one case, and the arithmetic says a no-regression gate
there is impossible.** On `lex_javier_milei` the file arm is *worse* than the rolling surface on
three deployed axes, by more than the tolerance in every case:

| axis | rolling | file | cost of terminal == file | can a no-regression gate coexist with the convergence bound? |
|---|---|---|---|---|
| DER | `.117333` | `.151833` | `+.034500` | **no** - every value within `.020` of `.151833` is `>= .131833` |
| speaker_accuracy | `.882667` | `.848167` | `-.034500` | **no** |
| text_coverage | `.907061` | `.870992` | `-.036069` | **no** |

A campaign gate may only ever *strengthen* a PRD bound (§1 of PREREGISTRATION-M3). These three
cannot, so they are **not gates**; they are decision D-M4-2 below, decided here, before the number
exists.

**The extent-free reading resolves it.** The deployed DER charges silence inside a gapless turn to
whoever published the long segment - plan §3.4's artifact - and file mode's 150 s windows publish
exactly those long segments. Evaluator v2, on VAD speech regions, says what terminal == file
actually costs:

| case | v2 WER | v2 content recall | v2 matched-word speaker | v2 DER (speech regions) | worse on |
|---|---|---|---|---|---|
| lex_bill_ackman | `-.045454` | `+.005682` | `+.011363` | `-.035926` | nothing |
| lex_javier_milei | `-.008000` | `+.000000` | `+.000000` | `+.007255` | v2 DER only |
| lex_keyu_jin | `-.028777` | `+.014388` | `+.014388` | `-.010134` | nothing |
| keyu-5m | `-.031463` | `+.015048` | `+.017784` | `-.022016` | nothing |

On the axes that cannot be gamed by segment extent, `lex_javier_milei` loses **exactly nothing**:
content recall and matched-word speaker accuracy move by `0.000000`, and its text improves by
`.008`. Its residual v2 speech-region DER cost is `+.007255`, a fifth of the `.034500` the deployed
metric reports. Four fifths of that headline regression is the metric, not the surface.

**Structural facts, read from production rather than asserted** (`WindowedRunner.window_seconds`
= 150, `stride_seconds` = 120, `plan_windows`, `LIVE_SAMPLE_RATE`, `PCM16_BYTES_PER_SAMPLE`):

| case | duration | terminal windows | window plan | complete tape | accepted samples |
|---|---:|---:|---|---:|---:|
| trio (each) | 60 s | **1** | `[0, 60)` - the un-windowed delegate path | 1.831 MiB | 960 000 |
| lex_adam_frank | 180 s | **2** | `[0, 150)`, `[120, 180)` | 5.493 MiB | (not yet run) |
| keyu-5m | 300 s | **3** | `[0, 150)`, `[120, 270)`, `[240, 300)` | 9.155 MiB | 4 800 000 |

Two consequences. First, on the trio the terminal pass is the *same call* file mode makes, so
`terminal == file` there is an identity, not an approximation - which is what
`prototypes/live-file-gap-context/` already measured. Second, Appendix B Q10's premise holds with
margin: the largest complete tape in scope is **9.155 MiB**, so the tape can be a session-lifetime
buffer in memory (D-M4-1).

## 3. Preconditions - a gate scored without these is void

- **P-M4-A. The three-minute comparator does not exist.** `lex_adam_frank` has never been run
  through the live path in this campaign; there is no paired file arm and no rolling arm for it.
  Until a paired pass exists under the warm-decoder protocol (`run_paired_passes.sh`'s shape: one
  discarded decode, then the scored pass, twice), M4 gates **3 of 5** cases and the milestone
  cannot close. Acquiring it is M4's first measured step, and the driver that acquires it must be
  the checked-in paired driver's shape, not a new instrument.
- **P-M4-B. A complete mixed tape must exist.** Plan §12.1 requires it and no session retains one
  today: `live_tape.py`'s disk store is opt-in (ADR-0003 D2), the deployed service declares no
  root, and the rolling ring is bounded at `2 x window` and is explicitly released at
  `RollingTranscriptConverger.stop`. G-M4-0 is scored against the tape, so no tape means no M4.
- **P-M4-C. The three §7.4 terminal events need producers.** `terminal_finalization_started` /
  `_completed` / `_failed` are named in the contract and have no producer (iteration 15 deliberately
  left them to E4). `finalization_status` reaches only `final` today; `running` / `failed` /
  `unavailable` have no producer either (iteration 12).

## 4. Decisions, made before any number exists

- **D-M4-1 - the tape lives in memory.** Appendix B Q10 says "memory or disk"; this campaign takes
  memory. The disk store is opt-in behind a declared root with ADR-0003 D4's refusals, and turning
  it on would change the deployment posture **every gate in this campaign was measured against**
  (ADR-0003 D2 is explicit that this must not arrive as a side effect). The whole retained tape is
  `<= 9.155 MiB` at the 5-minute cap. Its record is a refinement of ADR-0003, not a new ADR (PRD).
  If a later deployment wants the disk store, the terminal reader must not care which it is: the
  seam is "give me `[0, meeting_end)` of mixed PCM".
- **D-M4-2 - `lex_javier_milei`'s deployed-metric regression is accepted, and reported in full.**
  Terminal == file costs that case `+.034500` DER, `-.034500` speaker accuracy and `-.036069`
  coverage on the deployed scorer, while costing `0.000000` content recall, `0.000000` matched-word
  speaker accuracy and `+.007255` speech-region DER on the extent-free one, and *gaining* `.008`
  WER. The campaign's mission is convergence toward the paired file arm; a no-regression gate on
  those three axes is arithmetically incompatible with the PRD bound (§2). The disposition is to
  proceed and to publish all seven numbers together in the M4 evidence and in the plan §18 row -
  never the trio mean alone.
- **D-M4-3 - asynchronous finalization with snapshot polling.** Plan §12.3 asks reviewers to choose
  between async-with-polling and a separate `finalize` action and recommends the former; the
  snapshot already carries `finalization_status` and clients already poll it. No new endpoint.

## 5. Gates

`[PRD]` = named by the PRD's M4 milestone or plan G8-G10. `[C]` = campaign gate, **stricter** than
the PRD, added because a PRD bound is otherwise unfalsifiable (§2) or because the axis has no bound
at all.

| id | gate | bound |
|---|---|---|
| G-M4-0 `[C]` | **Tape fidelity**: the retained mixed tape is a faithful record of what the session accepted - sample count `== accepted_samples`, zero gaps, and its PCM digest equals the digest of the mixed stream the transport accepted. Verified from the tape and the session's own accounting, not asserted. The corpus-WAV comparison (differing samples, max absolute delta) is reported beside it, because it is what explains any G-M4-1 delta. | equality, zero gaps |
| G-M4-1 `[PRD G8]` | terminal WER within `.010` absolute of the **paired file arm of the same pass**, per case, all five | `abs(terminal - file) <= .010` |
| G-M4-2 `[PRD prerelease]` | terminal DER within `.020` absolute of the paired file arm, per case, all five | `abs(terminal - file) <= .020` |
| G-M4-3 `[C]` | terminal WER no worse than the rolling surface it replaces, per case (this is a strengthening everywhere and binds only on `lex_javier_milei`, where `.010` of convergence tolerance reaches past the rolling value) | bill `<= .204545`, milei `<= .096000`, keyu `<= .093525`, 5m `<= .082079`, 3-min `<=` that pass's own rolling arm |
| G-M4-4 `[C]` | evaluator-v2 content recall **and** matched-word speaker accuracy, per case, no regression vs the rolling arm of the same pass. These are the axes segment extent cannot move, and they are the only speaker evidence D-M4-2 rests on, so they must be gated rather than reported | bill `>= .926136` / `>= .920455`; milei `>= .920000` / `>= .920000`; keyu `>= .985612` / `>= .985612`; 5m `>= .957592` / `>= .954856`; 3-min `>=` that pass's own rolling arm |
| G-M4-5 `[PRD G10]` | accepted samples `==` terminal accounted samples, exactly, every session | equality |
| G-M4-6 `[PRD §12.3]` | asynchronous lifecycle: `finalization_status` goes `not_started -> running -> final`; the stop request returns **before** terminal completes; the snapshot stays readable and serves the rolling surface for the whole `running` interval | as stated |
| G-M4-7 `[PRD E4 exit]` | a terminal failure preserves and exports the rolling surface with `finalization_status=failed`: the export is non-empty and equal to the rolling surface, and the failure is on the event stream | as stated |
| G-M4-8 `[PRD §12.2]` | cold and warm model readiness reported separately, per scored session | both reported |
| G-M4-9 `[C]` | terminal replaces the surface **exactly once**, from sample 0, over `[0, meeting_end)`; a second terminal proposal is refused `already_finalized` (the existing `_text_revision_refusal` name) | as stated |
| G-M4-10 `[C, Appendix B Q10]` | complete-tape retention: the tape covers the whole session, is released after terminal finalization evidence is written, zero tapes survive the session, and peak retained bytes `<= 9 600 000` (the 5-minute cap) | as stated |
| G-M4-11 `[C]` | terminal work never enters the capture clock: during capture the combined RTF stays `< 1` with the M2-exit queue bounds (depth `<= 1`, zero admission refusals, zero stale completions, zero failed windows), and the terminal pass begins only after capture stops | as stated |
| G-M4-12 `[PRD constraint / G9]` | file mode byte-identical, **both** readings: (a) every pass's `file-hypothesis.jsonl` equals `prototypes/live-file-gap-baseline-20260824/`'s, as G-M2-8 and G-M3-12 check; (b) the decoder A/B probe against a HEAD worktree still hashes `ad381d8bd247e4a8ebe56240dfbc29c0b5a86ffb35a2fcb411c07bbd5b7707f2` | both hold |
| G-M4-13 `[C]` | no §7.4 terminal event carries transcript text - counts, samples, timings and typed names only, as `verify_rolling_events.py` G4 already reads the vocabulary from production | zero |

Clocks and instruments, fixed here:

- WER / DER / `speaker_accuracy` / coverage: the **deployed** scorer's `results.json`, produced by
  the paired driver against the running service - the same path M1, M2 and M3 exited through. Two
  passes per corpus; per-pass values shown; a mean is never quoted without its per-case row.
- content recall and matched-word speaker accuracy: `evaluator_v2.score_v2` with WebRTC VAD speech
  regions (`webrtcvad_mode1_10ms`).
- accounting, queues, RTF, lifecycle, events: the §7.4 event stream plus the run summary, read
  exactly as `verify_m2_exit.py` reads them.
- cold vs warm readiness: measured on the same clock as the pass, cold = the first terminal pass
  after a service restart, warm = a terminal pass in a service that has already finalized once.

## 6. Predictions

Falsifiable, recorded before the finalizer exists. Being wrong is a finding, not a failure.

- **P1** With a faithful tape and a warm decoder, the terminal-vs-file delta is **`0.000000`** on
  every case and every axis - not merely inside `.010`. Terminal runs the identical
  `WindowedRunner` over identical audio; the only ways to get a nonzero delta are a tape defect
  (G-M4-0 catches it) or the decoder's measured non-determinism (M0d), and those two are
  distinguishable by which gate moves.
- **P2** Trio mean WER lands at `.103946` and the five-minute case at `.050616`.
- **P3** `lex_javier_milei` DER rises to `.151833`, speaker accuracy falls to `.848167`, coverage
  falls to `.870992` - and G-M4-2 still passes with delta `0`. G-M4-4 passes at exactly its bound
  (zero headroom, see R1).
- **P4** Trio mean DER falls `.111278 -> .102111`; trio mean speaker accuracy rises
  `.888722 -> .897889`. The trio mean improves on **both** speaker axes while one case regresses on
  both, which is why the report may not quote means alone.
- **P5** Peak retained tape is 1 920 000 / 5 760 000 / 9 600 000 bytes at 60 / 180 / 300 s, and the
  process high-water is within 5 % of that (one buffer, no second copy).
- **P6** The terminal pass plans 1 / 2 / 3 windows at 60 / 180 / 300 s, and the trio's terminal pass
  takes the single-window delegate path.
- **P7** `lex_adam_frank`'s rolling WER lands between the trio's `.131357` and the five-minute
  case's `.082079`: boundary seams are a shrinking share of a longer meeting.
- **P8** Cold terminal readiness exceeds warm by the model-load time only; the terminal pass itself
  is warm by construction, because it runs seconds after a meeting the same service just decoded.

## 7. Risks recorded before the numbers

- **R1 - G-M4-4 has zero headroom on `lex_javier_milei`.** Its v2 content recall and matched-word
  speaker accuracy are `.920000` on both arms; the gate is `>=`, so any hairline movement fails it.
  That is deliberate - the bound is the measurement, and inventing slack is the tuning the PRD
  forbids - but if it fires, the disposition is an owner decision recorded with the decoder-noise
  evidence, not a re-run until it passes.
- **R2 - two convergence gates are already satisfied by a build that ships nothing** (§2). Their
  passing is not evidence that terminal did anything, and the M4 report states that beside them.
- **R3 - the deployed decoder is not a function** (M0d, `probe_decode_determinism.py`). Terminal is
  warm by construction; the *file* arm is the one at risk, and the pass warm-up is its only
  mitigation. A nonzero G-M4-1 delta with a clean G-M4-0 is a decoder reading, and must be reported
  as one rather than as terminal quality.
- **R4 - three of five gated cases exist today** (P-M4-A). Any M4 verdict written before
  `lex_adam_frank` is acquired covers 3 cases and must say so in the same sentence.

## 8. Selection and disposition

1. Acquire the three-minute paired comparator (P-M4-A), then build to plan §12.3 steps 1-7.
2. **M4 closes iff every gate above passes on a fresh pass of all five cases.**
3. A gate miss is answered by evidence, never by moving a bound, adding a case, or re-running until
   the number falls the right way.
4. If a gate cannot pass, M4 ships what is provably correct and leaves the plan §18 E4 row
   **unsigned**, with the measurement and the failure written to
   `evidence/live-convergence-0824/M4-*/`. That is the disposition M0(d) G2, M1 G-M1-1, M2 G-M2-4
   and M3's D-M3-2 all received.
5. `.stop` is reserved for a plan §15 **global** stop condition: ambiguous corpus provenance, a
   failing scorer self-test or degenerate control, truth read during reconciliation, a promoted
   authority regressing case-level WER without an accepted trade-off, file mode changing,
   accepted/accounted equality failing, real time not sustained, or **terminal audio unavailable**
   (the one §15 condition M4 can trip directly: a tape that cannot be retained is not a gate miss,
   it is the phase's precondition failing).

## 9. Reproduction

```bash
# the comparator table this preregistration is written from (no GPU, no service)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m4_baseline.py \
  --output /tmp/m4-baseline.json

# prove every derived quantity reacts before trusting it
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m4_baseline.py --selftest

# the same instrument, pointed at a pass root that contains a terminal arm
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m4_baseline.py \
  --passes-root /tmp/m4-terminal-<stamp> --output /tmp/m4-terminal.json
```
