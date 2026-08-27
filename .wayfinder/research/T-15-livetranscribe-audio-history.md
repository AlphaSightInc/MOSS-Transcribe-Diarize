# T-15 — LiveTranscribe audio persistence & session history internals

Audited read-only over SSH: `ga0@m4mbp:~/Desktop/AI_Projects/LiveTranscribe`, branch
`ralph/production` @ `6a8d0c1fafe8a1a8d6ea449036dd1ca330309d70` (dirty worktree; all code facts
read from `git show HEAD:` — none of the locally modified files touch the audio/history
subsystem; the local diffs on `frontend/src/App.tsx` / `frontend/src/api/types.ts` are
provisional-ASR readiness gating only). Real data directory inspected read-only at
`~/Library/Application Support/LiveTranscribe/` (68 sessions, May–Jul 2026 vintage — some
observed layouts predate HEAD; version skew is flagged where it matters).

---

## 1. Audio write path

### When audio hits disk: continuously during capture, from session start

- Wiring at live-controller construction (i.e., at `POST /api/sessions/start`):
  `Sources/Server/EmbeddedSessionRuntime.swift:418-423` — if
  `shouldRecordFullSessionStopTimeAudio`, the capture source gets
  `configureDualLaneWAVExport(directoryURL: <sessionDir>/dual_lane_audio)`.
- Gate: `Sources/Server/EmbeddedSessionRuntime.swift:811-815` —
  `config.recordDualLaneAudio || snapshot.live.recordFullSessionAudioEnabled`; and
  `recordFullSessionAudioEnabled` defaults **true** (`Sources/Config/Defaults.swift:356`). So
  full-session audio recording is ON by default for every live session, independent of the
  `record_dual_lane_audio` request flag (`Sources/Models/SessionModel.swift:7`, default false).
- Streaming append: `Sources/Audio/DualLaneWAVExport.swift:93-137` — each capture callback
  enqueues Float32 samples onto a serial utility `DispatchQueue`; samples are converted to
  little-endian Int16 PCM (`pcmData`, lines 190-203) and appended to the open file descriptor
  with a full-write loop (`writeAll`, lines 250-266). Audio is on disk within one queue hop of
  capture — not buffered until stop.
- Header lifecycle: a WAV header with `sampleCount = 0` is written at open
  (`DualLaneWAVExport.swift:88-91`); at `close()` the queue is drained, the header is rewritten
  at offset 0 with the final sample count, then `fsync` + close (lines 139-162). Comment at
  line 117: "Close still drains and finalizes the header for any bytes that did land."

### Container / codec / rate / width

- **Container: WAV (RIFF/WAVE), codec: PCM (`fmt` audioFormat=1), mono (1 channel), 16-bit
  little-endian** — hand-rolled header at `Sources/Audio/DualLaneWAVExport.swift:205-229`
  (`bytesPerSample=2`, `channelCount=1`, `bitsPerSample=16`).
- Sample rate: the capture pipeline's target rate, `AudioConfig.targetSampleRate = 16_000`
  (`Sources/Config/Defaults.swift:17-22`; struct at `Sources/Config/AudioConfig.swift:33-37`).
  So the canonical stream format is **16 kHz mono s16le WAV = 32,000 B/s**.
- Frontend voiceprint samples use the identical format
  (`frontend/src/lib/wavEncode.ts:1-50`, 16 kHz default mono s16 WAV).

### Per-source, never mixed on disk

- Two lane files, fixed names: `local.wav` (microphone) and `remote.wav` (system audio):
  - Dual capture writes both: `Sources/Audio/DualLaneWAVExport.swift:30,34`;
    `Sources/Audio/DualCapture.swift:190` (`append(microphone:systemAudio:)` per callback),
    `DualCapture.swift:398-404`.
  - Mic-only capture writes only `local.wav`: `Sources/Audio/MicrophoneCapture.swift:676-687`.
  - System-audio-only ("speaker" mode) writes only `remote.wav`:
    `Sources/Audio/SystemAudioCapture.swift:1010-1022`.
- The **mixed** lane is explicitly not a persistable audio artifact: `AudioSnapshot.create`
  rejects `.mixed` (`Sources/Session/Live/AudioSnapshot.swift:106-108`), and
  `fullSessionAudioURL(for:)` returns nil for `.mixed`
  (`Sources/Session/Live/LiveSessionCoordinator.swift:5784-5798`).

### Chunking / rotation

- **None.** One monotonically appended WAV per lane per session; no rotation, no size cap on
  the recording itself. Sample counter is `UInt32` with wrapping add
  (`DualLaneWAVExport.swift:77,124`) — header overflows past ~4.29 G samples (~74.5 h at
  16 kHz), data keeps appending.
- Write failures are counted but do not stop capture (`writeFailureCount`, lines 111-128) —
  recording is best-effort; diagnostics surface queue depth / lag / failures
  (`DualLaneWAVExportDiagnostics`, lines 4-13).

### Secondary audio artifacts (same 16 kHz mono s16 WAV format)

- **Retained-ring fallback WAV** `stop_time_file_refinement/<lane>.wav`: at stop, the
  stop-time "file transcript" pass prefers the full-session lane WAV; if it is missing,
  unreadable, empty, shorter than the retained interval, or **longer than the foreground cap
  `foregroundFullSessionMaxSeconds = 240 s`** (`Defaults.swift:357`), it materializes the
  in-memory retained ring to disk instead
  (`LiveSessionCoordinator.swift:5493-5563` selection ladder; ring write at 5750-5782;
  directory at 6349-6356). The ring is RAM-only under HEAD
  (`Sources/Session/Live/LiveRefinementAudioRing.swift:14-62` — chunks in arrays; the
  `directoryURL` param only mkdirs) with retention =
  `finalizationLagSeconds(60) + finalizationIntervalSeconds(60) +
  completenessSlack(5) + vadContext` ≈ 125–130 s (`LiveSessionCoordinator.swift:1103-1116`,
  `Defaults.swift:245-248`), so this fallback WAV is bounded to ~4.2 MB.
- **Drift-corrected copy** `dual_lane_audio/drift_corrected_<lane>.wav` — written only when
  capture-clock drift correction is enabled (default **off**,
  `Defaults.swift:364-369`; writer at `LiveSessionCoordinator.swift:5616-5634`).
- **Leading-silence-trimmed copy** `dual_lane_audio/leading_silence_trimmed_<lane>.wav` —
  only when trim threshold > 0 (default **0 = disabled**, `Defaults.swift:359`; writer at
  `LiveSessionCoordinator.swift:5706-5729`).
- **Background-finalization snapshot** `background_finalization/audio_snapshot/audio.wav` +
  `audio_snapshot.json`: an immutable, hash-verified private copy of one closed lane WAV
  (copy → verify source unchanged → sha256 → chmod 0400 file / 0700 dir / 0600 manifest →
  atomic rename; `Sources/Session/Live/AudioSnapshot.swift:99-197`). Manifest schema 1.0.0
  records byte count, RIFF data-chunk offset/length, rate/channels/bits, frame count,
  duration, sha256, lane, route epoch, covered span (lines 9-53). Gated on
  `backgroundBatchEligibility == .candidateOnly`; default **.disabled**
  (`Defaults.swift:358`; gate at `LiveSessionCoordinator.swift:6884-6897`;
  orchestrator dirs at `Sources/Session/Live/BackgroundFinalizationOrchestrator.swift:36-73`).
- **URL-mode audio is NOT retained**: downloads land in
  `<sessionDir>/<tmp working dir>` (`audio.wav`, `audio.raw.wav`, `audio.normalized.wav`,
  `audio.exact-window.wav` — `Sources/Session/URL/URLAudioDownloaders.swift:96-99,258-261`,
  `URLIngestDurationGovernor.swift:129`) and the whole working directory is deleted in a
  `defer` when processing ends (`Sources/Session/URL/URLSessionCoordinator.swift:119-126`).
  Only `url_ingest.json`, optional `source_info.json` / `page_text.txt` survive
  (`URLSessionCoordinator.swift:417,441,462`). Observed on disk: URL session
  `77bf5b53…` has transcripts + `url_ingest.json` and no audio.
- **File-mode audio is never copied**: `audio_path` in the session record points at the user's
  original input file; export re-serves that path
  (`Sources/Session/SessionRouteService+AudioExport.swift:166-195`).

---

## 2. Storage layout

Root (hardcoded): `~/Library/Application Support/LiveTranscribe/`
(`Sources/Storage/Database.swift:4-17`).

```
LiveTranscribe/
├── livetranscribe.sqlite3(+ -wal, -shm)   # GRDB DatabasePool, WAL mode, FKs on
│                                          #   (Database.swift:7,41-50)
├── user_settings.json                     # LLM/user settings (Database.swift:8)
├── fingerprints/                          # voiceprint profiles dir (Database.swift:9)
└── sessions/<session-id>/                 # one dir per session; id = lowercased UUID
                                           #   (SessionOrchestrator.swift:245; dir join at
                                           #    SessionPersistence.swift:117-135)
    ├── session_meta.json                  # sidecar metadata (SessionPersistence.swift:132)
    ├── audio/                             # created always, UNUSED by any writer at HEAD
    ├── transcripts/
    │   ├── segments.json                  # full segment array (SessionPersistence.swift:133)
    │   └── <yyyymmdd-hhmm-slug>.md        # auto markdown export at every snapshot
    │                                      #   (SessionPersistence.swift:271-280)
    ├── dual_lane_audio/                   # local.wav / remote.wav (+optional drift/trim copies)
    ├── stop_time_file_refinement/         # fallback lane wav + file-mode diagnostics
    ├── refinement_audio/                  # mkdir'd for the ring; empty at HEAD (ring is RAM)
    ├── live_diagnostics.json              # (EmbeddedSessionRuntime.swift:1908-1912)
    ├── activation_metrics.json            # (EmbeddedSessionRuntime.swift:1914-1918)
    ├── refined_live_observability.json    # optional (1920-1928)
    ├── summary.json                       # LLM summary (SessionPersistence.swift:474)
    ├── formatted_overlay.json             # LLM overlay (SessionPersistence.swift:487)
    ├── stop_time_*.json diagnostics
    ├── [speaker_evidence/, boundary_evidence/]        # opt-in only, default off (ADR-0025;
    │                                                  #  Defaults.swift:250-261)
    ├── [provisional_asr_stream.jsonl + _manifest.json] # opt-in, default off, owner-only files
    │                                                  #  (ProvisionalASRStreamWriter.swift:7-8,
    │                                                  #   66-73; Defaults.swift:262-267)
    └── [background_finalization/…]        # opt-in lifecycle + audio_snapshot/, default off
```

What identifies a session's audio: **directory convention, not the DB** — live sessions store
`audio_path: ""` and export resolves `<sessionDir>/dual_lane_audio/{local,remote}.wav` by
probing the filesystem (`SessionRouteService+AudioExport.swift:197-207`). File/URL sessions
store the source path/URL in `audio_path` (URL example observed: meta of `77bf5b53…`).

### Example real session (live, "speaker" capture mode, ~112 s, Jun 7 build)

`sessions/d2c6ff1b-27dd-4178-bf5d-b09b8e6d6c25/` — 17.8 MB total:

```
session_meta.json                                377 B
activation_metrics.json                       28,583 B
live_diagnostics.json                          7,029 B
stop_time_refinement_diagnostics.json         63,093 B
stop_time_file_transcript_diagnostics.json     1,679 B
audio/                                         (empty)
dual_lane_audio/remote.wav                 3,572,424 B   # 111.6 s @ 16 kHz mono s16
refinement_audio/mixed-<startSample>-<idx>.f32 × 3,488 @ 4,096 B ≈ 14.3 MB
                                               # legacy ring spill; removed by commit 6240d8bda
                                               # (2026-06-08); HEAD writes no .f32 files
stop_time_file_refinement/file_diarization_diagnostics.json  225,116 B
stop_time_file_refinement/activation_metrics.json              1,113 B
transcripts/segments.json                      9,052 B
transcripts/20260607-1412-speaker.md           1,315 B
```

`session_meta.json` verbatim:

```json
{
  "audio_path" : "",
  "mode" : "live",
  "selected_refinement_lane" : "remote",
  "selected_refinement_lane_reason" : "capture_mode_speaker",
  "session_id" : "d2c6ff1b-27dd-4178-bf5d-b09b8e6d6c25",
  "started_at" : "2026-06-07T18:12:54.598Z",
  "status" : "completed",
  "title" : "speaker",
  "title_source" : "auto_default",
  "updated_at" : "2026-06-07T18:14:58.220Z"
}
```

Second observed session (`95ddbc7b…`, ~89 s, May 31 build) additionally carries
`stop_time_file_refinement/remote.wav` at 2,836,524 B ≈ the full dual-lane file — that build
always wrote the ring copy; HEAD writes it only on the fallback ladder above.

---

## 3. History model

### Persistence: SQLite authoritative + JSON projection per session

- Table `sessions` (`Sources/Storage/Migrations.swift:37-50`): `session_id` TEXT PK, `title`,
  `mode` (live|file|url), `status`, `audio_path`, `output_dir`, `started_at`, `updated_at`
  (ISO8601 strings), `error?`, plus later `selected_refinement_lane(_reason)?`
  (Migrations.swift:127-137). Record struct: `Sources/Storage/SessionStore.swift:4-18`.
- Transcript rows `transcript_segments` FK→sessions ON DELETE CASCADE with
  start/end/text/speaker_id/speaker_entity_id/display_name/state + refinement/lane/stable-id
  columns (Migrations.swift:57-101,104-185,431-444).
- JSON projection `session_meta.json` (shape at `Sources/Session/SessionPersistence.swift:10-22`;
  fields above plus file-only `title_source`, `enrichment_skipped_reason`).
- Write ordering is crash-aware (`SessionPersistence.swift:160-183, 232-291`): terminal status
  (completed/failed/cancelled) is committed to SQLite only **after** transcript artifacts are
  durable ("Status is the snapshot's commit marker", lines 282-285); non-terminal writes are
  fail-closed. Reads reconcile: SQLite wins, JSON is backfilled when stale
  (lines 189-220).
- All JSON writes are atomic temp-file + rename (`writeDataAtomically`, lines 649-673).

### A completed record contains

DB/meta row (title, mode, status, audio_path, timestamps, lane) + on-disk artifacts:
`transcripts/segments.json` (full `TranscriptSegment` array), auto-exported markdown
transcript, `summary.json`, `formatted_overlay.json`, diagnostics JSONs, and the lane WAV(s).
The "audio pointer" is `audio_path` for file/url modes and directory convention for live.

### History API + UI

- Routes (`Sources/Server/Routes/SessionRoutes.swift:31-49`):
  `GET /api/sessions/history`, `DELETE /api/sessions/history` (clear all),
  `DELETE /api/sessions/history/:sessionID`; handlers in
  `Sources/Session/SessionRouteService+HistoryAndLiveQuery.swift:4-17`.
- Listing (`SessionPersistence.swift:333-384`): from SQLite ordered
  `updated_at DESC, started_at DESC, session_id DESC` (`SessionStore.swift:66-76`),
  **excluding active statuses** (starting/recording/stopping/processing); a no-DB fallback
  scans `sessions/*/session_meta.json`. Response item =
  `SessionHistoryItem {session_id,title,mode,status,audio_path,started_at,updated_at}`
  (`Sources/Models/SessionModel.swift:131-139`).
- Frontend: `frontend/src/api/rest.ts:174-177,654-672` (GET/DELETE);
  `frontend/src/state/history.ts:4-23` (signals + client-side search over
  title/audio_path/status); `frontend/src/components/HistoryPanel.tsx:203-217,291-296,467-474`
  (delete one, clear all, per-item source label). Re-opening a history item loads the
  persisted session via the status/transcript/LLM-state endpoints
  (`GET /api/sessions/:id`, `/transcript`, `/llm/state` —
  `SessionRoutes.swift:78-92`, `TranscriptRoutes.swift:21`); browser `localStorage` holds only
  UI state / last session id / LLM settings (`frontend/src/lib/persistence.ts:16-21`).

---

## 4. Lifecycle

- **Retention/quota: none for the core recording.** No age/size-based cleanup exists for
  session directories, lane WAVs, or the DB; sessions accumulate until the user deletes them.
  The only capped artifacts are the opt-in evidence sidecars
  (speaker evidence 1,800 s / 9,000 rows / 64 MiB; boundary 9,000/9,000/64 MiB; provisional
  ASR stream 1,800 s / 9,000 events / 64 MiB — `Defaults.swift:250-267`,
  `ProvisionalASRStreamCaptureConfig.swift:37-43`, ADR-0025) which mark the packet
  *incomplete* rather than rotating.
- **Deletion** (`SessionPersistence.swift:398-446`): refuses active sessions; cancels+awaits
  any background finalization task for the id; `removeItem` on the entire session directory
  (audio, transcripts, evidence — everything); then deletes transcript rows and the sessions
  row (FK cascade also covers mappings). Returns whether anything existed. "Clear all"
  iterates the same flow (386-395). ADR-0025 relies on exactly this: evidence sidecars die
  with the parent directory.
- **Crash mid-meeting**:
  - Audio: the appended WAV survives with a stale zero-length header (header only finalized in
    `close()`); readers treat unreadable/empty full-session audio as fallback reasons
    (`LiveSessionCoordinator.swift:5500-5519`).
  - Records: on next startup `reconcilePersistedSessions` marks any DB row still in an active
    status as `failed` with the interruption reason and re-persists a snapshot
    (`SessionPersistence.swift:675-715`); server shutdown does the same in-process
    (`SessionOrchestrator.swift:269-302`). Live sessions therefore reappear in history as
    failed, with whatever transcript had been persisted.
  - Background finalization: restart-safe via the hash-verified `AudioSnapshot` + durable
    lifecycle checkpoint; resume validates sha256 before continuing
    (`BackgroundFinalizationOrchestrator.swift:103-140`,
    `AudioSnapshot.swift:200-259`); mismatch fails closed.
- **Partial writes**: every JSON artifact is temp+rename atomic
  (`SessionPersistence.swift:649-673`); snapshot creation cleans up temp+final on error
  (`AudioSnapshot.swift:192-197`); WAV appends are the one deliberately non-atomic stream.

---

## 5. Download / export

- **Transcript** — formats markdown/txt/json/srt/vtt
  (`SessionPersistence.swift:634-647`; `Sources/Transcript/TranscriptExporter.swift`):
  - `GET /api/sessions/:id/transcript/export?format=` → attachment download
    (`Sources/Server/Routes/TranscriptRoutes.swift:58-73`);
  - `POST …/transcript/export-to-folder` → server-side write into a user-picked folder
    (`TranscriptRoutes.swift:75-83`); every snapshot also auto-writes the `.md` into
    `transcripts/` (`SessionPersistence.swift:271-280`). Export filename stem =
    `yyyymmdd-hhmm-<title-slug>` (`SessionPersistence.swift:546-557`).
- **Audio** (`Sources/Session/SessionRouteService+AudioExport.swift`):
  - `GET /api/sessions/:id/audio/download[?lane=local|remote]` → streams the file with
    `attachment` disposition (`TranscriptRoutes.swift:95-119`);
  - `POST …/audio/export-to-folder` → copies the default source into a folder (lines 65-114).
  - Source resolution (lines 154-226): file/url `audio_path` if it is a local file (URL-mode
    http(s) paths are rejected — "No local source audio file"); otherwise probe
    `dual_lane_audio/{local,remote}.wav`, **filtering out lanes whose audio is silent across
    every transcript span** (RMS probe, lines 234-316); default lane preference: local, else
    first (line 116-118). Multi-lane downloads get `-local`/`-remote` filename suffixes
    (lines 128-134). Content types: wav→audio/wav, mp3→audio/mpeg, m4a/mp4→audio/mp4
    (lines 136-145). No transcoding anywhere — the WAV is served as recorded; export requires
    a non-empty transcript (lines 159-164).
- Frontend calls: `frontend/src/App.tsx:830` (transcript export URL), `App.tsx:850`
  (`/audio/download`), `rest.ts:565,583` (export-to-folder posts).

---

## 6. Size reality (observed read-only on m4mbp)

- Store totals: `LiveTranscribe/` = **84 MB**; `sessions/` = **76 MB** across **68 sessions**;
  `livetranscribe.sqlite3` = 6.66 MB (+0.49 MB WAL). `fingerprints/` empty.
- Lane WAV arithmetic (format-derived, confirmed by files): 16 kHz × 2 B mono =
  **32,000 B/s → 115.2 MB per lane-hour** (~110 MiB).
  Observed `remote.wav` files: 3,572,424 B / 111.6 s; 2,836,664 B / 88.6 s; 2,551,064 B;
  2,381,404 B; 1,996,184 B — all exactly on the 32 kB/s line.
- **Per meeting-hour at HEAD defaults**: speaker-only session ≈ **115 MB**; dual-capture
  (mic + system) ≈ **230 MB**; + bounded extras (retained-ring fallback WAV ≤ ~4.2 MB;
  JSON transcript/diagnostics ≈ 0.1–0.5 MB/h; drift/trim copies and background snapshot off
  by default — snapshot would add another full lane copy ≈ +115 MB/h when enabled).
- Observed sessions are short (≤2 min); the five biggest (10–17.8 MB) are dominated by the
  legacy `.f32` ring spill (≈14.3 MB in `d2c6ff1b`) that HEAD no longer writes
  (no `.f32` writer in HEAD sources; removed in `6240d8bda`, 2026-06-08).

---

## 7. MOSS-relevant contrasts (for the Audio retention design decision)

- LiveTranscribe retains **per-lane** WAVs and refuses to persist a mixed lane
  (`AudioSnapshot.swift:106-108`); MOSS ADR-0003's retained **mixed tape** is the opposite
  default — LiveTranscribe's mixed audio exists only in the RAM ring for stop-time use.
- Recording is default-on, uncompressed, unbounded, deletion-only lifecycle — a deliberate
  simplicity: 115 MB/lane-hour, no rotation, no quota, atomic-JSON + SQLite-commit-marker
  around a deliberately non-atomic audio stream.
- Restart-safe processing over retained audio is done by **copy + sha256 manifest**
  (`AudioSnapshot`), not by locking the live file.

---

## Unknown / unmeasured

- No long (≥1 h) real session existed on disk; the 115.2 MB/lane-hour figure is
  format-derived and verified only against ≤2-minute recordings.
- No session with `local.wav` (mic lane) was present — every observed session used
  "speaker" capture mode; dual-capture on-disk shape is inferred from code
  (`DualCapture.swift:190`).
- No `background_finalization/`, `speaker_evidence/`, `boundary_evidence/`, or
  `provisional_asr_stream.jsonl` existed on disk (all default-off); their layouts are from
  code/ADR only.
- No drift-corrected or leading-silence-trimmed WAV observed (both default-off).
- `livetranscribe.sqlite3` contents not queried (would require sqlite3 open — avoided as
  arguably non-read-only on a WAL DB); row counts inferred from file size only.
- The deployed app binary's exact build vs HEAD is unknown; on-disk sessions show behaviors
  of May–Jul builds (`.f32` spill, always-written ring copy) that HEAD has since changed.
- Exact `finalizationVadContextSeconds` contribution to ring retention not resolved
  (function of VAD config; ring ≈ 125–130 s total).
- UInt32 sample-counter overflow behavior (>74.5 h) untested anywhere in the repo.
