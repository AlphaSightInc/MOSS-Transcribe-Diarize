# Data durability, backup and code rollback

WP31 measured the integrated build at `ea89af0c` against 13 private copies of real
stores: 47 saved meetings, including pre-lane and per-lane documents. All 47 opened,
rendered, renamed and preserved their transcripts/audio; all 235 exports passed the
independent oracle. All 13 stores accepted a new real-decoder Live meeting without
losing old meetings. These are local upgrade observations, not deployment acceptance.
Evidence and exact commands: `prototypes/data-durability/NOTES.md` and
`evidence/mvpfix/wp31/`.

## Store compatibility

Browser-workspace stores use SQLite `user_version=2`. Lane attribution is optional
within transcript JSON; old mono documents remain mono and gain no invented lane.
Versions 1, 3 and 999 and a corrupted header were refused before serving; original
bytes remained unchanged. Refusal is not migration: preserve the incompatible store
and select a compatible release. Do not reset its version or create an empty file
at its path to bypass refusal.

A saved meeting owns transcript rows and separately referenced audio files. A database
backup alone is not a complete meeting backup. Account credentials, speaker labels,
voiceprints and summaries also live in the database. Keep these private.

## Backup and restore

Use a **stopped web process** for an ordinary filesystem backup. Idle in the browser
is insufficient: outstanding work and SQLite's write-ahead log (WAL) can still change.

1. Finish intended captures and wait for their saved terminal state. Stop only the MOSS
   web process that owns this state; wait for its exit. Leave the decoder service alone.
2. Copy the SQLite database, any remaining `-wal`/`-shm` sidecars, and the complete
   configured meeting-audio root into one new backup directory. Preserve relative
   audio paths. Retain the candidate identity and configured root locations with it.
3. Restore into a **fresh** state directory while its web process is stopped. Point the
   candidate's `--database` and `--meeting-audio-root` at those restored paths. Do not
   overwrite a newer user store to perform a drill.
4. Start the same or a compatible candidate. Check history count, representative
   transcripts/exports, and every referenced audio file. Keep the pre-restore state
   until that comparison succeeds.

WP31's stopped copies matched database bytes, table rows and every audio file in
13/13 stores. A live database-only copy lost the one acknowledged transcript in its
control: SQLite had committed it to WAL, not yet to the database file. SQLite's
online backup API retained it, but that API does not snapshot the external audio root.

**Copying SQLite files and audio while capture is active is an unqualified hot copy,
not a complete-backup guarantee.** One WP31 copy made during real ingress was valid
and recovered as interrupted. A concurrent audio append, publication or cleanup can
cross the copy boundary. Use the stopped-process procedure above for an ordinary
restorable backup; no new hot-backup coordinator was implemented.

## Interrupted capture and cold start

A restarted process does not resume an old capture. Startup recovery marks the saved
meeting `interrupted`, retains committed transcript rows and converts recoverable
mixed PCM into a partial MP3. The browser must Reset and explicitly start a new capture.
A frame acknowledgement is not proof that every buffered lane frame has already
become a durable transcript word. WP31 compares committed transcript segments and
recoverable audio, not untranscribed frame durability.

A new-state-path startup with installed model assets is a local process cold start.
It does not measure OS reboot, cold filesystem/model caches or shared-host service
autostart. Missing/invalid manifests and missing model assets must refuse startup
through the existing provider preflight; no readiness threshold is relaxed.

## Rollback contract: base 37979e53

On the same copied per-lane store, integrated → base → integrated preserved all table
rows. Base opened all 8 meetings and preserved words, labels and timing. It displayed
no lane badges and omitted lane fields from all 8 JSON exports (32/40 full-oracle
exports passed). Returning to integrated restored all lanes and 40/40 exports.

Therefore **base is a storage-compatible, reduced-capability reader, not a lane-faithful
rollback**. Do not present its exports as retaining lane attribution. This drill did
not qualify base writes to existing per-lane meetings or its recording behavior.
Keep the newer store intact; restoring a pre-upgrade backup would discard later user
work and is a separate data-loss decision. `CutoverRun.restore()` remains an
interrupted-cutover recovery mechanism, not a post-release data rollback command.
