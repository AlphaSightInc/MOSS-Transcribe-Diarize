# I3/I4 verification result

**PASS.** Executed every command in `VERIFY.md` from the owned clone on
`round4/impl-i3i4`. External decoder/provider/network/tunnel calls: `0/0/0/0`.

## Results

1. **Checkout/import/scope/secrets — PASS.** Import resolved inside this clone.
   Secret grep was empty. Frozen-product diff is limited to the six owned files in
   `phase2.py`, `phase2_file.py`, `tools/qualify/{decoder,test_bundle}.py`, and
   `prototypes/feature-rows/{run.py,NOTES.md}`.
2. **Forbidden seams — PASS.** AST source equality against `2fa9dfda` proved
   `_assert_no_active_meetings`, `accept`, `accept_url`, `_retain_new_directory`,
   both existing reclaim methods, and `_checkpoint_is_valid` byte-identical.
3. **Strict/focused controls — PASS: 50/50.** The two P3 controls first failed
   `2/2` on the frozen implementation. Only their strict-xfail markers were
   removed; both now pass. Retained lifecycle and summary accounting controls pass.
4. **Readiness/exclusion — PASS.** Every matrix point returned the exact reserved
   set before injected validation entered. Measurements:

   | Owners | Validation | Readiness | Per owner |
   |---:|---:|---:|---:|
   | 1 | 3 ms | 0.115917 ms | 0.115917 ms |
   | 10 | 3 ms | 0.755334 ms | 0.075533 ms |
   | 120 | 3 ms | 9.745708 ms | 0.081214 ms |
   | 1 | 300 ms | 0.102375 ms | 0.102375 ms |
   | 10 | 300 ms | 0.830625 ms | 0.083062 ms |
   | 120 | 300 ms | 12.408542 ms | 0.103405 ms |

   Both 120-owner values are below the required `0.2 ms/owner`. Controls also
   prove invalid reserved work becomes durable `interrupted` then reclaimed,
   Live work is untouched by reservation, duplicate ownership is refused, the
   descriptor remains serviceable during held resumed work, and background
   failures become durable/operator-visible.
5. **Summary row — PASS (plan only).** Production geometry gives 50 s = 1 window,
   180 s = 2 windows: planned decoder `3`; planned provider `6`; cumulative cap
   `8/10`; actual calls `0/0`. Execution owns numeric proxy deltas and requires
   `3/3/0`, peak `<=2`; mismatch becomes `INCOMPLETE`. Main-bundle
   `capacity_2x1800` remains `REQUIRED-NOT-RUN`.
6. **Backend — PASS:** `2176 passed, 5 skipped, 2 xfailed, 0 failed`, plus
   `37 subtests`, in `196.11 s`. The two xfails are only the retained parametrized
   Jamie exclusion in `tests/test_round4_jamie_violating_controls.py`.
7. **Frontend — PASS:** `28/28` files, `312/312` tests. Typecheck and build exit
   `0`; generated asset diff is empty.

## Honest boundary

Pane 3.2 has not yet supplied `WindowedRunner.validate_resume`; I3 therefore calls
the existing byte-identical `_checkpoint_is_valid` behind the background boundary,
as the brief requires. Swap to the runner-owned method when pane 3.2 lands.

One loaded full-suite attempt produced a `0.613 ms/owner` wall-clock outlier in the
embedded timing assertion while all semantics passed. The absolute timing gate now
runs only in the isolated readiness probe above; the full-suite control proves that
startup returns while 300 ms validation is still running. The final full suite is
green.
