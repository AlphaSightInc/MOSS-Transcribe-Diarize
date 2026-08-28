# ADR-0012: Phase 2 replaces Phase 1 atomically and ships in three waves

- **Status:** Accepted
- **Date:** 2026-08-27
- **Scope:** Phase-2 release boundary

## Context

Keeping legacy tokens or unauthenticated routes beside Account ownership would preserve two trust
models and make isolation unverifiable. Shipping Voiceprints and summaries in the first cut would
delay the independently useful Account product.

## Decision

Wave 1 atomically replaces Phase 1 with Google Sign-in, Account workspaces, durable Live/File
Meetings, history, and owner-private MP3. `/` is the only product UI; `/studio`, `/live`, external
plaintext `:7860`, shared-token, pairing/device, view-token, and legacy job paths are removed.
Phase 2 starts with empty schema-v1 Account histories and Voiceprint banks; one complete pre-upgrade
snapshot remains quarantined outside MOSS.

Cutover blocks new work, drains active and queued work to zero, snapshots Phase 1, installs the
authenticated candidate, and runs the production-origin canary before admission. Pre-admission
failure restores the whole old snapshot and services; there is no dual-auth fallback or partial
merge. After Wave 1, the private Voiceprint bank ships independently as Wave 2; browser-owned Final
summaries ship independently as Wave 3.

The last Phase-1 deployment therefore carries one deliberately temporary prerequisite before its
product surface is deleted: a private, reboot-durable host marker shared by the batch and Live
processes, composed with one process-local counted admission scope. The scope starts before a
creation request can wait for its body and ends only after work is registered or its staging is
cleaned, including coroutine cancellation. Marker existence rejects only new Live create and job
create/rerun/resume/render; marker access uncertainty fails closed. Existing frame, heartbeat,
read, download, Stop, abort, accepted
jobs, and startup recovery remain outside the gate and drain normally. `/api/runtime` reports only
the marker state, entrants, active/queued job counts, and active Live count; a closed Live session
remains active drain work while its real terminal finalizer is running. The marker is not an
authority, database fact, proxy, or second service, and the Phase-2 replacement removes this
legacy seam after old-deployment quiescence is proven.

The cooperating host controls that fact with `mtd-phase1-quiesce enable`, verifies both process
views through `/api/runtime`, and uses `mtd-phase1-quiesce disable` only when abandoning cutover and
reopening the old deployment. All three commands use the same Linux-home marker by default.

## Measured prerequisite verdict

`prototypes/phase1-creation-quiesce/` derived `PASS` from 47/47 predicates on Python 3.10.19 and
3.12.12. It spawned two distinct operating-system processes with production `create_app` runtime
views over the same marker, plus isolated production registration, upload-cancellation, and
terminal-runtime falsifiers. Distinct PIDs converged across enable, process replacement, and
disable while each entrant count remained process-local. It held an upload across enable, kept it
visible as one entrant until registration, rejected all five creation routes with typed retryable
503 responses, exercised existing frame/heartbeat/snapshot/events/download/Stop/abort, proved
exact drain status in both processes, preserved quiescence across restart, reopened on double
disable, and failed closed on marker uncertainty. A held render first falsified the old ordering:
the thread was registered while the durable job still looked terminal, creating a false zero-drain
window. The accepted ordering persists `rendering` before thread start and the same probe then saw
and drained it. Review falsifiers then exposed two more false-zero paths: `closed/running` terminal
work counted as zero, and `CancelledError` released an upload entrant while leaving its staging
directory. The accepted correction counts existing `finalization_status=running` truth and aborts
every non-committed upload in `finally`, before admission closes. The probe held the real terminal
pass and cancelled the real upload coroutine, then observed exact `1` to `0` drain and no orphan.
The final construction falsifier failed staging-file open after directory creation but before an
abortable transaction existed. Strong construction cleanup in `JobManager` removed its owned
directory while admission was still `1`; HTTP then returned `400` with admission `0` and no files.
The rerun falsifier pre-admitted before marker enable, wrote a real partial copy under
`quiesced/entrant=1`, and raised. `create_job_from_file` now owns all effects through copy, hash,
record save, and enqueue return; failure removes transient registry state and the new directory
before HTTP returns, without changing the source job or queue.
The final registration falsifiers revoked a Live device between raw creation and authority bind,
and injected durable save failures into resume and render. Raw Live ownership now aborts and joins
the undisclosed session before admission closes. Resume and render mutate a copied candidate,
persist it, and only then publish it to the process registry and worker/thread; save failure leaves
the exact prior memory and disk state with no worker, and a later retry registers once and drains.
The resume concurrency falsifier then held the real worker and interleaved two HTTP requests: both
previously observed `failed`, returned success, and queued the same ID, while one JobRecord hid the
second accepted execution. One manager-local critical section now owns failed-state observation
through durable candidate, registry publication, and enqueue. Exactly one request succeeds, the
competitor receives typed conflict, and injected save/enqueue failure restores the prior state.
That mutation lock alone was then falsified by a fast failure: the first accepted execution became
failed before the second overlapping request acquired the lock, so both requests succeeded and
registered sequential executions. A nonblocking per-Job claim now owns route overlap from entry
through response construction and releases on every success, failure, or cancellation path. The
competitor receives typed conflict without waiting; a genuinely later sequential retry remains
allowed. Once an accepted route has returned, repeating resume while that registered execution is
active preserves Phase-1 idempotency (`200`, same attempt, no second execution); `409` describes
only actual route overlap. The claim preserves request identity, while the existing manager
critical section still owns durable save, registry publication, enqueue, and rollback; neither
duplicates the other.
The one command and full printed states are in the prototype `NOTES.md`. This is
deterministic implementation evidence only; 4070 Ti filesystem, service restart, and deployment
behavior remain unmeasured until the reviewed prerequisite lands and is deployed deliberately.

Issue #21 completes the source-side half of that replacement. The Account application now owns
the only browser UI, HTTP authority, and packaged commands (`mtd-phase2-web` and `mtd-admin`).
The Live protocol keeps one shared transport implementation but only its Account adapter remains;
the File and Live inference runners are constructed by a neutral composition module rather than a
legacy web server. The old global Job manager, shared bearer, pairing/device/view grants, Phase-1
quiesce marker, vector journal, native MOSSCapture client, alternate HTML pages, bearer HTTP replay,
and plaintext launcher are deleted instead of wrapped. Static serving is an explicit Account asset
allowlist, so build-only HTML cannot become a second product entry point.

Before deleting the legacy upload path, its three applicable ingress invariants moved to the
Account File route unchanged: a decimal `Content-Length` is required before body receive, free
space must cover twice the declared body plus 512 MiB, and every request-body or upload-file read
has a 30-second inactivity bound. Refusal creates neither a Meeting nor a staging directory.
Phase-1 histories, Voiceprints, auth records, and jobs have no import or compatibility path; a new
Account database remains empty until that Account creates Meetings. Historical plans and evidence
remain records, not executable product or authority surfaces.

Issue #22 adds the qualification boundary without adding another product runtime. One
`AcceptanceRun` binds one clean Git tree, frozen fixture identities, an embedded clean-wheel
candidate identity, the installed wheel-member RECORD projection, the exact installed dependency
projection, and every deterministic/deployed/pre-admission observation to one exclusive attempt
directory. Failed and interrupted attempts remain evidence; there is no resume, skip, retry, or
force path. The reducer derives G0-G6/G10 from raw predicate-bearing arrays and reports exact
collected, executed, passed, failed, skipped, and unmeasured denominators. Pytest JUnit XML and
Vitest JSON are load-bearing machine reports: a decreased denominator, missing required file, or
skipped required Phase-2/frontend case fails G10 even when the command exits zero. G7 remains
explicitly unclaimed and owned by Issue #23.

Privacy scans are non-vacuous: the mode-0600 qualification profile must supply distinct nonempty
Account-A/Account-B sentinels, both Account session cookies, the Google client secret, and the MOSS
cookie-signing secret. Values remain memory-only; evidence records roles and counts, not values or
paths. The G1 reducer requires the exact foreign read/cursor/frame/heartbeat/Stop/abort/rename/
rerun/resume/retry/download and invalid/revoked-session cases with exact status plus identical
before/after owner state. It also requires zero foreign matches across Account UI, history, Live
snapshot/events, operator status/journal, server logs, and the LLM prompt log.

SQLite 3.53.4 is an exact process invariant checked before database-parent creation or
`aiosqlite.connect`. The smallest measured Linux packaging seam is the official
`sqlite-autoconf-3530400` shared library in a candidate-owned prefix, pinned to published SHA3-256,
loaded only by a separate Account Python 3.12 runtime through scoped `LD_LIBRARY_PATH`. The
candidate stage installs lock-exported dependencies plus the exact clean wheel under an immutable
versioned release, verifies its embedded identity and RECORD projection, and leaves the release
inert beside the live Phase-1 checkout. It does not repoint the live checkout, create the
`account-current` activation pointer, restart vLLM, or mutate the shared GPU environment. Issue #23
alone quiesces Phase 1, seals its large archive, activates that one pointer, and installs the
web-only cutover unit while proving the running vLLM PID, argv, and activation timestamp unchanged.

The retained qualification prototype derived PASS from 38/38 policy falsifiers and separately
measured the Linux exact-runtime path: wrong SQLite refused before any database artifact; the
private prefix reported 3.53.4; `aiosqlite==0.22.1` preserved WAL, foreign keys, `FULL`, schema v1,
and restart truth; and a clean wheel's installed member projection matched its candidate wheel.
The final review falsifiers additionally bind the legal output path to `git_sha`, reject capacity
without measured contended queued/started/processed events, preserve a disposable revoked session
for G5, expose the exact 15/4/8/12/122 campaign units, and require installed `mtd-admin` human and
JSON status to cross the same allowlist. The cutover rehearsal now performs real isolated marker,
two-view drain, archive, manifested-release/unit-byte verification, pointer activation, injected
post-install failure, full-tree restore, and direct vLLM runtime-state comparison. Staging executes
SQLite construction and copies launchers only from the detached candidate checkout; qualification
binds the live web process to that manifested immutable release and active pointer. Final review
made that artifact boundary complete: every reuse rechecks the detached checkout is clean; the
manifest binds the web, admin, and vLLM launchers plus both future-restart systemd units; installed
unit bytes must match. The rehearsal starts with five accepted work units across both runtime
views, observes them unchanged immediately after the marker refuses a new admission, and performs
five explicit continuation transitions to zero before snapshot. G4 now derives pre-Stop inference
RTF from session-scoped canonical and rolling decode elapsed time over exact accepted audio,
excluding only canonical items queued for that Meeting with `reason=stop`; this prevents both
omitted rolling cost and cross-Meeting item-number collisions. Every admitted rolling item must
also have one same-Meeting healthy terminal completion with measured elapsed time, no decode
failure, and zero failed/stale counters. Overload backpressure carries its target/peer ordinals
plus refusal/progress/retry times inside the same eight-session interval.
Real Google OAuth, deployed four-session/600-second capacity, the 12-session frozen quality corpus,
production TLS, and the production-origin pre-admission campaign remain unmeasured until their
external prerequisites exist. Synthetic reducer fixtures cannot close them.

Issue #23 adds one attended cutover state machine rather than a second deployment path. Its public
command can start one new attempt with exactly one declared terminal, `restored` or `preadmission`,
or restore one interrupted nonterminal attempt. Both forward targets block the exact #31 marker,
observe both old runtime views at zero, stop the old web units, seal one complete snapshot, activate
the manifested immutable release, swap only manifested unit/profile bytes, preserve the running
vLLM PID/start/argv, start the Account web unit, and run the same-SHA #22 Wave-1 campaign. The
`restored` target then deliberately enters the same whole-restore primitive immediately after
qualification, without requiring the attended G7 browser.
`preadmission` leaves the candidate running but exposes no admission operation and is reachable only
after the candidate-owned attended collector directly observes both fixed production-origin Chrome
scenarios and reports `G7 PASS`. It accepts host prerequisites, never a caller-authored pass report.
Missing or synthetic evidence restores the whole old image. Interrupted attempts restore from their
own stored profile, manifest, plan, snapshot,
and append-and-fsync journal; they do not depend on the staging source still existing. Candidate
state is moved to an attempt-owned quarantine before old bytes are restored. Snapshot uncertainty
keeps the creation marker present and both web products stopped.

Every forward or restore command holds one nonblocking mode-`0600` host lock under the fixed ext4
state directory. Attempts overlapping candidate state refuse before effects. Each restore effect is
idempotent and journaled, so a process exit during restore remains replayable rather than becoming a
terminal `SAFE_STOPPED`; archive or journal uncertainty remains fail-closed.

The snapshot inventory is explicit and nonoverlapping: the old checkout contains both Phase-1 runs
trees; separate roots name the provider manifest, auth state, shared token, TLS certificate/key,
vector journal, cold generic GPU runtime, and model. Candidate state and the automatically captured
unit/profile/pointer mutation targets cannot overlap those roots. A missing required source refuses
before the marker or any service changes.

The first adversarial extension of `prototypes/phase2-cutover/` measured `RED` at 60/66 assertions:
attempt-local locks, an attempt nested in candidate state, a tenth snapshot role, an interrupted
restore, an attended-browser dependency on the restored target, and an arbitrary HTTPS origin all
violated the contract. The restore-ownership extension then measured `RED` at 78/80: normal restore
rewrote all nine present old-image roots, and replay after an unjournaled web-start effect rewrote
them while both old web units were live. The consolidated failure-boundary extension measured `RED`
at 83/86: persistent journal failure stranded the candidate, unverified marker/listener state was
reported as `SAFE_STOPPED`, and reconstructed files were not fsynced.

The intermediate correction derived `PASS` from 86/86 assertions. It measured one
fixed host lock, exact nine-role nonoverlapping inventory, pre-effect attempt/state refusal, replay
after each of five restore effects, a successful preadmission terminal, Wave-1 followed by planned
whole restore without G7, exact restore after seven forward mutation boundaries, unchanged vLLM
identity, `SAFE_STOPPED` after archive corruption, exact production-origin identity, and rejection
of absent or deterministic-rehearsal G7 evidence at the preadmission boundary. Normal restore now
preserves every present explicit old-image root and reconstructs only a missing root; automatic
unit/profile/pointer mutation targets remain restore-owned. Restore replay stops both web units before
snapshot application and never stops or rewrites the live vLLM process/runtime. Physical rollback is
independent of journal availability, but no durable terminal is claimed when the journal is
unavailable. `SAFE_STOPPED` is published only after exact marker bytes and both unit/listener views are
verified, and reconstructed regular files/directories are recursively fsynced before publication.
The final terminal-authority falsifier measured `RED` at 88/90 when a partial journal tail created a
standalone `result.json`; the corrected probe passed 90/90 by preserving physical blocking/stops but
raising nonterminal restoration uncertainty with no result or terminal record.
The production collector
owns the two real scenarios: microphone plus meeting-tab shared audio, then microphone plus
entire-screen System Audio. It observes display surface/audio track, both meters, exact browser frame
posts, distinct finalized speakers, clean Stop, owner MP3, running source revision, and browser
identity; the outer cutover attempt seals only this content-free projection. Real OAuth, trusted TLS,
attended Chrome capture, and the remote host remain unmeasured locally; this source evidence does not
claim G7 or deploy anything.

## Consequences

- Each wave passes its own release gates plus the cumulative Account/isolation core.
- Reload or browser close ends capture, preserves the received prefix as interrupted, and allows
  only same-Account read-only observation; capture never silently resumes.
- Old unowned content is not imported or assigned an Account.
