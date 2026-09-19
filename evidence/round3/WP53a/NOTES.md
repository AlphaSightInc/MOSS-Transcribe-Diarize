# WP53a evidence

Gate: `DONE` from round-2 `runner_storage/NOTES.md` F6/D6.

## Verdict

BLOCKED by the brief's file-ownership boundary; no production or test change made.

The required explicit path is:

`phase2_web_cli.py:file_work_root` → `live_provider_bundle.build_live_runtime_factory` → `LiveServiceRuntime` → `LiveCoordinator(tape_storage_root=...)` → mixed and lane `CompleteMixedTape(storage_root=...)` → `TemporaryFile(dir=...)`.

`live_service_runtime.py` is explicitly listed as another pane's file and must not be touched. `live_provider_bundle.py` is not in this pane's owned-file list. Neither current interface carries an operator-selected transient root. `LiveCoordinator` receives only session/decoder/policy/identity/arbiter objects and tape capacity; deriving a path from any of them would couple unrelated primitives. `tempfile.gettempdir()`, an environment variable, or a mutable process global would recreate the forbidden ambient placement and would make multi-app/runtime isolation false.

Exact minimal unblock:

1. Lead/owner adds a `tape_storage_root: Path` parameter through `build_live_runtime_factory` and `LiveServiceRuntime` to `LiveCoordinator.create`.
2. This pane can then require `storage_root` for every capacity-enabled coordinator/tape, create one narrow owned scratch directory, pass it to all mixed/lane `TemporaryFile(dir=...)` calls, and add the named placement/failure/release tests.

No workaround was implemented. Existing typed `tape_storage_failed` and idempotent release behavior remain unchanged and covered by baseline tests, but configured-filesystem placement remains unresolved.

Exact raw PCM16 owners at 16 kHz for 200 represented minutes:

- zero lanes: mixed tape 384,000,000 + durable mixed stage 384,000,000 = **768,000,000 bytes**;
- one lane: mixed + lane + durable mixed = **1,152,000,000 bytes**;
- two lanes: mixed + two lanes + durable mixed = **1,536,000,000 bytes**.

These are exact owner arithmetic, not a measured peak and not an admission policy.
