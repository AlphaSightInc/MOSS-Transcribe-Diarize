# WP52b verdict

Gate: existing round-2 prototype `SUPPORTED`; no new prototype permitted.

Structural question: can retained server-local clocks distinguish per-window
vLLM scheduling from a wrong whole-batch lease without changing arbitration?

Minimum primitives: content-free owner kind/key, monotonically increasing owner
window index, and accepted/wait-start/start/end monotonic timestamps. Removing
any stage loses the requested acceptance, queue, or service projection.

Invariants: two-call/one-background capacity, Live priority, per-window vLLM
composition, cancellation behavior, and retained cancelled-owner history do not
change. HF MG3 INCOMPLETE.

Assumptions/unknowns: clocks are comparable only within this server process.
No cross-host subtraction and no cross-backend fairness claim is made.

Falsifier: a deliberately scheduler-above-window-loop composition is not
classified as a whole-batch hold, or ordinary per-window composition prevents
File from appearing between terminal windows.

Tool decision: scheduler-unit controls exercise the production gate and an
evidence-only projector derives File acceptance-to-first-dispatch, per-window
wait/service, and overlap of terminal wait with another terminal's service.

Verdict: SUPPORTED. Baseline violating control failed at `a7a738cf` because the
clock seam was absent. Patched healthy and violating controls pass. The new
round-2 finding is named: approximately **25 seconds terminal-vs-terminal
wait**, within own-decode sums 19.9-26.6 seconds and Stop-to-final 45.0-62.5
seconds. This branch instruments that number; it does not claim a new live
measurement.
