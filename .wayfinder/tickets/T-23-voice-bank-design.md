---
id: T-23
map: map-002-phase2-multiuser
title: Voice bank design — ownership, storage, matching, abstention, versioning, deletion
type: grilling
status: closed
assignee: codex
blocked_by: [T-13, T-19, T-22, T-30]
---

## Question

How does the durable named voice bank work in multi-user MOSS: a user edits a speaker name,
the name persists with a voiceprint, and later matching speech automatically displays the saved
name?

**Operator direction (2026-08-26):** use LiveTranscribe's design as the behavioral baseline.
Adopt its choices unless they conflict with the closed Phase-2 account/privacy decisions or with
measured MOSS production-path evidence; do not copy an implementation defect or an unmeasured
numeric constant merely because the reference contains it.

Decide, with the operator, on the evidence of *LiveTranscribe voice bank internals*, the
identity model from *Identity and isolation architecture*, and the ruling from *Biometric
consent and voiceprint privacy boundary*:

- **Server vs client storage** (or a justified hybrid) — operator requirement to decide
  explicitly; the identity model's ownership edges apply either way.
- **Ownership and scope** — per-account bank vs team-shared bank (as T-22's ruling permits);
  cross-device behavior (same account, second browser).
- **Raw material** — build on the Phase-1 session-end album-centroid journal (embedder-stamped,
  session-keyed) vs re-derive; MOSS's two-tier album/centroid architecture (ADR-0002) is the
  substrate — separate within-session diarization from cross-session person recognition
  explicitly.
- **Matching and abstention** — when matching runs (live vs session-end), distance metric and
  threshold source (**measured on the standing bench** `prototypes/streaming-diarization/`,
  per `AGENTS.md` — a threshold chosen without measurement is not decision-complete; spawn a
  `/prototype` ticket if the grilling reaches an unmeasured threshold), and abstention behavior
  (unknown stays `Speaker N`).
- **Rename flow** — where rename happens in the UI, whether it relabels retroactively
  (LiveTranscribe evidence), and how it reaches the client (Phase-1 declared the reference's
  `speaker_renamed` event unreachable — this ticket makes it reachable or replaces it).
- **Embedder-version compatibility** — banked vectors are pinned to the embedder identity
  (T-18's journal stamps it); rule what a version bump does (re-enroll, dual-bank, refuse).
- **Deletion** — the mechanics implementing T-22's deletion ruling.

Resolution records the storage side, ownership scope, matching policy with measured-threshold
provenance, rename semantics, versioning rule, and deletion mechanics — decision-complete for
the AFK builder.

## Resolution

Resolved 2026-08-26 by operator grilling, using LiveTranscribe as the behavioral baseline and
the measured MOSS production-embedder result from *Measured MOSS Voiceprint matching and
abstention rule* wherever the reference's unmeasured constants conflicted.

### Domain and ownership

- A logged-in **Account** owns one server-side private **Voiceprint bank**. A **Voiceprint** is
  an acoustic reference inside that bank; it is not an Account/User profile and never identifies
  the represented person as a MOSS Account. The only Account relationship is ownership of the
  private bank. No cross-Account listing, reading, matching, renaming, enrollment, or deletion
  exists.
- A **Meeting Speaker** is session-local. A successful acoustic match links it to one exact,
  opaque Voiceprint ID and copies that Voiceprint's label onto the Meeting Speaker. Labels are
  owner-private display text, not identity, and are not unique: several Voiceprints in one bank
  may all be labelled `anonymous`. Label equality never creates, selects, merges, or updates a
  Voiceprint.
- The canonical bank lives on the server in the Account's SQLite-owned data. Browsers receive
  only the owner-visible library projection and labels; they never persist vectors. Every signed-
  in browser for the same Account sees the same bank immediately.

### Storage and deep module seam

- T-21's two voice tables are canonically named `voiceprints` and `voiceprint_samples`.
  `voiceprints` carries `account_id`, opaque Voiceprint ID, label, immutable embedder ID,
  embedding dimension, and timestamps. `voiceprint_samples` carries the same Account ownership,
  Voiceprint ID, source Meeting/Speaker provenance, and the L2-normalized float32 vector BLOB.
  One composite uniqueness rule permits at most one sample from a given Meeting Speaker to a
  given Voiceprint; a later manual rename/retry replaces that source sample instead of adding
  weight. `meeting_speakers` may link to the exact Voiceprint ID under the same composite Account
  constraint.
- One deep **Account Speaker Identity module** sits inside the authorized Account workspace. Its
  small interface owns five behaviors: match evidence, manually name a Meeting Speaker, list
  Voiceprints, rename a Voiceprint, and delete a Voiceprint. It hides SQLite, vectors, sample
  aggregation, pending enrollment, bank revisions, label propagation, and match invalidation.
  Routes and live-session callers pass owner-bound Meeting handles and never pass `account_id` or
  touch Voiceprint rows. There is no generic persistence interface or alternate adapter; tests
  exercise this module through a temporary SQLite database.

### Manual naming and enrollment

- The transcript's existing speaker editor is the single naming surface in live and history
  views. A manual rename immediately and retroactively rewrites every transcript row belonging
  to that Meeting Speaker and advances the ordinary Meeting revision. User naming outranks
  automatic labels.
- During active capture, manual naming is also enrollment. If the Meeting Speaker is already
  acoustically linked, the operation changes that exact Voiceprint's label and upserts the one
  sample sourced from this Meeting Speaker. If it is unmatched, the operation creates a new
  Voiceprint regardless of duplicate labels. Text is never used to find an existing Voiceprint.
- Enrollment consumes the current Phase-1 quality-gated fingerprint-album centroid; it never
  re-embeds audio and never reads/imports the Phase-1 journal. The settled `2.0 s` album-enrollment
  floor still governs. If no eligible centroid exists at rename time, the Meeting rename remains
  committed and the live module retains one pending enrollment intent. The first eligible
  centroid completes it automatically exactly once. A later manual rename replaces that intent.
  Stop, abort, or crash before eligibility clears the pending intent without creating a
  zero-sample Voiceprint; the transcript label remains.
- In history, a linked Meeting Speaker may rename its exact Voiceprint label but contributes no
  new sample. An unmatched historical Speaker changes transcript text only: its unnamed vector
  was discarded at session end, and the MVP neither retains it nor re-embeds retained audio.
  Automatic acoustic matches never enroll, refresh, or otherwise learn from speech.

### Matching, abstention, and live visibility

- Apply clamped cosine similarity to every eligible live identity-evidence unit against the
  latest compatible Voiceprints in that Account's bank. Accept the best Voiceprint at
  `similarity >= 0.46`, with no runner-up margin and at least `1.0 s` of eligible speech. Match
  against the L2-normalized arithmetic mean of stored samples. Below either gate, without an
  embedding, or with no compatible Voiceprint, abstain and retain the session-local `Speaker N`.
- Apply the same rule to the Meeting's terminal album centroid; an accepted result may revise
  that Meeting's label. The measurement was 441/470 correct known causal probes, 29 abstentions,
  zero observed wrong names, 470/470 unknown abstentions, and 14/14 terminal correct/unknown
  abstentions across five speakers and two English recordings. Larger banks, other populations,
  and end-to-end terminal cluster-to-Voiceprint integration remain unmeasured.
- Enrollment, Voiceprint rename, and deletion publish a new Account-bank revision visible to
  every active Meeting for that Account. There are no per-session frozen bank copies. A Bank-
  screen rename retroactively relabels linked Speakers in active Meetings; stopped Meeting
  transcripts remain unchanged. All same-Account clients observe these changes through the
  ordinary authenticated snapshot/revision polling path; no separate `speaker_renamed` event is
  introduced.

### Embedder compatibility and deletion

- Every Voiceprint is stamped with an immutable embedder ID and dimension. A mismatch disables
  only that Voiceprint, excludes it from matching, and shows `re-enrollment required` to the
  owner. Compatible entries keep working. There is no conversion, dual-model runtime,
  auto-purge, or compatibility migration; the owner names the voice again under the current
  embedder and may delete the old entry.
- Delete addresses the opaque Voiceprint ID, never its non-unique label. In one Account-bank
  mutation, remove the Voiceprint and all samples, clear its active/persisted links without
  changing stored transcript labels, cancel pending updates targeting it, and advance the bank
  revision. A match result captured from an older revision must be rejected before it can apply
  a label, so after deletion returns no active Meeting can match that Voiceprint. Account deletion
  removes the whole bank. Historical transcript labels remain as recorded.

### MVP UI scope

The Voiceprint Bank screen supports only list, rename, and delete by opaque Voiceprint ID.
Voiceprints enter through active transcript naming. Merge, per-sample controls, standalone
manual creation, WAV upload, and microphone enrollment are outside this MVP.
