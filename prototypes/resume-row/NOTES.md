# F3r retained File resume row

**Verdict: UNMEASURED.** The existing F3/F3s rows do not restart a server during
a multi-window File transcription. This harness is ready for one real-decoder run
only after pane 3.3's F1 fix is merged and the product is re-frozen.

## Structural contract

- **Question:** after a crash with a committed File prefix, does restart reserve
  that exact Meeting, accept its checkpoint, decode only the suffix, publish the
  same transcript as an uninterrupted run, and reclaim the owner directory?
- **Minimum primitives:** one frozen SHA; one 360-second, three-window File; a
  one-window committed prefix; SIGKILL; one persistent state root; an owned
  counted proxy; and direct transcript equality in memory.
- **Invariants:** `n=3`, `k=1`; reference `3`, pre-crash `1`, post-restart `2`;
  six real decoder requests total, no provider, peak at most two. Missing evidence
  or upstream failure is `INCOMPLETE`.
- **Unknown:** the real result until F1 is fixed, re-frozen, leased, and executed.
- **Falsifier:** readiness waits on validation; reservation is absent; validation
  refuses; post-restart count differs from two; transcript differs; or retained
  owner survives completion.
- **Tool decision:** the production stack and bundle proxy test product custody and
  request custody. The stub dry run tests only harness SIGKILL/restart mechanics.

## Commands

Plan only, zero calls:

```sh
python prototypes/resume-row/run.py --plan-only \
  --frozen-sha "$FROZEN_SHA" --out /tmp/f3r-plan.json
```

The checklist contains the gated real command and required receipts.

## Arithmetic correction

The brief's `2n-k` total omits the `k` requests required to create the crash
checkpoint. The real row is `n + k + (n-k) = 2n = 6`. This is below the cap of
12. Reporting five would undercount one actual decoder request.
