---
id: T-13
map: map-002-phase2-multiuser
title: LiveTranscribe voice bank internals — embeddings, names, matching, deletion
type: research
status: closed
assignee: charting-research-20260826
blocked_by: []
---

## Question

How does LiveTranscribe actually implement its durable named voice bank? The Phase-2 voice-bank
design (*Voice bank design — ownership, storage, matching, abstention, versioning, deletion*)
must start from what the reference measurably does, not from its UI impression.

Audit read-only over SSH (`ga0@m4mbp:~/Desktop/AI_Projects/LiveTranscribe`, branch
`ralph/production` @ `6a8d0c1`, dirty worktree — `git show HEAD:<path>` where local edits
overlap; never edit/clean/run). Surface, with file:line evidence:

- **Embedding production** — which model produces speaker embeddings, its exact identity/version
  pinning, embedding dimensionality, and when embeddings are computed (live per-segment,
  session-end, on-demand).
- **Storage schema** — where voiceprints persist (files, SQLite, other), the exact
  schema/serialization, and what rides beside the vector (names, timestamps, model id, counts).
- **Rename flow** — how a user edits a speaker name, what the rename mutates, and whether/how it
  relabels earlier transcript rows (retroactive relabel semantics).
- **Matching** — how a new session's speakers are matched against the bank: distance metric,
  thresholds (exact values), abstention/unknown handling, and when matching runs.
- **Within-session vs cross-session** — where the boundary sits between session diarization
  clusters and durable person recognition.
- **Embedder-version compatibility** — what happens to banked vectors if the model changes.
- **Deletion** — whether a voiceprint can be deleted and what that touches.

Record findings in `.wayfinder/research/T-13-livetranscribe-voice-bank.md`: facts with paths,
exact constants, schema shapes, and an explicit "unmeasured/unknown" list.

## Resolution

Resolved 2026-08-26 by a charting-session research subagent (read-only SSH audit of
`ralph/production` @ `6a8d0c1`; dirty remote files verified irrelevant to the bank). Full
findings: [`../research/T-13-livetranscribe-voice-bank.md`](../research/T-13-livetranscribe-voice-bank.md).

Load-bearing facts for *Voice bank design* (T-23) and *Biometric consent* (T-22):

- **Embedder**: WeSpeaker ResNet34-VoxCeleb as CoreML, 16 kHz, 256-dim, L2-normalized; pinned by
  config constants (`Defaults.swift:147-163`, `modelHash sha256:0904e497…`) — hash not
  runtime-verified.
- **Storage = one JSON file per profile** (`~/Library/Application Support/LiveTranscribe/
  fingerprints/<uuid>.json`): display_name, model family/dim/hash, multi-sample base64 float32
  blobs; matching uses the plain mean of samples. No SQLite for the bank.
- **Vector provenance**: "save voiceprint" banks the live session's SpeakerBank centroid (no
  re-inference); a WAV-enroll endpoint exists (≥0.5 s voiced, loudest 10 s window).
- **Matching**: cosine; profiles preload as frozen `confirmed` entries at live start;
  fingerprint-first pass at 0.51 (0.55 match − 0.04 continuity grace) pre-empts session clusters
  (0.55). Profiles never update in-session; sessions never write back. Abstention comes from a
  separate acoustic gate, not the bank.
- **Live-only**: file/refinement lanes build diarizers without fingerprints — durable recognition
  exists only in live capture.
- **Rename = two decoupled flows**: profile PATCH renames the bank only; session-speaker PUT
  retroactively rewrites display_name on transcript rows (epoch-protected rename-authority store)
  without touching the bank. UI couples them via a "Save voiceprint" checkbox.
- **Embedder-version change bricks the bank**: strict equality on family+dim+hash; one
  incompatible profile fails the whole list (HTTP 400, empty preload); purge helper exists but is
  uncalled; no migration path, raw enrollment audio not retained (ADR-0013 mandates re-enroll).
- **Deletion**: per-profile DELETE + clear-all touch only the JSON file — transcripts keep names,
  running sessions keep the preloaded entry.
- **Cross-session identity is name-string-only**; `SPEAKER_NN` ids are session-local.

Unknowns (full list in findings): no on-disk profile specimen existed; 0.51 threshold accuracy
unvalidated (ADR-0013 shows weak resnet34 separability); per-lane bank instancing; whether
stop-time re-cluster can override a fingerprint match.
