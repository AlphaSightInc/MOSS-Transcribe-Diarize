# Bank revision and publication verdict — 2026-09-10

Question: can rename/delete fence stale recognition and update active labels without
changing stopped text or choosing another profile with the same name? Primitives are
the existing opaque profile ID, independent display label, owner-bound meeting handle,
and a process-local revision for process-local prepared work. Startup interrupts old
Live meetings, so a second persistent revision schema adds no protection here.

The throwaway Node-free Python state probe printed rename revision 1 and delete
revision 2. It measured all three falsifiers false: stale result rejected, same-name
neighbor survives, stopped label unchanged. Absorbed into production bank operations
and their HTTP/runtime tests; simulator removed.

Production implementation: identity -> sorted binding locks -> SQLite. Service-owned
mutation tasks survive client cancellation and shutdown joins them. Rename commits
exact linked active documents before publishing label revisions. Delete removes exact
samples/links and pending enrollment, preserves recorded names, advances revision;
old prepared results cannot reintroduce the deleted ID. Automatic matches never enroll.
Manual names remain authoritative; manually naming a recognized speaker updates only
that linked profile and propagates to other active meetings. Stopped labels stay frozen.

Evidence boundary: causal observations copy original per-span vectors under the runtime
publication lock, before another span can replace/consume them. This does not reconcile
or re-embed. The one-second recognition floor is separate from the two-second enrollment
album. Terminal matching uses the captured album. Configured encoder ID/dimension marks
only incompatible entries for re-enrollment.

Adversarial review reproduced a worker-death failure when bank reads/link commits raised
outside the publisher's persistence handler. The regression initially timed out waiting
for a failure status. Fixed: unwind identity locks, fence and settle the meeting, notify
terminal waiters; subsequent frames refuse and Stop returns. Lock-order and stopped-history
review found no other must-fix. Tests also inject a held real COMMIT plus cancelled client
and execute 32 concurrent renames; durable labels, active labels and one-sample bank converge.

Commands:

```sh
.venv/bin/python -m pytest -q tests/phase2/test_voiceprint_bank_operations.py tests/phase2/test_voiceprint_matching.py tests/test_live_provider_bundle.py --tb=short
npm --prefix frontend test
```

Real encoder quality is a separate standing-bench measurement, not supplied by these
synthetic state/HTTP fixtures. Integrated deployed G8 and load evidence remain required.
