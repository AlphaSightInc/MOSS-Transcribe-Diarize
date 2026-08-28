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

`prototypes/phase1-creation-quiesce/` derived `PASS` from 46/46 predicates on Python 3.10.19 and
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
allowed. The claim preserves request identity, while the existing manager critical section still
owns durable save, registry publication, enqueue, and rollback; neither duplicates the other.
The one command and full printed states are in the prototype `NOTES.md`. This is
deterministic implementation evidence only; 4070 Ti filesystem, service restart, and deployment
behavior remain unmeasured until the reviewed prerequisite lands and is deployed deliberately.

## Consequences

- Each wave passes its own release gates plus the cumulative Account/isolation core.
- Reload or browser close ends capture, preserves the received prefix as interrupted, and allows
  only same-Account read-only observation; capture never silently resumes.
- Old unowned content is not imported or assigned an Account.
