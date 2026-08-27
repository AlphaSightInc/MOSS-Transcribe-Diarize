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
