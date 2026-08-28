# ADR-0010: Retain one owner-private mixed MP3 per Meeting

- **Status:** Accepted
- **Date:** 2026-08-27
- **Scope:** Phase-2 Meeting audio

## Context

Users need post-Stop playback and download, but raw lane audio is large and is working material for
transcription rather than a durable product artifact.

## Decision

Each finished Meeting retains one Account-owned mixed MP3: MPEG Audio Layer III, 16 kHz, mono,
constant 48 kbit/s. Microphone, system-lane, raw mixed PCM, and WAV do not survive normal terminal
cleanup. The artifact is download/playback material only and is never input to later ASR,
diarization, Voiceprint, or language-model work.

The Meeting audio archive module owns staging, synchronous Stop conversion, atomic publication,
metadata, recovery, and authorized download. Complete and partial files live under the Account and
Meeting directories with `0700` directories and `0600` files. Clean Stop reaches `available`,
`partial`, or `unavailable` before completion returns. Crash recovery publishes the maximal usable
prefix as partial; audio failure never fails or deletes the transcript.

## Consequences

- History offers complete download, partial download, or unavailable; there is no embedded player.
- Wrong-owner download resolves `404` through the Account workspace.
- MOSS implements no quota, expiry, eviction, deletion, backup, storage dashboard, or file manager.
- The production-semantics probe in
  `prototypes/streaming-diarization/audio-retention-format/publication_probe.py` accepts
  one default-stream 16 kHz mono PCM WAV as the sole input to inference and `libmp3lame -b:a 48k`,
  then publishes through a same-directory staging file followed by fsync and atomic replacement.
  In a 151-second two-stream falsifier, the source's first/default streams measured 440/880 Hz;
  the canonical mix, long-window inference input, and retained MP3 all measured 880 Hz.
  FFprobe measured MPEG Layer III, 16 kHz, mono, 48,000 bit/s at stream and every packet; metadata
  duration/bytes matched the artifact, directories were `0700`, and the MP3 was `0600`. Each newly
  created root, Account, and Meeting entry is fsynced through its parent in creation order; final
  replacement is fsynced through Meeting before metadata. One production discard operation owns
  unlink, verified absence, and parent fsync for publication, metadata, and download reconciliation.
  Only its success permits durable unavailable. If the known-valid MP3 survives, retry that exact
  available metadata once; success is available, and another failure propagates without audio
  metadata. Size mismatch follows the same discard rule. Durable unavailable never coexists with a
  surviving MP3; authority loss fences all reconciliation.
