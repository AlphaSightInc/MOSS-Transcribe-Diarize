---
id: T-24
map: map-002-phase2-multiuser
title: Audio retention design — formats, lanes, ownership, lifecycle, download
type: grilling
status: closed
assignee: codex-20260826
blocked_by: [T-15, T-19]
---

## Question

How is meeting audio saved after Stop, and how does a user get it back?

Decide, with the operator, on the evidence of *LiveTranscribe audio persistence and session
history internals*, MOSS's own retention state from *MOSS multi-user-relevant current state*
(ADR-0003 mixed tape + two capture lanes), and ownership from *Identity and isolation
architecture*:

- **Canonical archival form first** — mixed mono tape, the two source lanes, or both; the
  operator requirement is explicit that mixed-vs-separate is decided, and the canonical form is
  chosen **before** transcoding convenience copies.
- **Format** — WAV, MP3, or both (operator requirement names exactly this choice); codec/
  bitrate if lossy; measured size per meeting-hour for each candidate (16 kHz mono arithmetic
  is not a measurement of the lossy options — take LiveTranscribe's real sizes as evidence,
  measure MOSS's own if needed via a small `/prototype`).
- **Storage owner and location** — server disk layout, DB metadata row (per *Persistence
  decision*'s file-vs-relational rule), account ownership column.
- **Retention default** — ADR-0003's deliberate raw-audio-OFF posture vs this requirement's
  save-after-Stop: is retention per-meeting opt-in, account default ON, or always ON? Interacts
  with T-22's consent ruling for counterpart voices in the recording.
- **Download and history** — how the UI lists a finished meeting's audio and serves it
  (authenticated download route, range requests or not, filename convention).
- **Lifecycle** — quota per account or global, expiry, deletion (user-initiated and
  quota-forced), and failure semantics (disk full mid-meeting must not kill the transcript;
  partial tape on crash).

Resolution records the canonical form, format(s) with measured sizes, layout, retention
default, download contract, and lifecycle rules — decision-complete for the AFK builder.

## Resolution

Resolved 2026-08-26 by operator grilling, a real-speech format/timing prototype, and read-only
verification of the deployed host.

### Canonical artifact and purpose

- A finished Meeting retains **one mixed mono recording only**: the exact mix used by the live
  transcription path. The microphone and system lanes are working material, not Meeting
  artifacts; they do not survive terminal audio finalization.
- Retained audio exists only for **human download and playback**. It is not a lossless audit
  master and no later ASR, diarization, voice-profile, or LLM job may treat it as model input.
- Existing raw lane/mixed tape may remain transient while capture and terminal transcript
  finalization need it. No raw PCM or WAV survives normal terminal cleanup.

### Format and measured cost

- The sole retained format is **MP3 (MPEG Audio Layer III), 16 kHz, mono, constant 48 kbit/s**.
  MOSS stores neither WAV nor a second convenience copy.
- The eight-case real-speech prototype measured **21,610,044 bytes per meeting-hour
  (21.6 decimal MB/hour)**. Two complete local timing runs measured 48-kbit/s medians of
  **5.78** and **6.48 seconds per audio-hour**, with all observations between **5.50 and
  6.99 s/hour**. This makes conversion marginal on the measured MacStudio without pretending
  host load is constant. Conversion time on the deployed Windows/WSL host is explicitly
  **unmeasured** because that host's controlling charter is read-only.
- Perceived quality was not measured. The operator delegated the bitrate judgment after ruling
  that the archive is playback-only; 48 kbit/s avoids the most aggressive measured option while
  using 25% less storage than 64 kbit/s.
- Reusable command and full verdict:
  [audio-retention format prototype](../../prototypes/streaming-diarization/audio-retention-format/NOTES.md).

### Ownership, storage, and metadata

- Audio is a Meeting artifact and inherits its single Account owner. The authenticated Account
  workspace opens the Meeting first; no route accepts a caller-supplied owner or performs a
  global Meeting lookup. A cross-owner identifier returns `404`.
- Read-only live verification found the deployed app running as a WSL2 Ubuntu user service
  (`moss-live-web.service`, Linux Python). The deployment therefore uses an ext4 root outside
  the checkout and batch-runs filesystem:
  `/home/devcontainers/.local/share/moss-transcribe-diarize/meetings/`.
- Complete path:
  `<root>/<account_id>/<meeting_id>/audio.mp3`. Partial path:
  `<root>/<account_id>/<meeting_id>/audio.partial.mp3`. Directories are `0700`; files are `0600`.
  The configured root stays out of database rows; rows store root-relative paths.
- One relational `meeting_audio` row is keyed and foreign-keyed by composite
  `(account_id, meeting_id)`. It records `state` (`available`, `partial`, or `unavailable`),
  `relative_path`, `mime_type`, `sample_rate_hz`, `channels`, `bit_rate_bps`, `byte_count`,
  `duration_ms`, `is_partial`, nullable `failure_code`, and `created_at`. It duplicates neither
  Meeting title nor ownership from client input.
- One deep **Meeting audio archive module** owns raw staging, final conversion, metadata commit,
  crash recovery, availability description, and download opening. Callers and tests use its
  Meeting-authorized interface; filesystem and database mechanics remain internal.

### Capture, Stop, and failure lifecycle

- Retention is **always ON**. There is no account setting, per-Meeting toggle, or consent prompt.
- Stop seals the working mixed tape, lets terminal transcript finalization finish with that raw
  input, then synchronously encodes MP3. Stop does not return the Meeting as complete until audio
  has one stable state: `available`, `partial`, or `unavailable`.
- Encoding writes a temporary sibling file, flushes it, atomically publishes the final name,
  commits metadata, then removes all raw lane/mixed working material. A publish failure never
  replaces an already complete artifact.
- On a crash or tape degradation, recovery encodes the maximal recoverable mixed prefix as a
  partial MP3 and labels it `partial`; it is never presented as complete. If no usable prefix can
  be published, audio becomes `unavailable`.
- Storage pressure, tape write failure, or MP3 failure **never fails or deletes the transcript**.
  Capture and transcript finalization continue as far as their own inputs allow. Audio failure is
  represented only by its audio state and `failure_code`; raw working files are not promoted as a
  fallback archive.

### History and download

- Finished-Meeting history shows exactly one of: **Download audio**, **Download partial audio**,
  or **Audio unavailable**. There is no embedded player.
- `GET /api/meetings/{meeting_id}/audio/download` is same-origin and Sign-in-session
  authenticated. It serves the whole MP3 with `Content-Disposition: attachment`; the MVP does
  **not** implement byte ranges, seeking, or resume.
- Download filename is
  `YYYY-MM-DD_<title-slug>_<first-8-meeting-id>.mp3`, using the Meeting's UTC start date and
  current title. Partial audio inserts `_partial` before `.mp3`.
- If the deployment operator removed the file out of band, the module reports audio unavailable;
  it neither searches for nor recreates the artifact.

### Explicit lifecycle scope

- MOSS implements **no audio quota, expiry, eviction, user deletion, storage dashboard, backup,
  or file-management UI**. The earlier discussed 500 GiB pool is superseded and is not a product
  rule.
- The cooperating deployment operator manages ext4 capacity and files outside MOSS. This is an
  operational responsibility, not an Account content-management capability.
