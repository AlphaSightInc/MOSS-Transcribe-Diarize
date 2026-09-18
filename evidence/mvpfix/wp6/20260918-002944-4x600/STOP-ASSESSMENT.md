# F3 — two interrupted sessions after simultaneous Stop

**Confirmed:** all four sessions acknowledged 2,400 lane frames (600 seconds);
sessions 1/2 reached final, sessions 3/4 persisted as interrupted. The retained
`terminal-log.txt` explicitly records `helper_lease_expired` for 3/4. Each of their
partial-status MP3s still contains exactly 600 seconds. This is no longer the
300-second tape-exhaustion outcome.

**Evidence limit:** the original HTTP exception collector kept only `HTTPError`,
not status/body or request stage. It saved final snapshots only for 1/2. Therefore
the precise HTTP refusal, terminal-refinement status and birth counters for 3/4
are not recorded. No inference RTF is recoverable from the incomplete rolling
event collection; the reducer correctly refuses admitted/completed mismatch.

H1 (Stop/drain wait outlasts helper lease) is supported by the observed lease
expiry and source ordering, but the initiating sequence is not established.
`run.py` ends heartbeat calls after the last frame and awaits Stop with deadline30.
`live_transport.py:190-268` releases helper state after v2/raw drain; a refused
unconsumed-frame Stop can leave capture state armed. The helper's expiry path is
`live_helper_failure.py:273-289`. Both a long drain and an earlier refused Stop
are plausible from the retained evidence; neither is selected as proven cause.
H2 (decoder terminal failure) has no retained failure record; not established.
H3 (same 300-second retention exhaustion) is falsified by all four 600-second MP3s
and two full final outcomes. Exact failed-session in-memory tape state is unmeasured.

The two-request measurement limiter includes terminal decode; remote service-wide
load contaminated 12/32 samples and ingress paused three times. This campaign
does not isolate a production defect. No production repair or policy change follows.
The read-only saved-state reduction is repeatable with `recover_run.py`; a new
live reproduction was not authorized beyond the single rerun and was not made.

For future runs only, the collector now retains last-observed identity/sample
counters plus HTTP status/code even on error, and excludes unassigned speech from
speaker counts. `runner-used.py` preserves exactly what ran here. These reporting
repairs cannot retroactively fill the missing fields and were not live-retried.
