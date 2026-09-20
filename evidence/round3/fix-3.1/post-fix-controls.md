# FIX-3.1 post-fix controls

Same three controls as `pre-fix-controls.md` on the working fix.

Verdict: PASS, `3 passed, 1 warning in 2.79s`, exit 0.

- Headed reader output expands to interval-bound source words.
- Scheduler exposes first dispatch, cumulative wait/service, and terminal contention per owner.
- Operator status carries the read-only stage summary after a background dispatch.
