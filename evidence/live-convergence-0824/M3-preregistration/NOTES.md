# M3 preregistration - the comparator table E3 must be gated against

Campaign iteration 19, 2026-08-25. **A measurement and a contract, not a change**: no
production file was touched, and the full suite is unchanged at 1091 passed / 2 skipped /
392 subtests.

## Why this bundle exists

M3's PRD gates name the *pre-campaign* live arm (trio DER `.2235 / .1945 / .1112`, mean bound
`.1393`, `speaker_accuracy >= .8437`, five-minute DER `<= .0947`). The M2 exit measured the
surface actually served today - **with no E3 code at all** - at trio DER mean `.111278`,
`speaker_accuracy` mean `.888722`, five-minute DER `.088600`. Every PRD absolute bound is
already met by a build containing no speaker-authority work, so gating M3 against the stale
comparator would let the milestone pass by doing nothing.

`PREREGISTRATION-M3.md` therefore states every gate against **both** the PRD bound and the M2
exit measurement, binding on whichever is stricter. Every row is a strengthening; no PRD bound
is relaxed anywhere.

## What the measurement found

DER decomposed on the deployed live arm (false alarm is `0.000000` on all four cases):

| case | DER | miss | confusion | confusion-free floor | confusion share |
|---|---|---|---|---|---|
| lex_bill_ackman | `.127333` | `.090167` | `.037167` | `.090167` | 29.2 % |
| lex_javier_milei | `.117333` | `.117333` | `.000000` | `.117333` | 0.0 % |
| lex_keyu_jin | `.089167` | `.077000` | `.012167` | `.077000` | 13.6 % |
| keyu-5m | `.088600` | `.082700` | `.005900` | `.082700` | 6.7 % |

**E3's ceiling is now a number rather than a hope.** Only confusion is a label a speaker
authority could have got right; miss is speech nobody published, which no embedding recovers.
A perfect speaker authority that changed nothing else moves trio mean DER `.111278 -> .094833`
(`.016445`), and the five-minute case by at most `.005900`. Three quarters of the trio's whole
confusion budget (`.037167` of `.049334`) sits in `lex_bill_ackman`; `lex_javier_milei` has
exactly zero, so any DER movement there is a regression by construction.

Unattributed seconds and the collapse screen:

| case | S00 s | segments | intervals | mixed windows (deployed / sliding) | collapsed |
|---|---|---|---|---|---|
| lex_bill_ackman | `0.73` | 3 | 29.63-29.96, 39.84-40.00, 49.75-49.99 | 3 / 9 | **1** |
| lex_javier_milei | `0.00` | 0 | - | 0 / 3 | 0 |
| lex_keyu_jin | `0.00` | 0 | - | 3 / 9 | 0 |
| keyu-5m | `0.56` | 1 | 150.08-150.64 | 5 / 27 | 0 |

The single collapsed window is `lex_bill_ackman` `[20.0, 30.0)`: the reference carries Bill
(20-29 s) and Lex (29-30 s, exactly at the 1.0 s birth floor) and the surface names only `S01`
there - the second voice IS detected, but published as `S00` at 29.63-29.96. Every S00 fragment
on both cases is 0.16-0.56 s, below the 0.5 s matching floor: plan §11.4 microfragments, a
separate candidate, not M3.

Both passes of every case agree to 6 dp on DER, miss, confusion, `speaker_accuracy`,
matched-word accuracy and S00 seconds (`runs_agree: true`, four of four cases).

## Two collapse screens, and why

The deployed screen is alignment-dependent: `lex_javier_milei`'s only reference turn falls
exactly on a 10 s window boundary, so the deployed grid reports **no** mixed window on that case
at all - a fact about the alignment, not about speaker health. The sliding screen keeps the
10 s window but hops by the deployed base-span cadence (2.5 s, read from each pass's own
`replay-manifest.json`), so it slides past every turn: 9 / 3 / 9 / 27 mixed windows instead of
3 / 0 / 3 / 5. Both are reported; **the gates use the sliding screen**.

## Instrument integrity

`--selftest` proves the two derived quantities react before any arm is measured against them,
and four mutations prove the self-test is not vacuous - each flips one rule and is caught by its
own check:

| mutation | caught by |
|---|---|
| `S00` counts as a published speaker name | "unattributed is not a name" |
| the second voice needs no evidence floor | "a voice below the birth floor is not a second voice" |
| the confusion-free floor forgets false alarm | "confusion-free floor" |
| a window nobody published counts as collapsed | "nothing published -> mixed but not collapsed" |

Every rule the instrument applies is read from production rather than spelled in the prototype:
`UNATTRIBUTED_SPEAKER` (`live_surface`), `DEFAULT_ROLLING_GEOMETRY`
(`app.live_transcript_convergence`), `ALBUM_BIRTH_MIN_SECONDS` (`app.live_identity_album`), and
the base-span hop from the pass manifest's `hard_cap_samples`. A production change moves the
measurement instead of silently disagreeing with it. The one deliberate refusal: a missing
`hard_cap_samples` raises rather than falling back to the stride, because that fallback would
silently turn the sliding screen back into the deployed one - which is exactly the bug the
first run of this driver had.

## Files

- `../../../prototypes/streaming-diarization/live-convergence/PREREGISTRATION-M3.md` - the
  contract: arms, 14 gates with their bounds and clocks, 7 predictions, the selection and
  disposition rules
- `baseline.json`, `baseline-console.txt` - the comparator table, per case per pass per arm
- `selftest.txt` - the instrument's own check
- `mutations.txt`, `mutations/*.diff` - the four-mutation sweep
- `pytest-identity-floor.txt` - `tests/test_live_identity_real_corpus.py`, 3 passed (G-M3-6's
  baseline, green before any E3 work)
- `sha256.txt`

## Reproduce

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m3_baseline.py \
  --output /tmp/m3-baseline.json
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m3_baseline.py --selftest
```

No GPU, no service, no MOSS request: the table is re-derived from the checked-in M2 exit passes.
