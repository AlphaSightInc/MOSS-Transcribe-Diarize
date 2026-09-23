# D46 coverage prototype (throwaway)

Structural question: Can each full 10 s corpus window be proved decoded by rolling, or covered by the applied terminal revision, using the production event trace?

Minimum primitives: accepted sample count (defines the full-window plan); rolling completion intervals (decoded windows); applied terminal revision interval plus finalization completion (terminal coverage). Each is needed to distinguish a decoded window from an inferred one.

Invariants: production 10 s / 10 s geometry and 16 kHz rate; each planned full window has one coverage classification; partial tails are outside the 122-window corpus invariant; missing/failed terminal proof never fills a gap. Quality bounds and the frozen corpus total remain unchanged.

Assumptions/unknowns: the H1 retained diagnostics may omit terminal revision events even when finalization succeeded. A final surface alone does not prove the sample range of the terminal pass. The next host run must retain the applied terminal revision's start/end samples and terminal completion in a content-free artifact.

Falsifier: any planned full window absent from rolling and outside the applied terminal range; a terminal event without applied completion; a duplicate/malformed rolling interval. All must fail completeness.

Tool decision: one local script reads H1's content-free raw observations/diagnostics and prints every case's coverage state; this shows whether retained evidence suffices before production code. Focused RED/GREEN tests then exercise the producer and validator. Full backend and bundle check integration. No decoder or host access changes this decision.

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python prototypes/round6-d46-coverage/run.py`

Verdict: both H1 layers show 122 planned / 116 rolling, but 0/12 case-pass diagnostics per layer retain an applied terminal range or terminal completion event. The six missing rolling windows therefore cannot be credited from H1. The validated design counts only windows contained in an applied terminal revision's trace interval; a missing proof leaves an uncovered count and fails the gate. H1 counts are retained in `evidence/d46-prep/h1-window-replay.jsonl` outside the clone.
