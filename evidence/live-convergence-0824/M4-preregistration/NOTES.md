# M4 preregistration - what a terminal pass must land on, measured before it exists

Campaign iteration 22, 2026-08-25. **No production file was touched.** This bundle fixes M4's
gates, comparators, decisions, predictions and risks before plan E4's terminal finalizer exists,
and it records the comparator table those gates are written against.

Artefacts:

| file | what it is |
|---|---|
| `../../../prototypes/streaming-diarization/live-convergence/PREREGISTRATION-M4.md` | the preregistration itself: 3 preconditions, 3 decisions, **14 gates**, 8 predictions, 4 risks |
| `m4-baseline.json` | the full comparator table, machine-readable |
| `console.txt` | `measure_m4_baseline.py` exit 0 - the table as read |
| `selftest.txt` | `measure_m4_baseline.py --selftest` - 0 failures, every derived quantity reacts |
| `pytest-full.txt` | the suite, unchanged by this iteration |
| `sha256.txt` | digests of everything above; paths are repo-root-relative, so `shasum -a 256 -c` verifies the whole bundle from the repo root in one command |

## 1. The headline

M4 is the only milestone in this campaign that gates against a **target** rather than a
no-regression bound: plan G8 (`terminal WER within .010 of the paired file arm`) and the
owner-directed prerelease companion (`terminal DER within .020`). The comparator is the file arm
of the *same pass*, and it is stable - identical to the pre-campaign file arm on all four scored
axes and all four cases that have a pass, across the campaign's eight production changes.

If terminal lands on it: **trio mean WER `.131357 -> .103946`** and **five-minute
`.082079 -> .050616`**. That is the largest single text move left on the ladder.

## 2. Three findings that had to be recorded before the numbers

**F1 - two of the ten convergence readings are already satisfied by a build that ships nothing.**
`lex_javier_milei` WER sits `+.008000` from its file arm against a `.010` tolerance;
`lex_keyu_jin` DER sits `+.010167` against `.020`. G-M4-1 on milei and G-M4-2 on keyu therefore
cannot, by themselves, demonstrate that a terminal pass did anything. The instrument prints
`ALREADY INSIDE` for exactly those two rows, and the M4 verdict must repeat it beside them - the
same honesty clause M3's disposition carried, reached from the opposite direction.

**F2 - converging to file is a REGRESSION on one case, and the arithmetic forbids gating it.** On
`lex_javier_milei` the file arm is worse than the rolling surface by `+.034500` DER, `-.034500`
speaker accuracy and `-.036069` coverage. Every one of those exceeds the convergence tolerance, so
a no-regression gate on those axes is *arithmetically incompatible* with the PRD bound: every
value within `.020` of `.151833` is `>= .131833`, and the rolling surface already publishes
`.117333`. A campaign gate may only strengthen a PRD bound, so these three are recorded as a
decision (D-M4-2), never as gates.

**F3 - the extent-free axes say four fifths of that regression is the metric.** Evaluator v2 over
VAD speech regions: terminal == file costs `lex_javier_milei` `0.000000` content recall,
`0.000000` matched-word speaker accuracy and `+.007255` speech-region DER, while *gaining* `.008`
WER. On every other case v2 improves on every axis. The deployed DER charges silence inside a
gapless turn to whoever published the long segment (plan §3.4) and file mode's 150 s windows
publish exactly those. So D-M4-2 accepts the deployed-metric regression and requires all seven
numbers to be published together - never the trio mean alone.

## 3. What the milestone cannot start without

- **P-M4-A. `lex_adam_frank` (3 min) has no live pass in this campaign.** No paired file arm, no
  rolling arm, no comparator. Until it is acquired under the warm-decoder protocol, M4 gates
  **3 of 5** cases. The instrument prints `MISSING COMPARATOR` rather than omitting the row.
- **P-M4-B. No session retains a complete tape today.** `live_tape.py`'s disk store is opt-in
  (ADR-0003 D2), the deployed service declares no root, and the rolling ring is bounded at
  `2 x window` and released at `RollingTranscriptConverger.stop`. Plan §12.1 requires the tape.
- **P-M4-C. The three §7.4 terminal events have no producers**, and `finalization_status` reaches
  only `final`.

## 4. Structural facts read from production, not asserted

| case | duration | terminal windows (`plan_windows` @ `WindowedRunner` 150/120) | complete tape | accepted samples |
|---|---:|---|---:|---:|
| trio (each) | 60 s | **1** - `[0, 60)`, the un-windowed delegate path | 1 920 000 B | 960 000 |
| lex_adam_frank | 180 s | **2** - `[0, 150)`, `[120, 180)` | 5 760 000 B | (not yet run) |
| keyu-5m | 300 s | **3** - `[0, 150)`, `[120, 270)`, `[240, 300)` | 9 600 000 B | 4 800 000 |

Two consequences. On the trio, terminal is the *same call* file mode makes, so `terminal == file`
is an identity there rather than an approximation - which is why P1 predicts a delta of exactly
`0.000000` on every case, not merely one inside `.010`. And Appendix B Q10's premise holds with
margin at **9.155 MiB**, which is what makes D-M4-1 (the tape lives in memory, not on the opt-in
disk store) safe: enabling the disk store would change the deployment posture every gate in this
campaign was measured against.

## 5. How this preregistration is kept honest

- Every bound in §5 of the preregistration is either quoted from the PRD/plan or is a measured
  value from `m4-baseline.json`; the gate ids parse out of the table with the same regex
  `verify_m3_disposition.py` uses on M3's, so a later scorer can be held to the document.
- `--selftest` proves each derived quantity reacts before any terminal number is measured against
  it: a distance inside/outside/exactly at a tolerance, a satisfiable vs unsatisfiable
  no-regression gate on both directions of "better", the window plan at all three durations read
  from production constants, the tape budget, and a missing summary returning `None` rather than
  zero.
- Risks are recorded with their headroom: **R1** notes that G-M4-4 has *zero* slack on
  `lex_javier_milei` (both v2 axes are `.920000` on both arms). Inventing slack would be the
  tuning the PRD forbids, so the bound is the measurement and the disposition of a hairline miss
  is an owner decision, not a re-run.

## 6. Reproduction

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m4_baseline.py \
  --output /tmp/m4-baseline.json
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m4_baseline.py --selftest
```

No GPU, no service, zero MOSS requests. The 4070 Ti was not touched; no service was restarted.
