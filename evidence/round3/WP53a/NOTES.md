# WP53a evidence

Gate: `DONE` from round-2 `runner_storage/NOTES.md` F6/D6.

## Verdict

SUPPORTED after the lead authorized the minimum mechanical root pass-through.

The implemented path is:

`phase2_web_cli.py:file_work_root/live-tapes` →
`live_provider_bundle.build_live_runtime_factory(tape_storage_root)` →
`LiveServiceRuntime(tape_storage_root)` →
`LiveCoordinator(tape_storage_root)` → mixed and lane
`CompleteMixedTape(storage_root)` → `TemporaryFile(dir=storage_root)`.

No admission, scheduling, pump, abort, manifest, or SQLite behavior changed.

## Falsifiers and results

- Unpatched `a7a738cf`: 3/3 violating placement controls failed as required
  (`unpatched-violating-controls.xml`). A missing root was accepted; the tape fd and
  coordinator tapes did not prove operator-selected placement.
- Patched targeted controls: 34 passed (`postpatch-targeted.xml`).
- Related integration controls: 245 passed plus 19 subtests.
- A capacity-enabled tape without a configured root is rejected.
- Mixed and 0/1/2 lane tapes resolve under one configured root; release removes all scratch.
- Deferred flush failure writes no samples, names all 12 refused samples, refuses reads,
  and refuses later appends.
- Double release closes once, retains accounting, and refuses later reads/appends.

## Exact ownership arithmetic

At PCM16 mono 16 kHz for 200 represented minutes:

- zero lanes: mixed tape 384,000,000 + durable mixed stage 384,000,000 =
  **768,000,000 bytes**;
- one lane: mixed + lane + durable mixed = **1,152,000,000 bytes**;
- two lanes: mixed + two lanes + durable mixed = **1,536,000,000 bytes**.

These are exact raw owners, not measured resident peaks and not admission policy.

## Prerequisites retained, not changed

- MG5: deployment SQLite runtime 3.50.4 versus required 3.53.4.
- MG10: shared-host five-minute tape manifest 9,600,000 bytes versus 384,000,000
  bytes for 200 minutes.
