# MOSS production completion plan — September 10, 2026

Status: adversarially reviewed and explicitly approved September 10. Implementation started on `production/browser-workspaces-20260910`, isolated from `dev` at `e5ff94e8`.

**Quiet-hours constraint:** the user has turned speaker volume down for the night. Do not change volume, play audio, request microphone/screen capture, or launch an attended audio canary without the user resuming it. Unattended file/PCM processing and silent automated browser tests are allowed. Do not claim actual device-capture acceptance from those tests.

This plan supersedes the recommendations and execution order in `health-and-fast-track-20260909.md`. That document's dated health observations remain historical evidence, not current availability claims.

## Outcome and settled decisions

Finish the complete existing three-wave project before its first production launch. Implement and validate incrementally; do not confuse internal candidate testing with release to users.

- **D1 — Automatic browser-private workspaces.** No Google login, passcode, capture-bearer entry, or hardware fingerprint. A server-issued browser credential opens one durable workspace. Different profiles/browsers have separate histories; a shared profile shares its history. Cookie clearing/private browsing/new profiles lose automatic access to the old workspace. No recovery/linking or Reset/Sign-out UI in this MVP.
- **D2 — Browser-trusted HTTPS.** Keep the existing Headscale network and canonical product hostname. Use DNS-01 certificate issuance and renewal with a privately stored, restricted DNS credential. User approved storage of that credential for this purpose. Never request its value in conversation. The credential itself has not been provisioned/found by this session; only lego availability was verified.
- **D3 — Complete all three waves before launch.** Wave 1: transcription, browser workspaces, history, audio and export. Wave 2: manual speaker naming and workspace-private voiceprints. Wave 3: optional external AI final summaries. Keep existing quality and four-session capacity requirements. No reduced-core early production rollout.
- **D4 — No temporary access gate.** User confirms no users know the current endpoint/port; it is an internal development/testing surface. Do not add a network maintenance exclusion or admission framework. Retain failure rollback and truthful state reporting. `admitted=False` in a journal is not technical access enforcement. Do not announce/open the production release before completion.
- **D5 — External AI stays browser/device-owned.** Endpoint, model, API credential, prompt, language and request/retry settings remain in the initiating browser, which calls its external provider directly. No MOSS proxy, central settings, server-side credential storage, settings synchronization, or server-side fallback. Empty settings disable summaries, never transcription. Validated summary results and meeting/lifecycle versions remain durable in MOSS history; provider settings/credentials are not copied into server provenance or logs.

## Structural contract

**Question:** can automatic browser admission preserve durable, isolated meeting work while all three existing feature waves become genuinely qualified?

**Minimum primitives:** network reachability admits cooperating clients; a browser credential establishes continuity; a workspace owns meetings; a meeting owns durable transcript/audio/summary results; the initiating browser owns optional external summary execution. Removing one loses admission scope, continuity, isolation, saved results, or device-owned AI configuration respectively. Keep these independent of the replaceable inference provider.

**Invariants:** no typed application credential; two tabs converge on one browser workspace before either admits work; separate workspaces cannot read/change each other's content; saved results survive ordinary browser/server restart; Stop never reports success before required durability; interrupted capture does not restart silently; AI failure never delays speech or audio finalization; AI settings never pass through MOSS.

**Unknowns:** first-bootstrap multi-tab coordination, actual old candidate databases, certificate credential availability/renewal, direct-browser provider HTTPS/cross-origin compatibility, current integrated quality/capacity, and unattended Windows/WSL recovery. Inspect or measure these; do not turn them into speculative frameworks.

**Falsifiers:** a fresh user must enter application credentials; tabs split workspaces; cookie loss silently switches an in-flight mutation to a new owner; cross-workspace content leaks; Stop loses acknowledged work; summary settings appear server-side; a gate is green without measured production-path evidence.

**Tools:** existing lifecycle/store and browser probes establish the identity design; targeted regression tests establish source fixes; existing speech/voiceprint/concurrency benches establish quality; disposable candidate testing establishes integration; one attended capture canary establishes actual device permissions/audio. Prototype new policies before production code. Do not re-litigate the accepted diarization architecture.

## Adversarial review dispositions

- **R1 — Candidate accessibility before qualification:** observed, but the proposed maintenance exclusion is withdrawn under D4. Preserve ordinary cutover failure recovery. Separately document post-release rollback: current `CutoverRun.restore()` refuses terminal attempts and is not a later-release/data rollback command.
- **R2 — Exact process verification:** fix collector recognition of the approved `python -I -m moss_transcribe_diarize.app.phase2_web_cli` invocation. Current collector expects `-m` at argv index 1 while the launcher supplies `-I`. Test approved invocation, wrong executable, and wrong module; do not bypass identity verification.
- **R3 — Cookie loss/reset:** D1 settles continuity limitations. Existing logout only settles origin-bound Live work and must not become a generic workspace Reset while File work exists. Omit Reset/Sign-out UI. Missing/invalid credentials during mutations visibly stop access; only explicit application bootstrap may create a new workspace. Workspace revocation cannot ban an anonymous person from creating another workspace; network admission owns that concern.
- **R4 — Schema and tabs:** Google-subject/email/allowlist requirements cannot be removed solely by changing routing. Inventory candidate state; create an explicitly distinct schema version for a genuinely empty browser-workspace deployment. Refuse incompatible old databases rather than silently redefining schema v1. Preserve any real data; no fabricated Google subjects/emails, destructive reset, or generic migration framework. Prototype concurrent first-tab initialization.
- **R5 — Full qualification:** implement actual G8/G9 producers and evaluators; they currently remain `unmeasured`. Extend the Wave-1-only cutover validator so the final launch requires cumulative core plus G8/G9 on the final integrated candidate and an actual attended G7 canary. Include the existing eight-session overload probe without changing supported four-session capacity. Change Google predicates and profile prerequisites together. Same-origin mutation checking is an explicit implementation/test task, not an already-proven existing safeguard.
- **R6 — Human capture proof:** current supported Live capture requires both microphone and shared-audio signal. Preserve the documented Chrome/macOS capture scope; Safari/Windows parity is not silently added. A sample-file demonstration cannot qualify microphone, meeting-tab audio or entire-screen System Audio. Keep one guided attended canary covering those paths.
- **R7 — Integration discipline:** merge-only, no rebasing existing ticket-24 work. Preserve its dirty changes. Sequential wave implementation remains, but the old requirement for separate user-facing wave releases is superseded by D3.

Evidence: `ops/account-web-launcher.sh:25`; `moss_transcribe_diarize/phase2_acceptance_external.py:507`; `moss_transcribe_diarize/phase2_acceptance.py:2159`; `moss_transcribe_diarize/phase2_cutover.py:760`, `:1067`, `:1238`, `:1304`; `moss_transcribe_diarize/app/phase2.py:269`, `:321`, `:914`; `moss_transcribe_diarize/app/phase2_lifecycle.py:127`; charter G4/G7–G9 and ADR-0011. Line numbers refer to the reviewed `e5ff94e8` source.

## Ordered autonomous execution

### A1 — Create branch/worktree and update the binding contract

After final confirmation, create a new isolated implementation branch/worktree from verified `dev` (`e5ff94e8` at review). Preserve the existing reports and unrelated worktrees. Bring this plan into that worktree. Update the relevant glossary, admission ADR, charter, summary privacy/provenance expectations and wave-release wording to D1–D5. Keep settled diarization, audio and lifecycle semantics unchanged.

**Exit:** branch and source identity recorded; governing docs agree; no unrelated changes lost.

### A2 — Prototype identity and schema using real interfaces

Use disposable state and the existing lifecycle bench. Exercise server-issued cookie bootstrap, persistence after browser/server restart, two persistent browser profiles, simultaneous first tabs, invalid/deleted/blocked cookies, and active-work credential loss. Both tabs must converge before work admission. Preserve owner-bound meeting handles and authority fences; do not disguise a new owner as a Google account. Measure and record a one-command verdict, then incorporate useful tests.

Inventory actual candidate databases before choosing their initialization path. Empty new deployment gets the explicit new schema; any real incompatible state is preserved and reported before a conversion decision.

**Exit:** measured continuity/isolation with a clear schema contract; no production data touched by the prototype.

### A3 — Implement Wave 1 and remove qualification bootstrap blockers

Implement the measured admission seam and browser entry, remove Google-required startup/profile configuration and bearer-entry UI, and retain meeting/file/live/audio/recovery primitives. No auth-mode flag or new identity provider framework. Use server-issued persistent HttpOnly/Secure/host-only cookies; bootstrap responses are not cached. Missing-cookie mutations do not transparently change owner.

Fix R2's exact isolated-process check with regression coverage. Repair acceptance producers, evaluators and profiles together: workspaces/cookies originate from real application bootstrap; sentinels are attempt-owned; real journal entries replace nonexistent log files. Do not fabricate credential files, write direct database fixtures into the tested runtime, or turn missing evidence into empty-file success. Replace the unsuccessful `[humming]` success fixture with validated real speech, preserving the former as an expected failure case.

**Exit:** installed app starts without Google configuration; automated acceptance starts without human login/token copying; focused and full Wave-1 regressions pass with exact counts.

### A4 — Implement Wave 2 on the proven workspace model

Review and integrate existing ticket-24 work without rebasing or discarding edits. Keep voiceprint ownership within the browser workspace, labels display-only, and enrollment/matching on the accepted production path. Implement real G8 measurement/evaluation, including changes to the new owner schema. Reuse the standing voiceprint/diarization bench.

**Exit:** manual naming, bank operations, matching, persistence and isolation meet existing G8 requirements; no placeholder `unmeasured` gate or invented threshold.

### A5 — Implement Wave 3 with browser-only external AI

Deliver device-local provider settings and browser-originated external requests. No configuration entry is required to record or transcribe; only users choosing summaries configure their provider. Send only the current finalized transcript and browser-owned request parameters to that provider. Keep API configuration/credentials out of MOSS requests, storage, status, traces and logs. Store validated summary results plus necessary meeting/version/lifecycle metadata, not copies of provider settings.

Retain the accepted final-only five-field output, serial work, bounded retry/cancel behavior and speech non-interference. Implement real G9 producers/evaluators, including actual browser reachability, trusted HTTPS and cross-origin behavior. A provider incompatibility is reported explicitly; it does not justify a server proxy. Automated tests may use a controlled external test endpoint but must not mislabel it as qualification of every user's provider.

**Exit:** configured browser produces and persists valid summaries; blank settings leave transcription fully usable; no provider settings/credential reaches MOSS; G9 is genuinely measured.

### A6 — Finish access and operator automation

Automate trusted DNS-01 certificates/renewal using a least-privilege DNS credential in a private host file. Prefer already installed tooling; do not print credentials or put them in commands/chat. Keep one canonical hostname across LAN/tailnet; validate the supported client name-resolution paths. No public app exposure or network migration. Distinguish DNS credentials approved for automation from AI credentials prohibited on MOSS.

Prepare MOSS-specific service startup, journal collection, status, health checks and consistent SQLite-plus-audio backup/restore instructions. Do not restart the working model merely to change the web app. Do not reboot Windows/stop unrelated workloads without a separately scheduled maintenance opportunity. Correct the final one-web-service topology, not the old Phase-1 pair.

**Exit:** fresh-browser HTTPS works without exceptions; renewal is tested; operator instructions name real working paths. Any missing credential/manual infrastructure prerequisite is reported precisely while other implementation continues.

### A7 — Qualify the final integrated candidate

Freeze a complete three-wave candidate; stage it immutably. Prior wave tests are development evidence, not substitutes for the final candidate. Run backend/frontend regressions, real file/URL/live flows, owner isolation, history/export/audio, restart/reconnect, interruption/failure cases, voiceprint G8, and summary G9.

Run the existing four-Live-meeting/600-second capacity campaign, ≤10-second per-session p95 lag and all other accepted G4 bars; run the mandatory eight-session overload/backpressure probe and six-case/two-pass quality corpus. Supply or explicitly reconcile required missing corpora; report exact passed/failed/skipped denominators. No threshold weakening, mixed-SHA release claim, or retry-until-green evidence.

Internal qualification installations use disposable candidate state and existing test-rehearsal restoration where appropriate. They are not user launches, and test workspaces are not production data. No added access-exclusion mechanism under D4. Final cutover must require complete same-candidate core/G8/G9 evidence rather than its current Wave-1-only bundle.

**Exit:** complete final integrated evidence; preserved failures; final release gate cannot pass on unfinished waves.

### A8 — Human canary, completion and production launch

Provide a short step-by-step Chrome/macOS canary: fresh-browser trust, no application credential entry, sample/file flow, real microphone plus meeting-tab audio, entire-screen System Audio, truthful Stop, playback/export, reopened history, second-profile isolation, and optional configured-provider summary. Actual browser/OS permissions and sound routing cannot be certified unattended.

After all three waves and required canaries pass, perform the first production launch under the reviewed cutover/runbook and verify served candidate identity. Preserve the Phase-1 archive; do not erase saved results. Distinguish failure recovery during qualification from rollback after real user data exists. Complete a controlled restart/restore exercise; schedule whole-host cold-boot validation separately if it would affect other projects, and do not claim it verified until measured.

**Exit:** finished integrated product, trusted supported browser access, real capture proof, measured release gates, truthful operational handoff. No early core-only rollout.

## Minimal human work

- **M1 — DNS credential:** if none exists, create/provide restricted NS1 DNS-01 authority through a private file, never chat. Agent will provide exact steps, configure issuance/renewal and validate it. No secret is needed to begin application implementation.
- **M2 — Real audio canary:** perform browser/OS permission choices and audible microphone/shared-audio checks when the agent has everything ready. No login/token/terminal setup for the app.
- **M3 — Shared-host reboot scheduling:** only if needed to complete cold-boot proof; coordinate a safe time, not an unscheduled autonomous reboot.

Optional summaries necessarily require a user's device-local external provider settings under D5. This is an opt-in feature prerequisite, not an application onboarding requirement. Users who only transcribe never need those settings.

## Stop/continue rules

Continue autonomously with scoped implementation, tests, packaging and evidence. Missing DNS credentials do not stop independent feature work. Escalate only new consequential choices, incompatible real data, missing infrastructure authority, actual browser/provider access requirements, or a shared-host interruption. Do not repeatedly ask the already settled D1–D5 questions. Do not mark production ready while a required gate is unmeasured or failed.
