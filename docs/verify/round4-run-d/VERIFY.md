# Round 4 run D — offline verification

**IN PROGRESS.** This verifier records completed run-D controls while the
remaining journal correction and final required gates are pending.

## D4 — ordinary task failures re-signal after durable truth

A File Meeting has two separate facts: its durable operator-visible outcome and
its background task result. A resumed task must return after recording failure
because it runs behind startup. An ordinary upload is not a startup dependency,
so it keeps the prior task failure signal after the same durable outcome and
owner-local cleanup.

Run D chose **restore**, not merely disclose. In
`FileMeetingTasks._complete`, commit and audio-publication exceptions now
re-raise only when `resumed` is false. Both branches first write `failed` and
remove only that Meeting's retained owner directory. The resumed controls still
return after durable `resume_failed`, preserving non-blocking startup.

`test_unresumed_failure_is_durable_and_resignals_task` was RED before the
restoration: the Meeting was `storage_failed` but its task had no exception.
It covers both ordinary failure arms. Together with the retained commit and
publication controls, the focused result is **4 passed**. No decoder, network,
GPU, tunnel, proxy, or provider request was made.

The directly affected ordinary-File and retained-resume modules are also
**39 passed**; `py_compile` and `git diff --check` are clean.

Falsifier: a normal commit/publication failure either lacks its durable failed
Meeting outcome or ends its task successfully; a resumed failure aborts
lifespan.
