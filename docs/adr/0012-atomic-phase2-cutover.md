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

## Consequences

- Each wave passes its own release gates plus the cumulative Account/isolation core.
- Reload or browser close ends capture, preserves the received prefix as interrupted, and allows
  only same-Account read-only observation; capture never silently resumes.
- Old unowned content is not imported or assigned an Account.
