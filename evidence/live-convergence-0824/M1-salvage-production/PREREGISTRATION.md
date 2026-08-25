# Preregistration — M1 paired rerun (plan E1 exit)

Written **before** any measurement pass on the M1 build, per the standing steering note at the
iteration 4→5 boundary of `scripts/ralph-live-convergence/progress.txt`. Nothing below may be
changed after a number is seen.

## What is being measured

The deployed dev `web_cli`, restarted onto the campaign branch with M1 salvage shipped, over the
paired corpus: the 1-minute trio (`lex_bill_ackman`, `lex_javier_milei`, `lex_keyu_jin`) and the
5-minute case (`benchmark_5m/lex_keyu_jin`). Same two drivers as M0d, unchanged:

    prototypes/live-file-gap-baseline-20260824/remeasure_live_vs_file.py <out>
    prototypes/live-file-gap-baseline-20260824/remeasure_5m_case.py <out>

## Protocol, fixed now

- **Passes.** Two fresh trio passes and two fresh 5-minute passes, sequential, one in-flight
  request, same order as M0d (trio A, trio B, 5m A, 5m B).
- **Warm-up.** One discarded decode request is issued before each pass. Adopted here, for the
  campaign, on the M0d measurement: the deployed decoder's only observed non-determinism was a
  cold-start flip (12 identical warm requests, 2 distinct outputs after a ~3-minute idle gap;
  `evidence/live-convergence-0824/M0d-paired-reacquisition/`). This is instrument hygiene, not a
  result-dependent choice, and it is fixed for every later milestone.
- **Aggregation.** The reported per-case number is the **mean of the two passes**. The trio mean
  is the mean of the three per-case means. No pass is dropped for any reason.
- **Attribution before verdict.** Any per-case delta is attributed with
  `diff_live_runs.py` (span bounds identical? decode flip? identity cascade?) *before* it is
  called a regression or an improvement. A delta whose whole cause is a single decode flip is
  reported as noise with its span id, and the noise floor cited is the measured one: 1 differing
  decode in 115 spans, extents moving ±10–20 ms (one webrtcvad frame) even when every span and
  decode match (F4).

## Gates (from the PRD, immutable)

| id | gate | comparator |
| --- | --- | --- |
| G-M1-1 | trio live WER `<= .190` | prototype projection `.1885` |
| G-M1-2 | no per-case live WER regression | baseline live bill `.2614` / milei `.1440` / keyu `.1942` |
| G-M1-3 | file mode byte-identical | M0d file arms |
| G-M1-4 | zero extra MOSS requests | decode count per case equals the M0d pass |
| G-M1-5 | no refusal boilerplate and no digital-silence words published | published transcripts |
| G-M1-6 | identity preparation receives only salvager-emitted intervals | trace |

## Predictions, recorded now

- The projection says **exactly one span moves**: `lex_bill_ackman#02`, 8 words, WER
  `.2614 → .2273`. milei and keyu are predicted **unchanged** (`.1440`, `.1942`); the two other
  salvage-eligible spans in the wider corpus belong to cases outside the trio.
- Trio live WER predicted `.1885`; v2 content recall `.9267`.
- `canonical_decode_salvage` predicted present on ~10 spans per trio pass at most: 1 `salvaged`
  (bill 02) and the `refused_gate` spans (milei 3/5/13/31).
- 5-minute case: **no prediction**. Its span corpus was never in the §9.2 set, so whatever it
  does is new evidence, and it is reported rather than gated by G-M1-1/2.

## Stop rule

A G-M1-1 or G-M1-2 failure that survives attribution is a hard gate failure: write the failure
evidence, a `BLOCKED:` entry, and create `scripts/ralph-live-convergence/.stop`. Re-rolling the
passes for a greener number is forbidden.
