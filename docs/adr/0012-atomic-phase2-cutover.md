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
cleaned. Marker existence rejects only new Live create and job create/rerun/resume/render; marker
access uncertainty fails closed. Existing frame, heartbeat, read, download, Stop, abort, accepted
jobs, and startup recovery remain outside the gate and drain normally. `/api/runtime` reports only
the marker state, entrants, active/queued job counts, and active Live count. The marker is not an
authority, database fact, proxy, or second service, and the Phase-2 replacement removes this
legacy seam after old-deployment quiescence is proven.

The cooperating host controls that fact with `mtd-phase1-quiesce enable`, verifies both process
views through `/api/runtime`, and uses `mtd-phase1-quiesce disable` only when abandoning cutover and
reopening the old deployment. All three commands use the same Linux-home marker by default.

## Measured prerequisite verdict

`prototypes/phase1-creation-quiesce/` derived `PASS` from 24/24 predicates against two production
`create_app` instances and the absorbed production gate. It held an upload across enable, kept it
visible as one entrant until registration, rejected all five creation routes with typed retryable
503 responses, exercised existing frame/heartbeat/snapshot/events/download/Stop/abort, proved
exact drain status in both processes, preserved quiescence across restart, reopened on double
disable, and failed closed on marker uncertainty. A held render first falsified the old ordering:
the thread was registered while the durable job still looked terminal, creating a false zero-drain
window. The accepted ordering persists `rendering` before thread start and the same probe then saw
and drained it. The one command and full printed states are in the prototype `NOTES.md`. This is
deterministic implementation evidence only; 4070 Ti filesystem, service restart, and deployment
behavior remain unmeasured until the reviewed prerequisite lands and is deployed deliberately.

## Consequences

- Each wave passes its own release gates plus the cumulative Account/isolation core.
- Reload or browser close ends capture, preserves the received prefix as interrupted, and allows
  only same-Account read-only observation; capture never silently resumes.
- Old unowned content is not imported or assigned an Account.
