# Overload qualification duration — 2026-09-12

The fixed 30-second overload requirement was a stale probe assumption, not a
product requirement. Round 12's `e03d6a310f86c3db0292ae3de0e784270e01f288`
ran 120.5 seconds per session: both layers finalized all eight sessions and
retained refusal → peer progress → retry of the same frame. The evaluator still
rejected both at `requested != 30`.

**This is the only evaluator expectation changed in this qualification effort.**
The user explicitly authorized this correction after accepting Round 12.
QUALITY_BOUNDS, the identity policy, runtime behavior, and all other overload
assertions remain unchanged. The existing three quality exceptions remain
exceptions; no quality bound is relaxed in code.

## Derivation and invariant

The structural question is whether the submitted workload can exceed the lane
buffer while allowing drain/retry progress. The necessary quantities are the
installed descriptor's `bounds.max_retained_samples`, its `frame_samples`, and
the fixed 16,000-sample/second live contract. Audio duration alone cannot answer
that question without the buffer and frame geometry.

The existing producer budgets one frame-rounded lane buffer, another buffer of
drain/retry headroom, then one whole frame beyond that:

```
capacity_frames = ceil(max_retained_samples / frame_samples)
minimum_frames = 2 * capacity_frames + 1
minimum_seconds = minimum_frames * frame_samples / 16000
requested_duration_seconds >= minimum_seconds
```

For the measured descriptor: 960,000 retained samples, 8,000-sample frames:
`(2 * 120 + 1) * 8000 / 16000 = 120.5 seconds`.
Thirty seconds cannot even fill the 60-second buffer. A doubled buffer requires
240.5 seconds; the evaluator must not merely replace one literal with another.

`overload_minimum_frames` now owns the existing calculation for both producer
and evaluator. The producer retains descriptor-derived capacity and frame size
in `backpressure_workload`; the evaluator derives the minimum from that record.
The producer's workload is unchanged. Requested duration may exceed the minimum;
accepted/accounted samples must still match the actual requested duration.

The retry margin is a bounded workload budget, not a guarantee that any scheduler
will refuse. Actual campaign-bound refusal, peer progress, same-frame retry,
fairness, complete wrong-owner probes, and sample accounting remain mandatory.
No new host run or provider request was used to justify this change.

## Falsifier and validation

The old evaluator accepted the 30-second fixture and rejected 120.5 seconds.
Regression tests reproduced that behavior before the fix. The corrected tests
reject 30, 60 and 120 seconds for the measured buffer; accept 120.5 and 121;
and require 240.5 seconds for a doubled buffer. Accepting a shorter workload or
ignoring a changed descriptor would falsify the correction.

Run:

```sh
python -m pytest tests/phase2/test_wave1_qualification.py \
  tests/phase2/test_acceptance_overload_window.py -q
```

The existing real `LiveV2Session` test exercises the 60-second lane boundary,
observes an actual capacity refusal, drains on peer progress, and retries the
identical frame. The evaluator regressions use complete eight-session evidence,
including accounting, lifecycle fairness and foreign-owner probes. All 180 tests
in the two affected modules pass, including independent rejection when any of
the three backpressure witnesses is false.

## Separate finding — terminal enforcement

Inspection also found that `_validate_overload` currently accepts an otherwise
valid fixture with `terminal_failures=1`. Its explicit terminal-failure check is
absent (the capacity validator has one). That gap is reported separately and left unchanged. This duration-only change does not
claim to add terminal enforcement or certify a new candidate. Round 12's zero
terminal failures and all-eight finalization were independently observed.
