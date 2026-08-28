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

Live capture tees only the exact runtime-accepted 16 kHz mono PCM16 mix into one fixed,
owner-derived stage. Every accepted append is fsynced and the existing `max_tape_bytes` bound is
the stage bound. Hitting the bound or a write failure never ends transcription, but permanently
makes complete audio ineligible: a positive prefix becomes partial and zero complete samples become
unavailable. Normal Stop settles MP3 metadata, verifies raw-stage cleanup, atomically commits the
final transcript and terminal Meeting status when the document changed (or finishes status-only
when it did not), and only then updates the public projection. One per-binding settlement lock is
shared by publication, fencing, shutdown, and in-service recovery. Startup never resumes capture;
it enumerates canonical active rows and recovers fixed owner paths without filesystem search. If
interruption follows verified complete publication but precedes terminal Meeting truth, one guarded
state-only mutation retains the identical canonical path, bytes, duration, and format as `partial`;
it does not rename or re-encode the MP3.

## Consequences

- History offers complete download, partial download, or explicit `Audio unavailable`; there is no
  embedded player.
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
  surviving MP3. If existence itself cannot be observed, discard raises typed cleanup uncertainty,
  the download surface returns a controlled failure, and metadata does not change. Authority loss
  fences all reconciliation.
- `live_recovery_probe.py` measured 1,920,000 staged bytes byte-exact across 120 fsynced appends;
  median/p95/max append latency was 0.048/0.080/0.117 ms versus the existing 500 ms cadence. A
  16,001-byte torn stage recovered 16,000 bytes; one sample produced a playable partial MP3; zero
  produced unavailable; a refused stage creation produced no raw path and did not stop capture.
  Fresh production Store/archive objects recovered process loss after Meeting-row creation,
  transcript, MP3 publication, metadata, stage cleanup, and Meeting finish. The pre-stage boundary
  had no directory and became interrupted/unavailable; every later active boundary retained the
  transcript, reconciled file/metadata truth, removed raw PCM, and ended interrupted. A fully
  finished boundary remained completed. A transient terminal cleanup failure retries that same
  owner-bound recovery operation and ends the authorized Meeting durably terminal only after raw
  absence is verified. A held concurrent fence measured one MP3 publication, one resolvable
  artifact, and no duplicate terminal mutation. Persistent cleanup uncertainty leaves the canonical Meeting active for
  visible startup recovery; it cannot make terminal status eligible while raw PCM survives.
  After authority is already lost, recovery cannot invent audio metadata. Its fixed-stage cleanup
  is binding-owned and cancellation-shielded with one causal retry. The historical authority-first
  failure path remains covered: if both attempts fail after SQLite has already interrupted the
  Meeting, startup reconciles canonical interrupted Live rows and fixed owner paths without
  filesystem search, even if the Account has since been re-allowed. Metadata-backed MP3 is
  resolved through the same archive truth seam: verified absence permits a guarded unavailable
  update, while cleanup uncertainty preserves metadata and blocks startup visibly. Unrecorded MP3
  is removed. A failed Live creation likewise reaches durable `failed` only after the fixed stage
  is verified absent; uncertainty leaves its canonical active row for startup recovery rather than
  making raw PCM unreachable. MP3 pre-publication uses one deterministic `.audio.staged.mp3` path;
  Live and File startup recovery remove it through canonical owner paths before preserving verified
  metadata or recording unavailable. Only normal completed settlement may retain complete audio;
  failed/interrupted/crash outcomes are partial or unavailable. The probe rejected interrupted
  `available`: active and already-interrupted recovery now downgrade a verified artifact to
  metadata-identical `partial` before terminal settlement, while uncertainty still blocks rather
  than changing truth. If Account revocation lands after MP3 replacement but before metadata, the
  binding remembers that the fixed unrecorded MP3 and raw stage both require cleanup. A transient
  refusal removed both on attempt two; persistent refusal remained explicitly unsettled across
  shutdown retry instead of declaring terminal settlement over an orphan. Revocation can also win
  after available metadata and raw cleanup but before the atomic transcript/status commit. Every
  revoked terminal exit therefore applies the same guarded state-only reconciliation before public
  terminal truth: the measured boundary ended interrupted/partial with identical `audio.mp3` bytes
  and metadata. Account lifecycle revocation now prevents that ordering in the product: it fences
publication, settles bindings and residual owner/mode rows while their captured generation remains
valid, applies any state-only `available → partial` transition, and only then disables Account
authority in a zero-active-row transaction. Persistent cleanup uncertainty leaves the row active
and the Account durably enabled for startup retry rather than making raw or MP3 truth unreachable.
The publication fence never cancels an accepted mutation or thread-backed operation. It blocks new
admission, skips still-queued work, sends a cooperative exit, and joins the worker. Thus an admitted
SQLite commit synchronizes binding truth and an admitted terminal audio publication produces its one
result before interruption or Account return. The accepted revoke itself is lifecycle-owned and
shielded from the Unix handler; product lifespan joins it before Live/File shutdown and Store close.
A measured handler-cancellation boundary produced one MP3, removed the raw stage, completed the
Meeting, and only then disabled authority—never a second recovery publish.
- A Stop request and a queued transcript persistence failure can become runnable together. Python
  3.10 measured the failure first while raw capture was still active; Python 3.12 measured raw Stop
  first. The shared transport therefore opens one adapter-owned Stop intent at endpoint entry and
  the Phase-2 publication fence waits for that raw outcome. Accepted Stop consistently returns only
  after interrupted/partial durability and raw cleanup; a genuine raw Stop failure remains a
  conflict. The latch exists only in flight: concurrent callers share it, while a later sequential
  Stop or a retry after timeout reaches the runtime's existing semantics. Route entry grants no
  authority or mutation. Each entrant owns one release claim, not the shared attempt: a rejected
  anonymous/foreign request cannot clear a joined owner, all rejected claims clear an unstarted
  attempt, and after an authorized start only the raw runtime outcome clears attempt identity.
  When a joined request observes v2 already `closed`, it continues through that same raw Stop
  intent instead of returning a premature v2 conflict; failed and aborted v2 states remain
  conflicts, and a later sequential Stop still receives the existing terminal conflict.
- Operator interruption reuses the same serialized terminal owners. The synchronous Live claim
  rejects capture/publication before its first await; raw abort makes queued and later inference
  unpublishable. The runtime-owned per-session arbiter discard removes queued canonical,
  refinement, and provisional items plus their timing/readiness accounting before abort yields;
  an already-running provider is not cancelled and its result is rejected by terminal authority.
  The measured target depth was `3 -> 0`, aggregate depth `4 -> 1`, and the peer then completed.
  The File claim cancels and joins only its selected task, waits for synchronous
  input use to end, and removes that working source while peer Meetings continue. Both paths reuse
  canonical artifact reconciliation: a verified complete MP3 keeps identical path, bytes, duration,
  and encoding metadata while state becomes `partial`; verified absence becomes `unavailable`;
  cleanup uncertainty fails the command with the Meeting nonterminal. The production-backed
  `phase2-operator-interrupt` probe and focused tests measured held inference, held SQLite commit,
  held File execution, handler cancellation, idempotency, and unchanged peer work.
