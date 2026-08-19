# MOSS Transcribe and Diarize MVP Demo Plan

Status: Proposed implementation plan  
Date: 2026-08-19  
Target: Private LAN and tailnet demo  
Audience: Product, implementation, validation, and demo operators

## 1. Purpose

The MVP demonstrates MOSS as a private, browser-based transcription appliance for a small trusted
group. A user opens the site, selects their preset profile, captures or uploads audio, receives a
speaker-attributed transcript, renames generic speakers for the current session, and exports either
the transcript or its source audio.

The demo must prove that two named users can use the same service without their sessions,
transcripts, controls, or exports crossing. It does not claim public multi-tenant security, durable
speaker recognition, or production-scale concurrency.

## 2. Product goal

Deliver one coherent workflow that a non-technical user can complete without credentials, bearer
tokens, command-line setup, or knowledge of backend session identifiers:

1. Select a preset profile such as `yugao`, `Quinn`, or `Paula`.
2. Start live dual-lane transcription or upload an audio/video file.
3. Read an updating diarized transcript.
4. Rename `S00`, `S01`, and similar labels to meaningful names.
5. Stop and finalize the session.
6. Export transcript text or audio from the left control panel.

## 3. MVP demo statement

> Two people on the private network can independently transcribe meetings at the same time,
> personalize speaker names for each session, and export their own results without seeing or
> controlling the other person's work.

## 4. Trust and security boundary

The demo is available only on explicitly admitted LAN, tailnet, and loopback networks. Non-loopback
access continues to require TLS.

Preset username selection is an identity namespace, not authentication. It prevents accidental
client confusion but does not prevent a trusted-network user from selecting another person's name.
The UI and documentation must not call this secure login.

The MVP accepts this limitation because Google account authentication is a post-demo feature. The
data model nevertheless uses stable internal user IDs now, so future authentication does not require
rewriting resource ownership.

Required protections remain:

- Private-network admission for all application and API routes.
- Same-origin validation for state-changing browser requests.
- Secure, `HttpOnly`, `SameSite=Strict` profile-session cookies.
- Server-side ownership checks on every session, job, transcript, control, media, and export route.
- Cross-user requests return `404` without revealing whether the resource exists.
- Operator-wide listing, provisioning, and revocation remain loopback-only.
- Random resource IDs are identifiers, never authorization.

## 5. Users and ownership model

### 5.1 Preset profiles

Users are provisioned before the demo. There is no public signup or profile creation.

User IDs are case-insensitive. The application trims and lowercases an ASCII identifier at the
boundary, so `YUGAO`, `Yugao`, and `yugao` resolve to one account. Display casing is stored
separately.

Recommended identifier policy: `^[a-z0-9._-]{2,32}$`.

### 5.2 Data model

SQLite is sufficient for the single-process MVP. Enable WAL mode and manage schema changes through
versioned migrations.

| Table | Required fields | Purpose |
|---|---|---|
| `users` | `id`, `username_key`, `display_name`, `enabled`, timestamps | Stable owner independent of login provider |
| `profile_sessions` | `token_hash`, `user_id`, `expires_at`, `last_seen_at` | Browser profile selection and revocation |
| `transcription_sessions` | `id`, `owner_user_id`, `mode`, `runtime_ref`, `status`, timestamps | Ownership and lifecycle for live and file work |
| `file_jobs` ownership extension | `owner_user_id` | Bind existing jobs and media to a user |
| `session_speaker_aliases` | `session_id`, `speaker_identity_key`, `display_name`, timestamps | Session-only speaker rename |

Database usernames and future Google identities both resolve to `users.id`. No session or job is
owned by username, email address, browser address, or display name.

### 5.3 Session lifecycle

| State | Behavior |
|---|---|
| `active` | Capture, transcript updates, and speaker rename allowed |
| `closing` | New capture refused while final work drains |
| `finalized` | Transcript, rename, and export remain available |
| `expired` | Audio, aliases, temporary transcript state, and profile attachment are purged |
| `failed` or `aborted` | Readable terminal result and explicit failure; export only when artifacts are valid |

Stopping transcription moves a session to `finalized`; it does not immediately destroy export data.
Session expiration is the boundary after which aliases and retained live audio are lost.

## 6. MVP scope

### 6.1 Existing capabilities retained

- One browser UI for live and file modes.
- Dual-lane live capture from microphone and shared system audio.
- Streaming transcription and diarization.
- Provisional, confirmed, and final transcript updates.
- Transcript search, copy, auto-scroll, stop, finalization, and browser reattach.
- File upload, progress, queued processing, and transcript rendering.
- Private-network and TLS admission.

### 6.2 New MVP capabilities

| Capability | MVP requirement |
|---|---|
| Profile selection | Select one preset case-insensitive username; server issues profile cookie |
| Ownership | Every live session and file job belongs to one internal user ID |
| Session listing | A user can discover only their own active/finalized resources |
| Speaker rename | Rename a generic speaker for the current session and all transcript surfaces |
| Export placement | Export lives in the left panel, never the transcript floating toolbar |
| Transcript export | Markdown, plain text, and versioned JSON |
| Live audio export | Mixed mono WAV from the exact audio track decoded by the runtime |
| File audio export | Original uploaded WAV, MP3, MP4, M4A, or other admitted media unchanged |
| Concurrent users | Two simultaneous live users at the certified demo bound |
| File concurrency | Multiple users may submit jobs; model inference remains a visible FIFO queue |

## 7. Explicit non-goals for the MVP demo

- Google, Microsoft, Apple, or other third-party authentication.
- Password, PIN, MFA, recovery, or secure resistance to profile impersonation.
- Public internet exposure or untrusted multi-tenant operation.
- Persistent speaker bank, voiceprint matching, or automatic recognition by personal name.
- Speaker-name persistence after session expiration.
- More than two certified simultaneous live sessions.
- Parallel file-job inference.
- Multiple Uvicorn workers or horizontally scaled service instances.
- Live MP3/MP4 transcoding.
- One-click ZIP packages containing transcript and audio.
- Permanent session history, sharing, collaboration, or account synchronization.
- LLM summaries, editable session titles, or advanced transcript editing in the main MVP UI.

## 8. Detailed feature plan

### 8.1 Profile selection and browser identity

Add a profile-selection screen before the transcription workspace. It requests the preset username,
normalizes it, verifies that the user is enabled, creates a random server-side profile session, and
sets the secure cookie.

The workspace displays the selected profile and offers `Switch profile`. Switching ends the browser
profile session, clears local transcript state, and returns to profile selection. It must not stop a
different browser's live session.

The frontend never sends a username as resource authority after selection. The backend derives the
user from the cookie.

### 8.2 Removal of the capture bearer

Remove the visible bearer field, shared bearer state, and bearer propagation from live and file UI
paths. Replace route-level shared-token decisions with `current_user` and resource-owner checks.

The browser capture client uses same-origin cookies for session creation, frames, heartbeat, stop,
abort, snapshot, and events. File upload, polling, media, segments, and export use the same identity.

Legacy operator or non-browser credential flows must not grant one shared principal ownership of all
browser sessions. Any retained non-browser flow receives its own explicitly scoped identity.

### 8.3 Speaker rename

Reuse the reference project's speaker-chip and utterance-label popover interaction. Remove the
voiceprint checkbox and all speaker-bank language.

Before implementation, extend the standing prototype bench to answer one question: does
`speaker_entity_id` remain stable through provisional updates, retrospective relabeling, and final
identity revision? The prototype prints the complete sequence of segment ID, speaker label, entity
ID, state, and alias resolution.

If entity identity is stable, use it as `speaker_identity_key`. If not, use target segment keys and
explicitly migrate aliases when relabel events arrive. Do not choose this policy by inspection.

A saved alias must update:

- Existing transcript turns.
- Future transcript updates for the same identity.
- Legend chips and utterance headers.
- Search labels and match results.
- Clipboard copy.
- Markdown, text, and JSON export.
- Reloaded or reattached views during the finalized-session retention window.

Aliases are stored only under the owning session and cascade-delete when that session expires.

### 8.4 Left-panel export

Add a permanent `Export` section below the mode-specific controls. Follow the reference project's
format selector plus ordinary button pattern.

Export options:

| Option | Result |
|---|---|
| Markdown | Timestamped transcript with resolved session aliases |
| Plain text | Compact timestamp, speaker, and text blocks |
| JSON | Versioned structured turns, identity fields, aliases, and provisional caveat |
| Audio | Live mixed WAV or original uploaded media |

Remove export state, menus, and markup from the floating transcript toolbar. Search, copy, and
auto-scroll remain there.

The button is disabled until the selected artifact is valid. Export never silently omits audio,
returns a partial file as complete, or substitutes a different source track.

### 8.5 Live audio export

Use the existing live tape on the production mixer path. Do not record a second browser-side audio
copy and do not rebuild the mixer in export code.

The deployment explicitly declares a retention root, maximum bytes per session, and a positive
post-finalization export TTL. The initial demo policy is one hour, subject to the measured capacity
check below.

Three PCM16 mono tracks at 16 kHz consume approximately 96 KB/s, or 346 MB/hour. Size the per-session
cap from the maximum permitted meeting duration plus margin. Storage degradation must never stop the
meeting, but it must mark audio export unavailable or incomplete explicitly.

Render the mixed track as mono PCM16 WAV on demand. Verify RIFF size, sample rate, sample count,
duration, gap behavior, and byte identity against the stored mixed PCM. No FFmpeg dependency is
required for WAV wrapping.

### 8.6 File audio export

The existing job directory already preserves the original upload. Export that file byte-for-byte
with its original supported extension. Do not transcode MP3 or MP4 merely to call it an export.

Media and transcript download routes require matching `owner_user_id`. The general jobs list returns
only the current user's jobs. Operator-wide job inspection remains loopback-only.

### 8.7 Two-user concurrency

The current live runtime owns isolated per-session state and round-robin scheduling, but canonical
decoding is serialized through one worker. The MVP does not redesign this scheduler unless
measurement proves that two sessions miss the demo gate.

Certify exactly two concurrent live sessions for at least ten minutes against the intended model
provider. Use distinct speech and markers for each user, saturate one session, reconnect one browser,
then stop both cleanly.

Pre-registered demo gates:

| Gate | Required result |
|---|---|
| Ownership | Zero cross-user reads, writes, controls, aliases, or exports |
| Transcript isolation | Zero other-session markers in displayed or exported text |
| Audio isolation | Exported audio belongs to the requested owning session only |
| Render lag | p95 commit-to-browser render latency at or below 2.0 seconds |
| Transport | Zero unexpected 500 responses and zero sequence gaps |
| Backpressure | 429 is per-session, retryable, and non-terminal |
| Fairness | Round-robin prefix dispatch skew no greater than one item |
| Memory | No OOM and no unbounded RSS/GPU-cache growth |
| Stop | Both sessions reach exact clean accounting within 60 seconds |
| Reattach | Reconnected owner resumes only their own transcript |

Do not add Uvicorn workers. Runtime objects, mixers, event queues, profile sessions, and current
session ownership are process-local in this MVP.

## 9. Implementation sequence

| Phase | Work | Exit condition |
|---|---|---|
| 0 | Prototype speaker-key stability and production-path WAV export | Measured verdicts recorded in prototype `NOTES.md` and design docs |
| 1 | SQLite migrations, preset users, profile sessions, ownership repository | Case-insensitive profile selection and owner lookup pass deterministic tests |
| 2 | Profile UI, secure cookie flow, bearer removal, route ownership | Two browsers cannot read or control each other's resources |
| 3 | Session speaker aliases and reference-style rename UI | Alias survives updates and reattach, then expires with session |
| 4 | Left-panel transcript export and file-media export | All formats contain correct aliases and owning media |
| 5 | Live tape retention, completed-tape lookup, WAV endpoint | Finalized live session exports valid WAV during TTL |
| 6 | Two-user live certification and attended demo rehearsal | Every pre-registered gate passes with raw evidence |
| 7 | Release packaging, operator runbook, rollback procedure | Exact built artifact and deployment configuration are demo-ready |

## 10. Validation plan

### 10.1 Deterministic coverage

- Username normalization, uniqueness, disabled users, cookie expiry, and profile switching.
- Every resource route accepts its owner and rejects another user.
- Cross-user rejection does not disclose resource existence.
- Live and file session creation always records `owner_user_id`.
- Speaker alias resolution across existing, future, relabeled, final, copied, and exported turns.
- Alias deletion at session expiration.
- Left-panel export presence and floating-toolbar export absence.
- WAV header, sample count, duration, and source-track correctness.
- Original file-media byte equality.
- Missing, degraded, expired, and cross-user audio export failures.

### 10.2 Live validation

- Two independent browser profiles with separate preset users.
- Ten-minute concurrent real-model run.
- One overloaded session while the peer remains healthy.
- Browser reload and reattach during capture.
- Speaker rename before and after retrospective refinement.
- Clean stop and export from both users.
- Attended microphone plus real shared-audio capture.
- Restart and expiration behavior for retained audio and aliases.

### 10.3 Evidence reporting

Report static tests, browser tests, real-model tests, attended tests, and operational checks as
separate denominators. A source test cannot certify the built browser bundle, and a synthetic mixer
test cannot certify real capture.

## 11. Demo runbook

1. Provision `yugao`, `Quinn`, and `Paula` in the MVP database.
2. Open two independent browsers or browser profiles.
3. Select `YUGAO` in one and `Paula` in the other, proving case-insensitive selection.
4. Start distinct live sessions simultaneously.
5. Capture microphone and shared audio in both sessions.
6. Show that each transcript contains only its own marker speech.
7. Rename at least two generic speakers in each session.
8. Show the renamed labels on prior and new transcript turns.
9. Stop and finalize both sessions.
10. Export one transcript and one WAV from the left panel for each user.
11. Verify filenames, speaker aliases, audio duration, and session ownership.
12. Attempt one cross-user resource request and show the non-disclosing rejection.
13. Upload an MP3 or MP4 in file mode and export the original media unchanged.

## 12. MVP release criteria

The demo is ready only when all statements are true:

- No bearer field or shared browser bearer remains.
- Preset profile selection works case-insensitively.
- Every live session and file job has one database owner.
- Every resource route enforces that owner.
- Speaker rename updates all current-session surfaces and exports.
- Export is an ordinary left-panel control.
- Live sessions export valid mixed WAV.
- File jobs export the original admitted media.
- Two concurrent live users pass the ten-minute gate.
- Cross-user transcript, control, alias, and audio isolation all pass.
- File-job queueing is visible and does not claim simultaneous inference.
- Retention limits, purge behavior, and operator rollback are documented.
- The exact served browser bundle matches the tested source revision.

## 13. Estimated effort

| Workstream | Estimate |
|---|---:|
| Profile database, profile sessions, and secure cookies | 2-3 engineering days |
| Ownership enforcement across live and file APIs | 2-3 engineering days |
| Session-scoped speaker rename | 1-2 engineering days |
| Left-panel transcript and original-media export | 1-2 engineering days |
| Live WAV retention and export | 2-4 engineering days |
| Concurrency certification and demo rehearsal | 1-2 engineering days with provider available |

Expected MVP implementation and certification: 9-16 engineering days. If serialized canonical
decoding fails the two-user gate, bounded parallel decoding is a separate 1-2 week contingency.

## 14. Post-MVP roadmap

The following features are deliberately deferred until after the MVP demo. They must not expand the
demo critical path.

### 14.1 Real authentication and account lifecycle

- Google OpenID Connect authentication using the provider's stable `sub` claim.
- Explicit linking of Google identity to the existing internal `user_id`.
- Removal of trusted username-only profile selection.
- Login recovery, logout-all-devices, session revocation, and account disablement.
- Role-based operator and administrator permissions.
- Audit records for login, session control, export, and administrative actions.

### 14.2 Persistent speaker bank

- User-owned speaker profiles and voiceprints.
- Explicit consent and retention policy for biometric data.
- Save a renamed session speaker into the user's bank.
- Automatic recognition in later sessions with confidence and refusal thresholds.
- Merge, split, rename, delete, and export speaker profiles.
- Measured false-accept and false-reject gates before automatic naming.

### 14.3 Persistent history and cross-device access

- Searchable session history in the currently collapsed history panel.
- Durable transcript and metadata retention selected by the user.
- Reopen finalized sessions from another device after Google login.
- Configurable deletion and retention windows.
- Download, delete, and ownership-aware session management.

### 14.4 Richer transcript workspace

- Editable session titles.
- LLM summaries and refresh controls.
- Transcript text correction with revision history.
- Speaker merge and split corrections.
- Main-UI integration with the existing subtitle editor workflow.
- Batch files, resumable upload, and visible queue position.

### 14.5 Export expansion

- One-click ZIP bundle with transcript, audio, and manifest.
- SRT, VTT, ASS, and subtitle-editor project export.
- Live audio export as MP3 or M4A through measured transcoding.
- Separate microphone, system, and mixed audio stems.
- Export templates and organization naming conventions.

### 14.6 Higher concurrency and deployment scale

- Certified 4+ simultaneous live sessions.
- Bounded parallel canonical decoding when provider capacity supports it.
- Parallel file-job inference with fair scheduling and quotas.
- PostgreSQL-backed shared identity and ownership state.
- Multiple service instances with externalized sessions, queues, and event streams.
- Per-user quotas, rate limits, storage budgets, and usage reporting.

### 14.7 Public or broader organizational deployment

- Internet-facing reverse proxy and hardened origin policy.
- Google Workspace organization restrictions.
- Administrative user provisioning and group policy.
- Encrypted durable audio/transcript storage and managed key rotation.
- Backup, disaster recovery, observability, alerting, and support runbooks.
- Formal privacy, consent, deletion, and data-processing policy.

## 15. Decision log

| Decision | MVP ruling | Revisit point |
|---|---|---|
| Identity | Preset case-insensitive trusted profiles | Replace with Google OIDC after demo |
| Authorization | Database owner plus secure profile cookie | Add roles and external identity |
| Speaker names | Session-scoped aliases | Add consented speaker bank |
| Live audio | Mixed WAV only | Add stems and compressed formats |
| File audio | Preserve original media | Add optional transcoding |
| Export UX | Left-panel selector and button | Consider ZIP bundle |
| Live concurrency | Certify two sessions | Measure 4+ and parallel decode |
| File concurrency | FIFO single worker | Add fair parallel scheduler |
| Persistence | Export-window session retention | Add user-controlled history |
| Deployment | LAN and tailnet only | Harden for public/organization access |

