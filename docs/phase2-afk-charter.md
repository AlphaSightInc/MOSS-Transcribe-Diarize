# Phase 2 AFK charter — authority, product contract, sequencing, and acceptance gates

This is the binding implementation handoff for Phase 2. It records planning decisions; it does
**not** claim that Phase-2 product code, deployment, or certification exists. AFK implementation
tickets must cite the applicable Phase-2 ADRs and this charter section. A builder may choose local
code mechanics, but may not change the product behavior or acceptance bars below without an
operator decision backed by new evidence.

## 1. Authority and hard limits

- Product repo: `aiSight-us/MOSS-Transcribe-Diarize`; never create implementation work on upstream
  `OpenMOSS`.
- Product branch: `dev`. Preserve unrelated dirty work. Do not clean, stash, reset, switch, or
  commit paths outside the claimed implementation ticket.
- Trust boundary: a known team of about 2–10 people on the tailnet. Public exposure and open signup
  are not part of this effort.
- Capacity: one MOSS process on the current Windows/WSL host, supporting four concurrent Live
  Meetings. Multiple Uvicorn workers, horizontal scale-out, and multi-process ownership are out.
- Phase 2 starts with empty schema-v1 Account histories and empty private Voiceprint banks. No
  Phase-1 run, shared token, view grant, speaker journal row, or artifact receives an Account owner.
- The deployed operator cooperates and owns the machine. Machine authority grants no product
  content access; the operator signs in as an ordinary allowlisted Account to use MOSS.
- This charter inherits the Phase-1 merge-only serialization protocol in
  `docs/phase1-afk-charter.md`: acquire the shared merge lock; merge current `dev` into the ticket
  branch; validate the merged result; fast-forward `dev`; revert a breaking merge. Do not rebase.

## 2. Binding ADRs

- [Account workspace isolation](adr/0006-account-workspace-isolation.md)
- [Google OIDC and revocable sessions](adr/0007-google-oidc-and-revocable-sessions.md)
- [SQLite Account-owned persistence](adr/0008-sqlite-account-owned-persistence.md)
- [Private Account Voiceprint bank](adr/0009-private-account-voiceprint-bank.md)
- [Owner-private mixed MP3](adr/0010-owner-private-mixed-mp3.md)
- [Browser-owned Final summary](adr/0011-browser-owned-final-summary.md)
- [Atomic cutover and three waves](adr/0012-atomic-phase2-cutover.md)

Operator observability is deliberately too small and reversible for an ADR; its exact contract is
in §7. Acceptance gates are in §9.

## 3. Canonical domain and ownership

- **Account**: the product principal, keyed only by verified Google `sub` (`AccountId`). Email is
  exact allowlist policy and display data, never identity.
- **Sign-in session**: one opaque revocable MOSS session for one Access client and Account. Browser
  or device identity supplies no authority.
- **Meeting**: the single durable ownership root for Live, uploaded-file, URL, and batch-created
  work. Each Meeting has exactly one Account owner.
- **Meeting artifact**: transcript, retained audio, or Final summary owned through its Meeting.
- **Voiceprint**: an opaque acoustic reference owned directly by one Account because it spans
  Meetings. Its non-unique label is display text, not identity.
- **Resource identifier**: locator only. It never conveys identity, Account ownership, or access.
- **Event cursor**: a position inside an already authorized Meeting event stream. It cannot be
  replayed to open another stream.
- **Operational metadata**: the exact content-free facts allowed through the host-local operator
  surface in §7.

Authentication opens one deep Account workspace. Its external interface is `list meetings`,
`create meeting`, and `open meeting`; `open meeting` returns an owner-bound Meeting handle used for
snapshot, events, control, transcript, audio, Final summary, and allowed mutations. Routes do not
accept `account_id`; owned repositories expose no global resource lookup. Background work carries
the owner internally. Wrong-owner identifiers return `404`; invalid or revoked Sign-in sessions
return `401`.

## 4. Wave 1 — Accounts, Meetings, history, and audio

### 4.1 Authentication and admission

- Google-only authorization-code flow through Authlib 1.7.2 with PKCE S256, `state`, `nonce`, and
  scopes `openid profile email`; no refresh token. Reject invalid signature, issuer, audience,
  expiry, state, nonce, or `email_verified`.
- Reuse Google project `ragtest-497122`, but create a separate MOSS Web OAuth client. Exact callback:
  `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861/auth/google/callback`.
- Auth routes are `GET /auth/google`, `GET /auth/google/callback`, `POST /auth/logout`, and
  `GET /api/auth/session`.
- `account_allowlist` is the sole admission policy. The host-local CLI exposes
  `mtd-admin accounts allow EMAIL`, `accounts list`, and `accounts revoke EMAIL`. Normalize only by
  trimming and lower-casing; do not normalize Gmail dots/aliases or admit a domain.
- First successful callback binds an enabled email to Google `sub`. Later email change may reopen
  the same `sub` only after the new exact email is allowed. An email already bound to another `sub`
  is denied and transfers nothing. A denied callback creates neither Account nor Sign-in session.
- The temporary `__Host-moss_oauth` cookie is Secure, HttpOnly, SameSite=Lax, Path=/, lasts ten
  minutes, and is cleared after callback/denial/error. The persistent `__Host-moss_session` cookie
  has the same attributes, no Domain, and contains only `secrets.token_urlsafe(32)` output.
- MOSS sessions have no idle or absolute expiry. Application bootstrap resolves the SQLite session
  and enabled Account and refreshes the browser cookie to 400 days. Poll/frame/event requests do
  not rewrite it. Browser and server restart preserve the session.
- Sign-out performs normal Stop and waits for transcript/audio durability before revoking that one
  session; a Stop failure leaves the browser signed in. Account revoke disables the Account,
  revokes every session, fences new capture/results, and durably marks all active Meetings
  `interrupted` before the CLI returns. The next request from each revoked browser is `401` and the
  browser stops local capture visibly. Other sessions survive single-browser sign-out.
- Keep origin and explicit port `:7861`; use a browser-trusted Let's Encrypt certificate for
  `ga0-alienware-rtx4070ti.tailnet.aisight.us` obtained by lego 5.3.1 through NS1 DNS-01. Load a
  renewed certificate only at a zero-Live-Meeting restart.

### 4.2 Persistence

- SQLite runtime 3.53.4 via aiosqlite 0.22.1; one long-lived connection; WAL,
  `foreign_keys=ON`, `synchronous=FULL`; one transaction per Account-workspace mutation.
- Schema v1 has ten application tables: `account_allowlist`, `accounts`, `sign_in_sessions`,
  `meetings`, `meeting_transcripts`, `meeting_speakers`, `meeting_audio`, `voiceprints`,
  `voiceprint_samples`, and `llm_artifacts`. The later audio decision's `meeting_audio` name is
  canonical and supersedes the earlier generic `audio_artifacts` name.
- Every user-owned table carries `account_id`. Meeting children carry composite
  `(account_id, meeting_id)` ownership; Voiceprint children carry composite
  `(account_id, voiceprint_id)` ownership. Cross-Account foreign keys cannot be represented.
- One current structured transcript document and version is persisted after every accepted
  transcript commit. Events/cursors are not durable. The 250 ms poll path reads memory, not SQLite.
- Filesystem owns only large Meeting audio. There are no JSON projections, audio BLOBs, durable
  event/cursor/device/view-grant tables, or separate durable batch/job object.
- Missing database initializes once with `PRAGMA user_version=1`; an existing non-v1 database is
  refused. No migration framework, downgrade, retry framework, or compatibility layer ships.
- Crash recovery retains the last committed transcript and maximal recoverable audio prefix,
  marks every formerly active Meeting `interrupted`, exposes it in Account history, and never
  resumes capture.

### 4.3 Product surface and Meeting lifecycle

- `/` is the sole product UI. It contains Google sign-in states, Live/File modes, Account history,
  transcript, title rename, and audio action.
- `/studio` and `/live` are unregistered `404`s. External plaintext `:7860`, shared bearer,
  pairing/device tokens, view tokens, and legacy `/api/jobs*` authority paths are removed. Only
  authentication entry/callback and content-free deployment health may be unauthenticated.
- Live and File Meetings share one durable shape. File accepts multi-select uploads and
  newline-separated HTTP(S) URLs. The browser submits items serially; each accepted item becomes
  an independent Account-owned File Meeting that continues server-side if the browser closes.
  “Batch” has no durable ID, table, owner, status, or lifecycle.
- Reuse LiveTranscribe's collapsible History rail, search, refresh, date groups, cards, selection,
  and rename dialog. Show active Meetings first, then terminal, newest first. Same-Account devices
  see identical history and live updates.
- Reopening an active Meeting is read-only observation. Only the original live page continues its
  already-granted browser media capture. Reload/close ends capture, finalizes the received prefix as
  `interrupted`, publishes partial MP3 when recoverable, and requires a new Meeting to continue.

### 4.4 Meeting audio

- Retention is always on. Preserve only the exact transcription mix as MP3/MPEG Audio Layer III,
  16 kHz, mono, constant 48 kbit/s. Raw lanes, raw mixed PCM, and WAV are working material and do
  not survive normal terminal cleanup.
- Audio is for human download/playback only. It is never later ASR, diarization, Voiceprint, or
  language-model input.
- Root: `/home/devcontainers/.local/share/moss-transcribe-diarize/meetings/`.
  Complete path: `<root>/<account_id>/<meeting_id>/audio.mp3`; partial path ends
  `audio.partial.mp3`. Directories are `0700`; files `0600`; SQLite stores root-relative paths.
- The Meeting audio archive module owns staging, sealing, synchronous encoding, atomic publish,
  metadata commit, cleanup, recovery, status, and owner-authorized download.
- Normal Stop returns complete only after transcript and audio have reached durable terminal state.
  Audio is exactly `available`, `partial`, or `unavailable`. Crash/degradation publishes the
  maximal usable prefix as partial; no usable prefix becomes unavailable. Audio failure never
  fails or deletes the transcript.
- `GET /api/meetings/{meeting_id}/audio/download` serves the complete MP3 attachment to the owning
  Account. There is no byte range/resume. History shows Download audio, Download partial audio, or
  Audio unavailable; there is no embedded player.

## 5. Wave 2 — private Voiceprint bank

- One Account owns one server-side bank. A Voiceprint carries opaque ID, non-unique label, immutable
  embedder ID/dimension, and samples. Labels never find, select, merge, or update a Voiceprint.
- The Account Speaker Identity module owns match evidence, manual naming, list, rename, and delete.
  Callers pass owner-bound Meeting handles, never Account IDs or database rows.
- Active manual naming rewrites that Meeting Speaker's transcript rows immediately. If already
  linked, it renames that exact Voiceprint and upserts the source sample; if unmatched, it creates a
  new Voiceprint even when labels duplicate.
- Enrollment uses the existing quality-gated album centroid at the 2.0 s floor; it never re-embeds
  audio or imports the Phase-1 journal. If evidence is not ready, retain one replaceable pending
  intent; the first eligible centroid completes exactly one sample. Stop/abort/crash clears an
  unfulfilled intent but preserves transcript text.
- Matching uses clamped cosine `>=0.46`, no runner-up margin, at least 1.0 s eligible speech, and
  the L2-normalized arithmetic mean of samples. Apply to live evidence and terminal album centroid;
  otherwise abstain as `Speaker N`. Automatic matches never add samples.
- Bank revision changes are visible immediately to all same-Account active Meetings. Bank rename
  relabels linked active Speakers; stopped transcript labels remain recorded. No separate
  `speaker_renamed` event is added.
- An incompatible embedder ID/dimension disables only that Voiceprint and shows re-enrollment
  required. Delete by opaque ID removes samples/links, cancels pending updates, advances revision,
  rejects older-revision in-flight results, and preserves historical transcript labels.
- Bank UI is list, rename, and delete. Merge, per-sample controls, standalone creation, WAV upload,
  and microphone enrollment are absent.

## 6. Wave 3 — browser-owned Final summary

- Generate one Final summary only after the Meeting transcript is authoritative and finalized.
  Live, file, URL, and batch-created Meetings use the same contract. No rolling summary, live
  formatting, name enrichment, reformat, reconciliation, or separate title call ships.
- The initiating browser is the LLM worker. Endpoint, model, bearer token, V15/custom prompt,
  target language, timeout, and retry schedule live only in that browser's local storage. Blank
  endpoint/model disables calls; Clear removes values. The server never stores or serves them.
- Browser calls non-streaming OpenAI-compatible `POST /v1/chat/completions` and reads
  `choices[0].message.content`. `/v1/models` is not required. Requested model is provenance, not a
  verified identity. Chrome must reach and trust the configured endpoint and its CORS policy.
- Send only this Meeting's finalized transcript, browser prompt, and request parameters. Never send
  audio, Voiceprints, another Meeting, Account history, or Account identifiers.
- Default to `prototypes/client-configured-llm/final-summary-prompt.txt`. Accept raw JSON with
  exactly `summary`, `topics`, `details`, `speaker_background`, and `data_references`; validate
  five field types, nonempty summary, and in-range `HH:MM:SS` detail timestamps. Do not invent,
  truncate, repair, or enforce digit coverage after inference.
- Browser serializes ready Meetings. Server admits at most one active summary attempt per Meeting.
  Initial delivery plus identical retries after 60, 120, and 240 seconds are allowed only for
  network error, timeout, HTTP 408/429, or 5xx. Invalid output and other HTTP errors fail
  immediately. Cancel aborts current/scheduled work; owner-only Retry starts a fresh capped group.
- Persist states `queued`, `generating`, `retry_wait`, `current`, `failed`, and `cancelled`, plus
  validated output, source/artifact versions, requested model, prompt profile, and automatic title.
  `topics[0].title` becomes title only when present and no owner-written title exists.
- `llm_status` and `llm_summary_update` become reachable. `llm_format_update` remains unreachable.
  Same-Account clients may read the artifact; view/history clients never call automatically.
- Speech finalization, audio durability, and history never wait for the LLM. LLM inference runs
  outside the speech server and consumes no server ASR VRAM or scheduling slot.

## 7. Operator observability and control

- Human surface: host-local `mtd-admin status`; exact machine surface: `mtd-admin status --json`.
  Both call one Operator Control module through a service-user-owned Unix-domain socket mode `0600`.
  No TCP/admin web/metrics endpoint, second daemon, or direct live-SQLite CLI exists.
- The module interface is only `snapshot()` and `interrupt(meeting_id)`. It cannot open an Account
  workspace or Meeting artifact.
- Status fields are limited to:
  1. readiness; active Live count against four; active File count; inference worker state; queue
     depth by `live_canonical`, `live_refinement`, `live_provisional`, and `batch`; backpressured
     Meeting count;
  2. Account email/display name, enabled state, Sign-in-session count, active Live/File counts;
  3. active Meeting email, opaque ID, mode, lifecycle, UTC start, elapsed time, safe error, plus
     Live capture phase, lane health/age, pending canonical count/limit, and backpressure state;
  4. free bytes per SQLite/audio filesystem, SQLite/WAL physical bytes, retained-audio counts/bytes
     by state host-wide and per Account, and per-Account logical Meeting/transcript/Voiceprint/Final-
     summary counts; and
  5. safe latest error: UTC occurrence, subsystem, stable code, severity, terminal/retryable,
     occurrence count, and allowlisted numeric/enumerated context only.
- Exclude Google `sub`, avatar URL, historical email, session secret/ID, device/activity data,
  Meeting title/status text, transcript, audio/waveform, source name/URL, Voiceprint label/vector/
  sample, prompt/output/endpoint/model/token, raw exception/locals/body, filesystem path, and
  fabricated per-Account physical SQLite bytes.
- `mtd-admin meetings interrupt MEETING_ID` accepts only an active Meeting, is idempotent, fences
  new capture and late results, removes queued inference, and returns only after durable
  `interrupted` state. Preserve last transcript and maximal Live-audio prefix; File working source
  is removed after in-flight use ends.
- Structured journal events exist only for readiness, Account admission/revocation, Meeting
  lifecycle, capture health, backpressure, artifact state, safe error, and operator mutation. No
  per-frame/periodic status log or MOSS audit-log table ships.

## 8. Release topology and evidence contract

The **cumulative core** is G0–G6 plus G10 below.

- Wave 1 passes the cumulative core and G7.
- Wave 2 reruns the cumulative core and adds G8.
- Wave 3 reruns the cumulative core and adds G9. It need not rerun the full Voiceprint corpus, but
  an owner transcript containing Wave-2 labels must pass the Final-summary privacy path.

Every wave must pass three evidence layers on the same candidate commit:

1. deterministic contract/adversarial tests;
2. deployed 600-second four-session campaign split across at least two Accounts, with continuous
   wrong-owner probes; and
3. production-origin pre-admission canary after installation.

One required failure blocks the wave. Preserve failed evidence. After a fix, create a new complete
wave evidence bundle; do not retry a failed case until it happens to pass. Report exact collected,
executed, passed, failed, skipped, and unmeasured denominators.

### Required harness locations

- Deterministic tests: `tests/phase2/`.
- One-command driver: `scripts/phase2-acceptance/run.py`.
- Evidence: `evidence/phase2/wave-<n>/<UTC>-<git-short-sha>/`.
- Voice matching: `prototypes/streaming-diarization/voice-profile-matching/`.
- Concurrency semantics: `prototypes/streaming-diarization/concurrency/`.
- Audio format baseline: `prototypes/streaming-diarization/audio-retention-format/`.
- Fake OpenAI-compatible endpoint and recorded output fixtures:
  `prototypes/client-configured-llm/`.

The implementation is not gate-ready until this command exists and prints full relevant state:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/phase2-acceptance/run.py \
  --wave <1|2|3> --output evidence/phase2/wave-<n>/<UTC>-<git-short-sha>
```

The driver records candidate Git SHA, dirty-state refusal, command, service/runtime/dependency
versions, production descriptor, fixtures/corpora, exact case denominators, raw predicate-bearing
arrays, browser/server logs after content-boundary checks, and the final gate table. Stub/fake
inference may exercise deterministic state paths but never qualifies a real inference/capacity bar.

## 9. Exact acceptance gates

### G0 — Candidate and evidence identity

All three layers execute the same committed candidate. The installed service reports that candidate;
the driver refuses scoped product/test modifications. Required artifacts and denominators exist and
the environment is left with zero active/queued Meetings. Missing evidence is failure, not zero.

### G1 — Adversarial Account isolation

Create Accounts A and B with unmistakable sentinel transcript, title, audio, Voiceprint label, and
Final-summary values. Cross every public read/mutation interface and direct route with the other
Account's Meeting, live-session, cursor, File-Meeting, audio, Voiceprint, and Final-summary IDs.

- Wrong-owner reads return `404` with no owned content.
- Cross-owner feed, stop, abort, rename, rerun, delete, retry, and download have no relevant
  before/after state change.
- Cursor replay under the other Account's Meeting returns `404`.
- Invalid/revoked Sign-in sessions return `401`; stored identifiers cannot reattach.
- No A sentinel appears in B's UI, snapshots, events, prompt log, persistence projection, status,
  or structured logs, and vice versa.
- Same-Account devices continue to share identical history/live state.
- Legacy tokens/routes are rejected or absent. Operator surfaces contain only §7 fields.

The bar is zero leaks and zero unauthorized mutations. One occurrence fails the wave; there is no
statistical tolerance.

### G2 — Authentication, allowlist, and revocation lifecycle

- Mandatory Authlib 1.7.2 prototype rejects bad signature, issuer, audience, expiry, state, nonce,
  and unverified email before authentication code lands.
- Google console saves the exact callback. One real allowed and one real denied external Google
  account traverse the callback. Denied creates no Account/session. Browser trusts production TLS
  without interstitial.
- Exact-email allow/revoke takes effect at CLI return. Re-allow requires fresh sign-in and restores
  only the original `sub` owner.
- Cookie attributes/value boundaries match §4.1. Browser restart and server restart retain a valid
  session/history.
- Sign-out waits for successful Stop, revokes only that browser, and leaves another same-Account
  session working. Stop failure leaves it signed in.
- Account revoke returns only after all its active Meetings are durably `interrupted`; the next
  request from every revoked session is `401`; no later frame or result commits; durable transcript
  and recoverable partial audio remain.
- MOSS session expiry is not tested because it does not exist. Removing/losing the cookie exercises
  the same `401` path.

### G3 — Durable Meetings and Account history

- Live, single-file, multi-file, URL, and serial batch submission each create the ruled Account-
  owned Meetings; one item failure does not alter peers; accepted work continues after browser close.
- Two same-Account clients observe identical active/history order, title rename, transcript, audio
  state, and terminal status. Another Account observes none.
- Every accepted transcript commit survives restart. Crash changes active to `interrupted`, retains
  the last committed transcript and usable audio prefix, exposes history, and never resumes capture.
- Composite SQLite ownership constraints reject cross-Account Meeting/artifact/Voiceprint links.
  Startup accepts only schema v1.
- Reload/close ends capture rather than resuming media; a same-Account observer remains read-only.

### G4 — Four-session capacity and live-quality non-regression

Run four concurrent Live Meetings for 600 seconds, split across at least two Accounts, with real
human speech, real production routes/decoder, 0.5 s ingress cadence, and continuous G1 probes.

- Maximum per-session p95 transcript lag is `<=10.0 s`, linear Type-7.
- Continuously-ready dispatch skew is `<=1`.
- Combined pre-Stop inference real-time factor is `<1`; refinement queue depth is `<=1`.
- vLLM GPU-cache use is `<=0.95`; service/inference process-tree RSS growth is `<=4 GiB` over
  warmed idle; out-of-memory/accelerator errors are zero.
- Sequence gaps, dropped canonical commits, terminal failures, stale/failed windows, and cross-
  Account sentinel delivery are zero.
- Saturating one session yields retryable per-session `429` while a peer progresses; the refused
  frame later succeeds. A short eight-session overload probe must retain isolation, fairness, and
  per-session backpressure; it does not change supported capacity.

Rerun the fixed six-case, two-pass, 12-session production quality corpus. Macro bars inherited from
`evidence/live-g4-recovery-20260825/REPORT.md` are: immediate WER `<=.166655`; settled WER
`<=.140442`; recall `>=.929636`; time-based speaker attribution `>=.876970`; diarization error rate
`<=.161430`; matched-speaker accuracy `>=.911512`; reference-speech diarization error rate
`<=.134804`; and final WER `<=.095074`. Report per-case/category and duration-weighted values.
Historical first-publication/correction/Stop clock values are reported, not promoted into new gates;
the accepted concurrency p95 is the 10.0 s bar above.

### G5 — Audio durability and owner download

- Clean Live and File Stop produce a playable MP3 and metadata matching MP3, 16 kHz, mono, constant
  48 kbit/s; raw lane/mix/WAV material is absent after cleanup.
- Stop reports complete only after transcript and audio are durable in one terminal audio state.
- Forced crash during capture publishes the maximal usable prefix as `partial`, or `unavailable`
  when no prefix exists; transcript remains. Forced encode/storage failure also preserves transcript.
- Owner download returns the correct complete/partial attachment and filename. Other Account gets
  `404`; unauthenticated/revoked gets `401`; removed out-of-band file becomes unavailable without
  search/recreation.
- Account/Meeting paths, `0700` directories, `0600` files, relative database path, byte count,
  duration, and partial flag reconcile with the artifact.

### G6 — Content-free operator control

- Admin socket is host-local, service-owned, mode `0600`; no TCP/browser admin surface exists.
- Human and JSON snapshots contain exactly §7 fields. Two-Account sentinel content and forbidden
  values are absent from status and journal. Storage/logical counts reconcile with authoritative
  metadata.
- Account revoke has G2's all-session/Meeting effect.
- Deliberately pause inference, interrupt its Meeting, then release it: the late result is discarded;
  durable transcript and maximal partial-audio prefix remain; terminal state is `interrupted`.

### G7 — Wave-1 atomic cutover and attended canary

- Block creation; drain active/queued Live/File work to zero; stop Phase 1; create one complete
  quarantined pre-upgrade snapshot; install trusted TLS, empty schema v1, allowlist, and authenticated
  `:7861`; keep `:7860` stopped.
- Before admission, prove allowed/denied Google sign-in, two-Account wrong-owner `404`, authenticated
  Live Stop/download, interrupted partial audio, upload/URL/batch Meetings, reference History,
  service/browser restart persistence, and absence of old routes/tokens.
- Attended Chrome canary exercises real microphone plus meeting-tab shared audio, then entire-screen
  System Audio: both meters independently nonzero, exact frame geometry/no sequence gaps, distinct
  speaker text, clean Stop, and owner MP3 download.
- Any pre-admission failure restores the entire Phase-1 snapshot and old services. Do not partially
  merge, import, or open traffic under mixed authentication.

### G8 — Wave-2 Voiceprint behavior and measured matching

- Standing production-embedder bench reproduces: 441/470 correct known causal probes, 29/470
  abstentions, zero wrong names; 470/470 unknown abstentions; terminal 14/14 correct and 14/14
  unknown abstentions, at cosine `>=0.46`, no margin, `>=1.0 s` evidence.
- Duplicate labels create/select only the addressed opaque Voiceprint. Manual naming at the 2.0 s
  floor stores one sample; below the floor creates one pending intent whose first eligible centroid
  stores exactly one sample. Replace/Stop/abort/crash paths behave as §5.
- Active manual rename rewrites its Meeting Speaker; Bank rename propagates to linked active
  Meetings and all same-Account clients but leaves stopped transcripts unchanged.
- One incompatible Voiceprint is excluded and marked re-enrollment required while compatible entries
  still match.
- Pause an accepted match, delete its Voiceprint, release the result: old-revision result is rejected,
  active links clear, pending work cancels, and historical labels remain.
- Cross-Account list/match/rename/enroll/delete follows G1.

### G9 — Wave-3 Final-summary privacy, lifecycle, and speech non-interference

- Fake OpenAI-compatible endpoint logs exact requests for two Accounts with distinct transcript
  sentinels. Each request contains only its owner Meeting's finalized transcript, browser prompt,
  and request parameters; it contains no other Meeting/history, Account identifier, audio,
  Voiceprint, endpoint secret leakage to MOSS, or server-side prompt copy.
- Exactly one active attempt per Meeting; browser serializes ready Meetings; summary begins only
  after transcript finalization. Delivery retries are byte-identical at 60/120/240 seconds and stop
  after the fourth attempt. Invalid output receives no repair call. Cancel/Retry/state events and
  same-Account artifact reads match §6; wrong owner follows G1.
- Validator accepts/rejects recorded fixtures for the exact five-field shape, nonempty summary, and
  valid timestamps. Automatic title never overwrites an owner title.
- While four Live Meetings pass G4, separate finalized Meetings trigger the maximum allowed browser
  LLM work against a delayed fake endpoint. All G4 bars still pass; no LLM call reaches server ASR
  VRAM/scheduling.

### G10 — Existing suites and Phase-1 behavior

All applicable existing behavior remains green:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests/
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Report exact counts; every collected required test passes. Re-run applicable Phase-1 real mic,
synthetic system lane, failure-path, background-tab, fidelity, Live/File, and contract gates through
the authenticated Account path. Superseded shared-token/view-token reattach behavior is tested absent,
not preserved.

## 10. Explicitly not gated or promised

- Public exposure/open signup; horizontal/multi-process scale; Safari; Windows Chrome parity;
  native capture helpers; the measured-rejected 15/10 lexical candidate.
- Non-Google fallback, Google-side revocation of an existing MOSS session, product-admin content
  access, cross-Account sharing, Account ownership transfer, or legacy compatibility.
- Audio perceptual quality, quota, expiry, eviction, product deletion, backup, storage dashboard,
  file manager, byte ranges, or embedded playback. The operator manages storage/cold bundles.
- Voice populations beyond the measured five speakers/two English recordings, banks over five,
  automatic learning, Voiceprint merge, uploads, standalone enrollment, or compatibility migration.
- Language-model providers/models/endpoints beyond the recorded tuning setup, LAN/cloud bearer
  behavior, blind holdouts, meetings beyond 30 minutes, non-English output, or broader semantic
  quality. Provider availability is not MOSS release readiness.
- A fixed pass threshold for descriptive first-publication, correction, drain, Stop-to-final,
  deployed MP3 conversion time, or perceived audio quality where no operator-approved gate exists.
- Cold-backup cadence/retention and operator storage operations. Restore remains an operator runbook,
  not a product acceptance gate.

## 11. Implementation handoff

Cut tracer-bullet implementation tickets on private `aiSight-us/MOSS-Transcribe-Diarize` only after
this planning commit is on `dev`. Each ticket names its blocking edges, ADRs, charter sections,
production path, focused tests, and which acceptance predicates it advances. Preserve wave order:
Wave 1 must ship and pass before Wave 2; Wave 2 before Wave 3. Do not combine Voiceprint and Final-
summary work into one release.
