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
