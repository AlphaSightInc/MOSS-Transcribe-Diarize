# Issue #20 measured verdict

## Pre-production policy measurement — PASS (2026-08-28)

The one-command interleaving measured the smallest sufficient composition before production
edits:

- two concurrent commands joined one service-owned target settlement and returned the same
  content-free result;
- the synchronous per-Meeting claim removed queued target results before any await; released
  late Live and File results committed zero text, while both unrelated peer Meetings continued;
- complete audio changed only `available -> partial`, preserving the fixed path, 48,000 bytes,
  and 8,000 ms duration; a target with no artifact became `unavailable`;
- command completion observed `interrupted`, source absence, and zero owned interrupt tasks;
- cancelling the transport caller did not cancel accepted settlement; service shutdown joined it;
- a repeated terminal ID and an unknown opaque ID returned the same no-change shape and no
  Account/content fields.

Both independent negative controls were effective: `--suppress fence` and `--suppress cleanup`
each printed `FAIL` and exited `1`.

**Decision:** deepen existing Live/File owners with one synchronous opaque-ID claim, and let one
service-owned interrupt task compose their existing settlement. Do not add a second socket,
scheduler, Account workspace, artifact reader, or global cancellation path. Production absorption
must replace the prototype-local reducer and retain the same self-gating output.

## Production absorption — PASS

The probe now imports and runs production `AccountLifecycle.interrupt_meeting`; only thin
deterministic Live/File adapters hold the result boundary. The same full state passed, and both
negative controls still exited `1`. Focused production tests additionally held a real Live decode,
an admitted SQLite transcript commit, a synchronous File runner, and a real FFmpeg MP3 artifact:
the target alone became interrupted, delayed results committed nothing, File input cleanup preceded
return, complete MP3 bytes/metadata stayed identical while state became partial, and a cancelled
Unix handler remained joined by product shutdown.

## Runtime queue correction — RED before production (2026-08-28)

The extended probe held one real `LiveServiceRuntime` target decode, then placed exactly one
canonical, one refinement, and one provisional item in that target's per-session arbiter while a
peer canonical item waited. Production `abort` left target depth `3 -> 3`; the operator aggregate
stayed `4 -> 4`. After releasing the held provider, its answer committed zero and the peer reached
1,000 accounted samples, but the terminal target still owned all three queued items. This falsified
the claim that the Phase-2 publication fence alone drained accepted lower-runtime work.

**Required correction:** the runtime that owns the per-session arbiter must discard all queued Live
kinds and reconcile their timing/readiness counters under its existing lock before `abort` first
awaits. The already-running provider remains non-cancellable and is rejected by terminal authority;
peer state is outside the target arbiter and must remain untouched.

## Runtime queue correction — PASS

The absorbed probe repeated the same held production runtime interleaving. Target canonical,
refinement, and provisional depth changed exactly `3 -> 0` inside `abort` before its first await;
operator aggregate depth changed `4 -> 1`, retaining only the peer canonical item. Releasing the
held target provider committed zero target samples, the peer reached 1,000 accounted samples, all
queued timing/readiness entries were reconciled, and repeat abort changed no counter. The existing
`--suppress fence` and `--suppress cleanup` controls remain independent falsifiers for the higher
owner composition.
