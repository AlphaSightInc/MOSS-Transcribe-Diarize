# Fix runner evidence

## Structural contract

- Question: can the production scheduler prove bounded, attributed, window-level S7/S8
  ordering while two Live sessions, File, URL, and terminal work contend?
- Minimum primitives: owner kind/key/window; accepted/wait/start/end server clocks;
  Stop and File-submission client clocks; scheduler limits.
- Invariants: at most two total and one background dispatch; complete denominator;
  Live priority at observed opportunities; File/URL yield between windows.
- Unknown before measurement: real-service dispatch times and whether a qualifying
  Live-preemption opportunity occurs.
- Falsifier: missing attribution, incomplete timings, >2 total, >1 background, File
  first dispatch >12 seconds, whole-batch hold, or observed Live priority inversion.

## Prototype controls

Unpatched `738cdfdd`:

```text
pytest -q tests/test_capacity_campaign_fix.py --junitxml=evidence/round3/fix-runner/unpatched-controls.xml
3 failed
```

Patched prototype:

```text
pytest -q tests/test_capacity_campaign_fix.py --junitxml=evidence/round3/fix-runner/patched-controls.xml
3 passed
```

The first patched attempt was 2 passed / 1 failed because the healthy fixture created
two valid preemption opportunities while its assertion expected exactly one. The
production predicate already required all observed opportunities to pass; the test was
corrected to assert a non-zero, complete denominator. No product behavior changed.

## Isolated manifest

`copy_manifest.py --minutes 240` admitted `460,800,000` tape bytes (14,400 seconds).
The host manifest stayed byte-identical. MG5 SQLite and MG10 host-manifest prerequisites
remain unchanged.

## Live verdict

The literal combined S7/S8 run passed cleanly. See `campaign-summary.md` for the
denominator tables and `s7-s8-2x300/result.json` for all 342 attributed window rows.
The runner used 342/400 decoder requests. No product defect was found.

## Full-suite gate

Frontend passed 310/310 plus typecheck and build. Backend attempt 1 was 2,102 passed,
1 failed, 5 skipped, 37 subtests: the 151-second multistream test missed its fixed
5-second poll deadline. It passed alone 1/1 in 5.00 seconds without a change; the full
rerun passed 2,103 with 5 skipped and 37 subtests in 184.40 seconds. Both attempts are
retained in `suite-summary.txt`; the transient failure is not hidden or waived.
