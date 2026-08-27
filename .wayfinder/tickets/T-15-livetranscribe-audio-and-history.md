---
id: T-15
map: map-002-phase2-multiuser
title: LiveTranscribe audio persistence and session history internals
type: research
status: closed
assignee: charting-research-20260826
blocked_by: []
---

## Question

How does LiveTranscribe persist meeting audio and session history? The Phase-2 decision *Audio
retention design* needs the reference's real write path, formats, and lifecycle as evidence, and
MOSS's own retained mixed tape + two capture lanes (ADR-0003) differ structurally from a
single-host recorder.

Audit read-only over SSH (`ga0@m4mbp:~/Desktop/AI_Projects/LiveTranscribe`, branch
`ralph/production` @ `6a8d0c1`, dirty worktree — `git show HEAD:<path>` where local edits
overlap; never edit/clean/run). Surface, with file:line evidence:

- **Audio write path** — when audio hits disk (during capture vs at stop), container/codec
  (WAV/CAF/MP3/AAC…), sample rate/width, mixed vs per-source files, chunking/rotation.
- **Storage layout** — directory structure, naming, what identifies a session's audio, sidecar
  metadata.
- **History model** — what a completed session record contains (title, transcript, summary,
  audio pointer), where it lives, and how the history UI lists/reopens/deletes it.
- **Lifecycle** — retention/quota/cleanup behavior, deletion flow and what it removes, failure
  semantics (partial writes, crash mid-meeting).
- **Download/export** — user-facing export paths and formats.
- **Size reality** — approximate on-disk size per meeting-hour in its chosen format (from real
  files present, if observable read-only).

Record findings in `.wayfinder/research/T-15-livetranscribe-audio-history.md`: facts with paths,
exact formats, an example layout, and an explicit "unmeasured/unknown" list.

## Resolution

Resolved 2026-08-26 by a charting-session research subagent (read-only SSH audit of
`ralph/production` @ `6a8d0c1` + read-only inspection of the real data dir, 68 sessions). Full
findings incl. an example real session layout:
[`../research/T-15-livetranscribe-audio-history.md`](../research/T-15-livetranscribe-audio-history.md).

Load-bearing facts for *Audio retention design* (T-24):

- **Audio recording is ON by default** for every live session
  (`recordFullSessionAudioEnabled` default true) and writes **continuously during capture**
  (serial-queue streaming append; WAV header finalized at close with fsync) — not at Stop.
- **Format: WAV RIFF, PCM s16le, 16 kHz mono = 32,000 B/s → ~115 MB per lane-hour;
  dual-capture ≈ 230 MB/meeting-hour.** No MP3/AAC anywhere; no chunking/rotation; UInt32
  header overflow past ~74.5 h; write failures are counted best-effort, capture continues.
- **Per-source only, never mixed on disk**: fixed names `local.wav` (mic) + `remote.wav`
  (system) under `<sessionDir>/dual_lane_audio/`; the mixed lane is structurally rejected as a
  persistable artifact.
- **History = SQLite authoritative + per-session JSON projection**: `sessions` table (id,
  title, mode, status, audio_path, timestamps, lane) + `transcript_segments` FK CASCADE;
  crash-aware ordering — terminal status commits only after transcript artifacts are durable;
  reads reconcile SQLite-wins with JSON backfill; atomic temp+rename JSON writes.
- **Completed record** = DB row + `transcripts/segments.json`, auto-exported markdown,
  `summary.json`, `formatted_overlay.json`, diagnostics, lane WAV(s); history API has
  list/clear-all/per-session delete.
- Observed store: 84 MB total, 76 MB sessions, 6.66 MB SQLite; observed WAVs sit exactly on
  the 32 kB/s line.

Unknowns (full list in findings): SQLite row contents not queried (WAL DB — avoided as
non-read-only); deployed-binary vs HEAD skew (May–Jul sessions show behaviors HEAD removed);
ring-retention constant; >74.5 h overflow untested.
