---
id: T-26
map: map-002-phase2-multiuser
title: Wave-1 boundary and Phase-1 cutover — accounts, /studio, /live, existing data
type: grilling
status: closed
assignee: codex-20260826-t26
blocked_by: [T-19, T-20]
---

## Question

What exactly ships in wave 1 (C3: accounts + isolation, usable alone), and what happens to
every Phase-1 surface the day accounts arrive?

Decide, with the operator, once *Identity and isolation architecture* and *Authentication
decision* are closed:

- **Wave-1 feature line** — sign-in, allowlist, per-account live capture + transcript +
  file-mode history: precisely which existing surfaces get an owner and which wait (voice
  bank, audio download, LLM are waves 2+; their identities/schema slots are reserved by
  T-19/T-21 so no re-planning).
- **Single auth cutover** — *Identity and isolation architecture* already requires deletion
  of shared, pairing/device, and view tokens with no flag or compatibility mode. Decide the
  bounded outage/deploy sequence for replacing them with Sign-in sessions.
- **`/studio` and `/live`** — Subtitle Studio and the operator diagnostic page: behind
  sign-in, operator-only, or untouched-but-tokened? Each is a potential cross-user window
  (C6).
- **Existing data** — pre-account sessions, journal rows, retained artifacts on the server:
  assign to the operator's account, quarantine, or delete? (Ownerless rows must not be
  reachable post-cutover.)
- **Client reattach** — old token-backed `sessionStorage` does not cross the cutover. Decide
  how active Meetings are drained before deployment and how account-authenticated reattach
  works afterward.
- **Recovery** — restore the whole pre-upgrade snapshot during the bounded outage if cutover
  fails; do not ship dual-auth rollback scaffolding.

Resolution records the wave-1 line, the sunset ruling, per-surface dispositions, the existing-
data ruling, and the cutover/rollback sequence — decision-complete for the AFK builder.

## Resolution

Resolved 2026-08-26 by operator grilling and read-only checks of Phase 1 and the
LiveTranscribe reference. This is a one-way planning decision; it ships no product code.

### Wave 1 feature line

Wave 1 is the first usable multi-user product, delivered in one hard cutover:

- Google Sign-in, exact-email allowlisting, Sign-in sessions, Accounts, and Account-scoped
  Meeting workspaces from *Authentication decision* and *Identity and isolation architecture*.
- Account-owned Live Meetings with durable transcripts and the always-on mixed 48 kbit/s MP3
  artifact from *Audio retention design*. Finished history offers authenticated complete or
  partial MP3 download, or states that audio is unavailable.
- Account-owned File Meetings created from local file uploads or HTTP(S) URLs. Source media is
  working material and is removed after durable terminal transcript finalization or terminal
  failure cleanup; it is never a retained Meeting artifact.
- Durable Account history for Live and File Meetings. Voiceprint banking and language-model
  assistance remain later waves.

### One Account path for interactive and batch work

- MOSS has no product-level administrator role. The Deployment operator's machine/service
  authority grants no Meeting access. When that person uses MOSS, they sign in as an ordinary
  allowlisted Account.
- File mode accepts a multi-select of local files and a newline-separated list of HTTP(S) URLs.
  The browser submits items independently and serially; each accepted item creates one durable,
  Account-owned File Meeting and continues server-side if the browser closes.
- A Batch submission is not a durable domain object: it has no identifier, table, owner, shared
  status, or lifecycle. Per-item failures affect only their Meetings; Account history is the
  durable progress/result view.
- No new CLI credential, admin bit, shared bearer, or operator-only content route ships. SSH is
  for deployment and maintenance, not product use.

### Phase-1 surface disposition

| Existing surface | Wave-1 disposition |
|---|---|
| `/` | Sole product UI: sign-in states, Live/File modes, Account history, transcript, and audio download. |
| `/studio` | Removed; the route is unregistered and returns `404`. |
| `/live` | Removed; the manual view-token portal is unregistered and returns `404`. |
| External plaintext `:7860` | Stopped and no longer published. Batch capability moves behind authenticated `:7861`; it is not a second trust path. |
| Shared-token, pairing/device, and view-token paths | Deleted, including their routes, configuration, browser fields, persistence, and operator tools. No compatibility mode. |
| Legacy `/api/jobs*` surface | Replaced by Account-scoped Meeting operations. Retain only upload/URL create, status, and transcript-read behavior required by `/`; remove rerun/resume, raw-media serving, segment mutation, subtitle/video rendering, and server-side artifact downloads. |
| Application data and runtime-description routes | Require a valid Sign-in session and resolve through one Account workspace. Only authentication entry/callback and non-content deployment health may be unauthenticated. |

### Reference History UI contract

- Reuse LiveTranscribe's collapsible History rail, search, refresh, date groups, Meeting cards,
  duration, selection state, and rename dialog rather than inventing a new layout.
- Show every Account-owned Meeting. Pin active Meetings above terminal Meetings; order each set
  newest first. Cards show title, Live/File mode, start time, status, duration, and audio state.
- Opening a card loads its durable transcript; an active card receives same-Account live updates.
  Owner-written title changes ship in Wave 1.
- Omit the reference Voiceprints tab until the voice-bank wave. Omit Meeting Delete and Clear-all:
  the settled audio lifecycle leaves Meeting/audio storage management with the Deployment
  operator. Add the settled complete/partial/unavailable MP3 action to the reference surface.

### Reattach and browser cutover

- Reattach means Account-authorized read-only observation, never capture resumption. Any
  same-Account browser may reopen an active Meeting and watch its transcript; only the original
  live page continues its already-granted browser media capture.
- Reload or close destroys browser media capture. MOSS never silently restarts microphone or
  screen sharing. It finalizes the received prefix as `interrupted`, publishing a partial MP3
  when recoverable. Continuing capture creates a new Meeting.
- The Phase-1 `sessionStorage` record `{sessionId, viewToken}` and locally entered capture bearer
  do not cross the cutover. The new client ignores/removes those keys and requires Sign-in; no
  old Meeting or authority is reattached.

### Existing-data ruling

- Phase 2 starts with schema-v1 empty Account histories and empty private voice banks. No old
  `runs/` job, speaker-vector journal row, live-auth record, or retained artifact is assigned to
  an Account or exposed through the product.
- Preserve exactly one complete pre-upgrade snapshot outside MOSS for rollback/manual recovery.
  This quarantines old data without asserting an owner. The deployed Phase-1 audio-retention
  path was off, but any bytes found are treated the same way rather than imported.

### Drain, cutover, verification, and rollback

1. Block new Live and File Meeting creation. Drain active capture and queued/running batch work
   to zero; if work remains, postpone deployment rather than force-stop it.
2. Stop the old services and snapshot all Phase-1 persistence/configuration roots as one
   pre-upgrade bundle. No mutation or import is performed inside that bundle.
3. Install the trusted certificate, Phase-2 service/configuration, empty SQLite schema, allowlist,
   and authenticated `:7861`; leave legacy external `:7860` stopped.
4. Before admitting users, prove: allowed and denied Google sign-in; two-Account wrong-owner
   `404` isolation; live Stop to authenticated MP3 download; interrupted partial-audio behavior;
   multi-file and URL File Meetings; reference History behavior; old routes/tokens absent; and
   service/browser restart persistence promised by the closed authentication/persistence tickets.
5. Reopen Meeting admission only after every cutover check passes.
6. Any failure before reopening stops Phase 2 and restores the entire snapshot plus old services.
   There is no dual-auth fallback, partial data merge, or retry loop inside the outage. Once
   traffic reopens, the cutover is accepted and the pre-upgrade bundle is quarantine evidence,
   not a live rollback store.
