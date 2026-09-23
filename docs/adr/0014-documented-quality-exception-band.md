# ADR-0014: The documented quality exception becomes executable

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** Phase-2 acceptance, gate G4 (`quality_corpus`)

## Context

The release mandate rules that a quality macro landing **within 5 % relative** of its
`QUALITY_BOUNDS` value, on a fully finalized clean run, is a documented exception rather than a
rejection. That ruling was recorded in the mandate and in issue #10 and applied by hand when
reading each round's report. It was never expressed in code.

The evaluator therefore applied the strict bounds unconditionally. Every round from 12 onward
reported `quality_corpus` as failed on the same three macros, and a human then re-read the numbers
and ruled them acceptable. That was tolerable for `--terminal restored` rounds, whose result is a
report. It is not tolerable for `--terminal preadmission`, which is the only command that leaves a
candidate serving: the gate rejected before reaching G7, so **the attended canary was unreachable**
and no candidate could ever be admitted while those three macros sat outside their bounds.

The 2026-09-13 pre-admission run made this concrete. Every other gate passed on both layers — G0,
G1, G2, G3, G5, G6, G8, G9, G10, all 19 deployed and 17 pre-admission predicates executed, nothing
crashed — and the run was rejected on:

| macro | reported | bound | relative |
|---|---|---|---|
| `diarization_error_rate` | 0.162548 | max 0.161430 | +0.69 % |
| `reference_speech_der` | 0.135590 | max 0.134804 | +0.58 % |
| `matched_speaker_accuracy` | 0.911502 | min 0.911512 | −0.0011 % |

Two hours of measurement, discarded over a matched-speaker miss of one part in ninety thousand that
the mandate had already ruled acceptable.

## Decision

`quality_bound_status` classifies each macro as **strict**, **exception**, or **failed**.
`_validate_quality` rejects only `failed`. `QUALITY_EXCEPTION_RELATIVE_TOLERANCE = 0.05` expresses
the ruled band; the boundary is inclusive, and the division that computes it is protected against
rounding pushing an exactly-5 % result out of the band. That guard is a relative comparison at
`rel_tol=1e-9`, so the admitted band is 5 % plus roughly 5e-11 relative rather than 5 % exactly —
stated here because "exactly 5 %" would be false. The slack is eleven orders of magnitude below the
smallest margin any real run has produced.

**`QUALITY_BOUNDS` is not edited.** The bounds keep their meaning: a macro outside one is a miss.
What changes is only whether a miss of ruled size rejects the candidate.

An admitted exception is **named**. `quality_exception_records` emits one record per admitted macro,
carrying the value, the bound, the relative distance and the tolerance, and the verdict gains a
`quality_exceptions` field. A passing verdict therefore states every exception it rests on. An
exception is never silent, and `_quality_failure_details` no longer reports an admitted macro as a
failure reason when a run fails for some other cause.

The exception is reachable only after the run proves itself **structurally**: six cases, two passes,
twelve sessions, 122 windows, ≥ 1239.987 s of audio, twelve per-case rows, six input identities with
every check true and matching source audio and reference, a macro that recomputes from the per-case
rows, and duration-weighted and per-category projections that agree. Those checks run first and are
unchanged. The tolerance excuses distance from a bound; it excuses nothing about completeness,
provenance or consistency.

**What the evaluator does not itself prove.** "Fully finalized and clean" is enforced by the
*producer*, not by this function. `_quality_validation` never reads `surface_observations`, so a
self-consistent report whose surfaces are absent, or which records a failed finalization, would
satisfy it. The normal path is protected upstream — `measure_three_surfaces.py` refuses a non-final
final capture and raises on settle timeout, and the external measurement requires all three surfaces
— but that is a property of the producer, not of the gate. This gap predates this decision and is
unchanged by it; it is recorded here because the tolerance now rests on that precondition and the
precondition deserves to be stated honestly rather than assumed.

Admission and recording judge the **same recomputed macro**, and records are emitted only for an
observation that validated. Reported and recomputed macros are required to agree only to 1e-12, so
reading the reported value could have named a different number than the one admitted, or stayed
silent about an admission; and classifying distance alone would have attached "admitted" records to
runs the gate rejected. Both are regression-tested.

## Consequences

Preadmission can now reach G7 on a run whose only deviations are ruled exceptions, which is what the
mandate always intended. The three macros above are admitted; anything worse than 5 % still rejects,
in both directions, for all eight macros.

`test_quality_numeric_failures_are_reported_without_weakening_bounds` previously perturbed each macro
by ±0.01 **absolute**. That is 6–10 % for the error rates but ~1 % for the accuracies, whose bounds
sit near 1.0, so three of its eight perturbations now fall inside the admitted band. It was rewritten
to perturb **relatively**, which restores its intent — every macro moved decisively past the
tolerance — and made the asymmetry it had been hiding explicit. Companion tests assert the admitted
case (a self-consistent report offset 1 % from every bound passes G4 and produces eight named
exception records), that **each bound rejects on its own** when moved past the band while the other
seven stay clean, and that an admission is recorded from the recomputed macro even when the reported
one sits exactly on the bound. These exercise `evaluate_external_report`; they do not exercise
`run_acceptance` or a persisted `verdict.json`, so the recording guarantee is proven at the
evaluator, not at the file.

The risk this accepts is drift: a candidate may now be admitted while three macros sit just outside
their bounds, and successive candidates could each sit just inside the band. The mitigation is that
every admitted exception is recorded in the verdict, so drift is visible in the record rather than
inferred. If the bounds themselves should move, that is a separate decision about
`QUALITY_BOUNDS`, made deliberately — not something this tolerance should be widened to absorb.

## Amendment 2026-09-23 — D46: window completeness counts terminal coverage
User ruling D46 = O1 (round 6). The structural completeness condition stays **122 planned full 10-second windows** for the frozen six-case,
two-pass corpus (planned from accepted samples on the production 10 s / 10 s geometry). A planned window is complete when rolling decoded it
**or** the applied terminal pass covers it: exactly one terminal text revision with status `final`, the `post_stop_final` snapshot finalization
status `final`, and a revision sample range containing the whole window. Any planned window covered by neither fails the predicate. Reason:
commit `3f8e592b` (WP35, 2026-09-18) intentionally stops rolling at Stop when the terminal pass will supersede it, so the last window of some
cases is decoded only by the terminal pass (host H1 2026-09-23: 116 rolling of 122 planned, per layer). The public event stream ends at the
terminal revision, so `terminal_finalization_completed` is not required. Quality bounds and the 5 % exception band are unchanged.
