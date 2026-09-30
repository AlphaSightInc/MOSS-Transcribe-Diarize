# ADR-0013: Browser-private workspaces and one complete production launch

Status: accepted by the user September 10, 2026, following adversarial review and a grill-me interview.

MOSS is an internal LAN/Headscale MVP for cooperating users. Replace Google-person admission with an automatically issued browser credential opening one durable workspace; no sign-in, passcode, hardware fingerprint, Reset or Sign-out UI. Preserve owner-bound meetings, generation fences, truthful Stop and crash recovery. Ordinary browser/server restart preserves access; clearing credentials or changing browser profiles loses automatic access, and no linking/recovery is promised.

Implement and validate all three waves sequentially, then perform one production launch after cumulative same-candidate qualification and attended capture proof. Internal test installations are not user releases. No new temporary access gate is needed: the user confirms nobody knows the endpoint. Preserve failed-test recovery and existing data; do not confuse journal admission labels with technical enforcement.

External AI remains browser/device-configured and called directly by that browser. No MOSS proxy or server persistence of provider credentials, endpoint/model/prompt/settings. Validated summary results and necessary meeting/version/lifecycle state remain durable. DNS credentials are a separate explicitly approved exception: store restricted DNS-01 credentials privately for automated trusted certificates and renewal. Keep the existing canonical hostname and Headscale network.

This supersedes Google/allowlist-person identity in ADR-0006/0007, schema-v1 ownership assumptions in ADR-0008, provider-settings provenance persistence in ADR-0011, and separate production-wave release sequencing in ADR-0012. Unrelated invariants, including audio custody, four-session capacity, and accepted voiceprint/diarization behavior, remain binding. New schema/first-tab coordination must be prototyped before production changes; incompatible existing databases are preserved, not silently reinterpreted.

The exact execution and evidence gates are in [the approved completion plan](../production-plan-20260910.md). Quiet-hours audio restrictions and the final attended canary remain separate from silent automation.

Qualification-only revocation evidence may read exact test-created rows through a
read-only SQLite transaction and silently decode their audio. This exception is
limited to disposable candidate roots proven empty by cutover preparation and bound
to the same candidate restore plan. It does not permit database writes, authority
restoration, unrelated/user-data inspection, or a new operator content interface.
Artifacts contain checks and counts, never transcript/audio/credential values.
Measured verdict: `prototypes/phase2-account-lifecycle/REVOCATION_SNAPSHOT_NOTES.md`.

## 2026-09-29 — Gemini engine exception

For the Gemini engine, the server-held Gemini key covers transcription and the
owner-bound live and final summary routes described in ADR-0011. Summary prompt,
language, and model choices arrive with each browser request and are not saved as
Account settings or artifact provenance. External AI remains browser-configured;
the configured key-less tailnet relay retains its separate narrow exception. This
amends the earlier blanket prohibition on server-held AI credentials for Gemini only.

**2026-09-29 amendment (round 3, Q4):** the server-held Gemini key is withdrawn. Each
user enters their own Gemini key in browser Settings; it travels with each Live create,
File/URL upload, summary and provider-test request, is used in server memory for that
meeting/job/request only, and is never persisted (`docs/design-gemini-live.md`, Round 3).
