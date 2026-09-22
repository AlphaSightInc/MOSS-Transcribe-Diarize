# D34 row-10 best-effort harness

## Structural question

Can the existing row-10 browser harness represent up to five isolated measurements
without turning five recognition misses into a product or bundle failure?

## Minimum primitives

- An attempt is one fresh browser context and one `bank()` capture; reusing it can
  retain stopped capture state.
- A durable prior meeting is required before a later attempt because the product
  permits only two active live meetings.
- A retained attempt record needs the recognition number, timing projection, and
  meeting id; without all three a miss cannot be attributed or audited.
- `BEST_EFFORT_FAIL` means all five valid recognition attempts missed the 4.5 s
  empirical regression budget. It is not a harness exception or missing-bank-name
  failure, and so it is non-required only at the bundle row-10 gate.

## Invariants

No product code, endpoint geometry, frame protocol, identity constants, or decoder
requests change. Every attempt remains a real Chromium/browser HTTP capture and
real Stop path, with content-free retained evidence only.

## Assumptions and unknowns

The loopback stub cannot make the enrolled name appear, so it is expected to
exercise five recognition misses rather than a passing timing attempt. Real decoder
latency remains unmeasured here (budget 0).

## Falsifier

The design is falsified if a first passing attempt does not stop subsequent
attempts, five valid misses become `FAIL`/throw, a missing bank name is relabelled
as `BEST_EFFORT_FAIL`, or the bundle treats `BEST_EFFORT_FAIL` as required.

## Tool decision and one-command prototype

`run.py` uses the existing production-composed local stack, Chromium harness,
loopback vLLM-shape stub, and real Stop path. It changes the decision by proving
the new status and all-attempt receipt retention without a real decoder request:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python prototypes/round5-i4/run.py --loopback
```

## Verdict

`PARKED_CRITICAL` for loopback end-to-end. The focused controls support D34's
harness semantics, but the current `fd825ee7` stack cannot seed the existing
row-5 enrollment from the content-free stub, so row 10 cannot be reached under
this zero-decoder control.

Substantive attempts (all with real decoder/provider/GPU requests = 0):

1. `evidence/round5/i4/loopback-retry-2/result.json`: normal rows 4/10;
   row 4's internal enrollment timed out, 113 stub requests, no row-10 receipt.
2. `evidence/round5/i4/loopback-retry-3/result.json`: prior proven row-5 seed
   recipe against this clone; row 5 timed out, 75 stub requests, no row-10 receipt.
3. `evidence/round5/i4/loopback-retry-4/result.json`: same seed recipe through
   the local proxy shape; row 5 timed out, 76 accepted/completed stub requests,
   no row-10 receipt; stack, proxy, and stub listeners were all closed.

The exact missing evidence is a zero-real-request loopback fixture that passes
the existing row-5 enrollment on this checkout, then reaches row 10's five
current-harness attempts. Do not relabel the seed timeout or missing bank name
as `BEST_EFFORT_FAIL`.
