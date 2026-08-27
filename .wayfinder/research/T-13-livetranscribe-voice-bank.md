# T-13 — LiveTranscribe voice bank internals (embeddings, names, matching, deletion)

Audited read-only over SSH: `ga0@m4mbp:~/Desktop/AI_Projects/LiveTranscribe`, branch
`ralph/production` @ `6a8d0c1fafe8a1a8d6ea449036dd1ca330309d70` (verified `git rev-parse HEAD`),
dirty worktree. All cited files were checked against `git status`: none of the voice-bank files
below is locally modified. The only dirty frontend files touching this area's neighborhood
(`frontend/src/App.tsx` +43 lines, `frontend/src/api/types.ts` +2 lines) were diffed — the edits
are WhisperKit provisional-readiness UI only, zero voiceprint-related lines; committed content was
read via `git show HEAD:` where relevant. All paths below are repo-relative on the remote.

Terminology trap: `configurationFingerprint` in `Sources/Diarization/IdentityUnification/*` is a
config-hash string, unrelated to voiceprints. The voice bank is "Fingerprint*" in
`Sources/Storage/FingerprintStore.swift`, `Sources/Models/FingerprintModel.swift`,
`Sources/Diarization/VoiceprintTypes.swift`, and the `SpeakerBank` `isFingerprint` entries.

## 1. Embedding production

- Model: WeSpeaker ResNet34 (VoxCeleb) converted to CoreML, run in-process via `MLModel`.
  Config pin at `Sources/Config/Defaults.swift:147-163`:
  - `backend: "pyannote_wespeaker_resnet34"`
  - `dimension: 256`
  - `modelSource: "Wespeaker/wespeaker-voxceleb-resnet34"`
  - `modelFileName: "wespeaker_resnet34"`
  - `modelRevision: "manifest:wespeaker_resnet34.mlmodelc"`
  - `modelHash: "sha256:0904e4978738d12ea78d995e0e0f6de50864876a0845706420d14047a2cf6de9"`
  - `identityNormalizationTolerance: 0.0001`, `device: "cpu"`
- The compatibility family string is computed, not stored raw: `compatibilityModelFamily =
  backend + "|" + modelFileName + "|" + modelSource` (`Sources/Config/ASRConfig.swift:104-110`),
  i.e. `"pyannote_wespeaker_resnet34|wespeaker_resnet34|Wespeaker/wespeaker-voxceleb-resnet34"`.
- Extractor: `Sources/Diarization/EmbeddingExtractor.swift` — `targetSampleRate = 16_000`,
  `targetEmbeddingDimension = 256`, `defaultFrameCount = 998`, `defaultWeightCount = 589`
  (lines 43-49). Inputs are fbank features + pooling weights; output is L2-normalized
  (`Self.l2Normalize`, line 216). Alternate model filenames exist as Tier-E candidates:
  `wespeaker_voxceleb_resnet152_LM_4adba152`, `speechbrain_ecapa_voxceleb_0f99f2d` (lines 46-47),
  selected by backend string (`modelFileName(for:)`, lines 116-131). If the `.mlmodelc` asset is
  missing the extractor enters `.fallback` mode and every `extractEmbedding` returns nil
  (init, lines 71-114; consequence documented in `ProjectResources/Models/manifest.json:10`:
  "SpeakerBank explodes into a fresh SPEAKER_NN per utterance").
- The `modelHash` constant appears ONLY in `Defaults.swift` — it is not re-verified against the
  loaded `.mlmodelc` at runtime (no hash check in `EmbeddingExtractor.tryLoadModel`); per-file
  sha256 verification is delegated to `scripts/bootstrap_runtime_assets.sh --check` per
  `docs/adr/0013-speaker-embedding-upgrade.md`.
- When embeddings are computed:
  - **Live, per VAD-committed utterance**: `LiveDiarizationCoordinator.assignSpeaker`
    (`Sources/Session/Live/LiveDiarizationCoordinator.swift:114-152`) strips ASR carryover
    (`speakerEmbeddingAudio`, lines 431-446) and calls `extractEmbeddingOutcomeGated`
    (line 152 → 528-535). Utterance windows clamped by
    `utteranceEmbeddingMinSeconds: 0.5` / `utteranceEmbeddingMaxSeconds: 10.0`,
    `silenceRMSThreshold: 0.005`, `minEmbeddingDurationSeconds: 1.0`
    (`Defaults.swift:164-183` SpeakerBankConfig).
  - **Enrollment-on-demand from WAV** (POST `/api/fingerprints/enroll`):
    `EmbeddingExtractor.enrollSpeaker` (`Sources/Diarization/EmbeddingEnrollment.swift:10-25`)
    resamples to 16 kHz, requires ≥ 0.5 s (`utteranceEmbeddingMinSeconds`), and if longer than
    10 s picks the loudest 10 s window (`selectEnrollmentAudio`, lines 63-81). WAV decode +
    channel mixdown in `Sources/Server/Routes/RouteSupport.swift:128-196`; error text promises
    "at least 0.5 seconds of voiced audio" (RouteSupport.swift:118-123).
  - **Save-from-session** (POST `/api/fingerprints`): NO new inference — the saved vector is the
    live SpeakerBank centroid for that speaker: `ProductionLiveSessionRouteSupport.speakerEmbedding`
    (`Sources/Server/Routes/ProductionLiveSessionRouteSupport.swift:49-63`) →
    `LiveDiarizationCoordinator.speakerEmbedding` returns `speakerBank.getEntry(id)?.centroid`
    (`LiveDiarizationCoordinator.swift:363-365`). Works only while the live session handle is
    registered (register/unregister at lines 11-24 of the same file).
- No session-end batch embedding pass exists for the bank; file-mode `enrollSpeakers`
  (`EmbeddingEnrollment.swift:27-61`, longest-segment-per-speaker) exists but no production
  caller writes its output into `FingerprintStore` (grep: only save/enroll routes call
  `addSample`/`create`).

## 2. Storage schema

- Location: one JSON file per profile at
  `~/Library/Application Support/LiveTranscribe/fingerprints/<profileID>.json`
  (`Sources/Storage/Database.swift:4-37`, `fingerprintProfilesDirectoryName = "fingerprints"`).
  NOT in SQLite — `Sources/Storage/Migrations.swift` creates no fingerprint table (verified:
  table list is transcript/session/revision/claim/insertion tables only). The GRDB SQLite DB
  (`livetranscribe.sqlite3`, WAL) holds transcript/rename authority state, not voiceprints.
- Store: `actor FingerprintStore` (`Sources/Storage/FingerprintStore.swift:82-318`). Writes are
  pretty-printed, sorted-keys, atomic (lines 260-268).
- Serialized shape (`PersistedFingerprintRecord`, FingerprintStore.swift:320-361):

  ```json
  {
    "profile_id":  "<UUID>",
    "display_name": "Alice",
    "model_family": "pyannote_wespeaker_resnet34|wespeaker_resnet34|Wespeaker/wespeaker-voxceleb-resnet34",
    "embedding_dimension": 256,
    "model_hash": "sha256:0904e497…",
    "sample_count": 1,
    "last_seen":  "ISO8601 UTC w/ fractional seconds",
    "created_at": "ISO8601 UTC w/ fractional seconds",
    "samples": [
      { "sample_id": "<UUID>", "created_at": "ISO8601", "embedding_blob": "<base64 of 256 little-endian float32 = 1024 bytes>" }
    ]
  }
  ```

  Blob codec at lines 383-419 (little-endian `Float.bitPattern`, base64; decode enforces
  byte-count % 4 == 0 and count == `embedding_dimension`). Test-verified raw keys in
  `Tests/UnitTests/StorageTests/FingerprintStoreTests.swift:34-42`.
- What rides beside the vector: display name, model family string, dimension, model hash,
  `created_at`, `last_seen`, and N samples each with own id/timestamp. No per-sample duration,
  source session id, or quality metric is persisted.
- Multi-sample semantics: matching uses the arithmetic mean of all samples
  (`Fingerprint.embedding` → `averageEmbeddings`, `Sources/Diarization/VoiceprintTypes.swift:28-31,
  52-70`); saving under an existing display name (case-insensitive compare) appends a sample to
  that profile instead of creating a new one
  (`Sources/Session/SessionRouteService+LLMSettingsFingerprint.swift:122-136, 155-169`).
  `last_seen` is bumped only by `addSample`/`merge` (FingerprintStore.swift:136, 220) — being
  matched during a session does NOT touch the file.
- Store API beyond CRUD: `merge(source→target)` concatenates samples then deletes source
  (lines 211-225); `deleteSample` refuses to remove the last sample
  (`lastSampleRemoval`, lines 227-242). Neither merge nor deleteSample is exposed as an HTTP
  route (`Sources/Server/Routes/FingerprintRoutes.swift` has no such endpoints).

## 3. Rename flow

Two independent renames exist; neither cascades into the other.

- **Voiceprint profile rename** — `PATCH /api/fingerprints/:profileID` body
  `{"display_name": "..."}` (`FingerprintRoutes.swift:44-52` →
  `SessionRouteService+LLMSettingsFingerprint.swift:198-211` → `FingerprintStore.rename`,
  FingerprintStore.swift:193-198). Mutates only the profile JSON's `display_name` (trimmed,
  non-empty). It does NOT relabel any transcript rows, past or present, and does not touch a
  running session's `displayNamesBySpeakerID` (that map is populated only at diarizer preload,
  `LiveDiarizationCoordinator.swift:81-90`). UI: History panel → "Voiceprints" tab → rename
  dialog (`frontend/src/components/HistoryPanel.tsx:228-234, 301-320`).
- **Session speaker rename** — `PUT /api/sessions/:sessionID/speakers/:speakerID` body
  `SpeakerRenameRequest {display_name, target_segment_keys?}`
  (`Sources/Server/Routes/SpeakerRoutes.swift:21-30`,
  `Sources/Models/SpeakerModel.swift:3-11`). Handler
  `SessionRouteService+TranscriptSpeakerDevice.swift:145-220`:
  - Retroactive: rewrites `display_name` on EVERY transcript segment with
    `segment.speaker == speakerID` (or only segments matching `target_segment_keys` when given;
    renaming `UNKNOWN` REQUIRES target keys — lines 160-166), sets
    `speaker_label_source = .user`, persists the session snapshot. The underlying `speaker` ID
    on rows is never changed — only the display name.
  - Active live sessions route through `LiveSessionCoordinator.renameSpeaker`
    (`Sources/Session/Live/LiveSessionCoordinator.swift:2867-2991`): alias-resolves the ID,
    requires stable live segment IDs, commits a `LiveSegmentRenameAuthorityTransition` to SQLite
    (`Sources/Storage/LiveSegmentRenameAuthorityStore.swift`) bumping `canonicalRevision` and
    per-row `renameEpoch` before mutating actor state — user renames are epoch-protected against
    being overwritten by later machine relabeling.
  - Precedence: fingerprint-derived names merge into the session's `displayNameBySpeakerID` only
    where the current name is not already custom (`mergeDiarizerDisplayNames`,
    `LiveSessionCoordinator.swift:7531-7549`) — a user rename beats the bank name.
- **Rename+save coupling in UI**: the transcript speaker-edit dialog has a "Save voiceprint"
  checkbox (`frontend/src/components/TranscriptPane.tsx:1085-1103`); on commit it first renames,
  then calls `onSaveSpeakerVoiceprint(speakerId, newName)` (lines 486-507) → POST
  `/api/fingerprints` with `{speaker_id, session_id, display_name}` → banks the live centroid
  under that name (`App.tsx@HEAD:1056-1068`). Enabled only during an active live session
  (`canSaveSpeakerVoiceprint = Boolean(activeSessionId) && activeSessionMode === "live"`,
  `App.tsx@HEAD:1863`) and disabled for backend-unidentified rows (TranscriptPane.tsx:581).

## 4. Matching

- Metric: true cosine similarity, vDSP-accelerated, clamped [-1, 1]
  (`Sources/Utilities/CosineDistance.swift:14-39`; wrapper
  `Sources/Diarization/SpeakerBankSupport.swift:661-669`). All embeddings and centroids are
  L2-normalized on entry (`normalizeEmbedding`, SpeakerBankSupport.swift:81-96).
- Bank seeding: at LIVE session start, `EmbeddedSessionRuntime.makeLiveDiarizer` loads ALL
  profiles (`fingerprintStore.list()`) and passes them as `preloadedFingerprints`
  (`Sources/Server/EmbeddedSessionRuntime.swift:1498-1527, 1629-1636`). The coordinator filters
  by `isCompatibleFingerprint` and preloads each averaged profile vector as a `SpeakerEntry`
  with `isFingerprint: true, status: .confirmed`, allocated a normal `SPEAKER_NN` id
  (`LiveDiarizationCoordinator.swift:76-90`; `SpeakerBank.preloadFingerprint`,
  `Sources/Diarization/SpeakerBank.swift:49-80`). Display names map SPEAKER_NN → profile
  display_name in `displayNamesBySpeakerID`.
- Decision order per utterance (`SpeakerBank.assignWithDiagnostics`, SpeakerBank.swift:226-365):
  1. External post-cluster anchor match at `anchorMatchThreshold = 0.68`
     (`Defaults.swift` postCluster; SpeakerBank.swift:235-249).
  2. Short-utterance path if duration < `minEmbeddingDurationSeconds = 1.0`
     (SpeakerBank.swift:251-258).
  3. **Fingerprint-first pass** (SpeakerBank.swift:260-281): best among
     `isFingerprint && status == .confirmed` entries; accept if
     `similarity >= matchThreshold − continuityGrace = 0.55 − 0.04 = 0.51`;
     `decisionReason = "fingerprint_match"`. Fingerprints get a lower (easier) bar than live
     clusters and pre-empt them.
  4. Best overall entry at `matchThreshold = 0.55` (with continuity-bias override;
     `"best_match"` / `"continuity_bias"`).
  5. Continuity grace: `>= 0.51` AND last seen within `continuityRecencySeconds = 6.0`
     (`"continuity_grace"`).
  6. Fallback: create new tentative `SPEAKER_NN` (capped by `maxSpeakersHardCap = 8`) or absorb
     into an existing entry.
  Key constants (`Defaults.swift:164-183` SpeakerBankConfig): `matchThreshold 0.55`,
  `centroidUpdateMinSimilarity 0.60`, `tentativeMaxUtterances 3`, `centroidWarmupCount 3`,
  `centroidRecoveryThreshold 5`, `maxSpeakersHardCap 8`, `continuityRecencySeconds 6.0`,
  `continuityGrace 0.04`, `maxExemplars 4`, `utteranceEmbeddingMinSeconds 0.5`,
  `utteranceEmbeddingMaxSeconds 10.0`, `silenceRMSThreshold 0.005`.
- Scoring nuance: non-fingerprint entries score as `max(centroid, best-of-4-exemplars)`;
  fingerprint entries score on centroid only (`scoreEntryAgainstEmbedding`,
  SpeakerBankSupport.swift:632-644).
- Fingerprint centroids are FROZEN in-session: `touchEntry` updates centroid/warmup/exemplars
  only for `!entry.isFingerprint` (SpeakerBankSupport.swift:582-630) — session audio never
  drifts a banked vector, and nothing writes back to the profile file.
- Abstention/unknown: separate from the bank. The acoustic confidence gate
  (`Sources/Diarization/AcousticConfidenceGate.swift`) yields pending/unattributed
  (reasons `confidence_gate_pending_short|low_margin|mixed|near_threshold_continuity`,
  `confidence_gate_unattributed_no_embedding`; derived thresholds: minDuration 1.0 s,
  minSimilarityMargin = `fastPromotionSimilarityMargin` 0.04, nearThresholdBand 0.04,
  continuityMinSimilarity 0.51). Then `LiveSpeakerVisibilityPolicy`
  (`Sources/Session/Live/LiveSpeakerVisibilityPolicy.swift:30-54`) keeps non-confirmed speakers
  `pending` until ≥ 2 utterances, ≥ 1.5 s speech, ≥ 2 centroid updates
  (`Defaults.swift:268-272`). Placeholder row labels: `SPEAKER_PENDING`,
  `SPEAKER_UNATTRIBUTED`, `UNKNOWN` (`Sources/Transcript/SpeakerLabelVocabulary.swift:24-49`).
  Preloaded fingerprints are born `.confirmed`, so a fingerprint match is visible immediately
  once the acoustic gate accepts.
- When matching runs: on every VAD-committed utterance during live capture, inside
  `assignSpeaker`. There is no batch "match session against bank at end" pass.
- **File mode gets NO bank**: `FileSessionCoordinator` constructs `FileDiarizer` without
  `preloadedFingerprints` (`Sources/Session/File/FileSessionCoordinator.swift:88-104`), as does
  the refined-live OSF provider (`Sources/Session/Live/RefinedLiveOSFProductionViewProvider.swift:64-83`).
  `FileDiarizer` supports preloading (`Sources/Diarization/FileDiarizer.swift:60-92`) but no
  production caller passes profiles. Durable person recognition is live-mode only.

## 5. Within-session vs cross-session boundary

- Within a session: `SpeakerBank` is in-memory, per-session, per-lane. `SPEAKER_NN` ids are
  allocated fresh each session (`allocateSpeakerID`, SpeakerBankSupport.swift:68-71) — the same
  human gets different NN across sessions. Tentative→confirmed lifecycle, alias redirects,
  post-cluster consensus, and identity unification (`SessionIdentityResolver`,
  ADR `docs/adr/0026-session-identity-resolution.md`; "durable pins" =
  user-rename pins on evidence rows WITHIN a session,
  `Sources/Diarization/IdentityUnification/SessionIdentityResolver+DurablePins.swift`) are all
  session-scoped.
- Cross-session: the ONLY durable channel is `FingerprintStore` JSON profiles → preloaded as
  frozen confirmed entries at next live session start → matched at 0.51 → display name attached.
  Persistence into the bank is strictly user-triggered (save checkbox / enroll endpoint);
  sessions never auto-enroll or auto-update profiles. At session end the learned centroids are
  discarded (only diagnostics snapshots record them:
  `LiveDiarizationCoordinator.diagnosticsSnapshot` exports centroid + `is_fingerprint`,
  lines 388-399).
- Transcript rows persist `speaker` (session-local id), `speaker_entity_id`, `display_name`,
  `speaker_label_source` (`acoustic|contextual_rule|contextual_llm|url_metadata|user`)
  (`Sources/Models/TranscriptSegmentModel.swift:9-26`,
  `Sources/Transcript/SpeakerLabelVocabulary.swift:3-22`). Cross-session linkage in stored
  transcripts is therefore by display name only, not by stable person id.

## 6. Embedder-version compatibility

- Every profile is stamped with `model_family` + `embedding_dimension` + `model_hash` at create
  time from the active config (FingerprintStore.swift:88-98, 110-121).
- Load-time validation is strict equality on all three (`validateLoadedRecord`,
  FingerprintStore.swift:286-298). A mismatched profile makes `read`/`list` THROW
  (`invalidPersistedProfile`); because `loadAllRecords` maps with try (lines 244-258), ONE
  incompatible file breaks the entire listing: `GET /api/fingerprints` returns HTTP 400
  `invalid_persisted_profile` (FingerprintRoutes.swift:72-102) and live preload logs a warning
  and proceeds with an empty bank (`EmbeddedSessionRuntime.loadFingerprints` catch,
  lines 1629-1636). Net effect of a model change: the whole voice bank silently stops matching
  and the library UI errors, until profiles are purged.
- `purgeIncompatibleProfiles()` (FingerprintStore.swift:158-180) deletes mismatched files, but
  has NO production caller — only
  `Tests/UnitTests/StorageTests/FingerprintStoreTests.swift:124`. There is no migration,
  re-embedding, or projection path; raw enrollment audio is not retained, so re-enrollment is
  the only recovery. This matches the declared policy in
  `docs/adr/0013-speaker-embedding-upgrade.md` ("Voiceprints must be re-extracted from raw
  enrollment audio... mark stale... require re-enrollment"), of which only the
  stamp-and-reject half is implemented.
- Defense in depth: `SpeakerBank.isCompatibleFingerprint` re-checks dimension/family/hash before
  preload (SpeakerBank.swift:82-86) and `FingerprintStore.validateEmbedding` enforces
  dimension == 256 on every write (lines 277-284).

## 7. Deletion

- Single: `DELETE /api/fingerprints/:profileID` → `FingerprintStore.delete` removes the JSON
  file; 404 `fingerprint_not_found` if absent (FingerprintRoutes.swift:36-42,
  SessionRouteService+LLMSettingsFingerprint.swift:186-196, FingerprintStore.swift:200-209).
- Clear-all: `DELETE /api/fingerprints` iterates delete over all profiles, returns
  `{deleted_count}` (FingerprintRoutes.swift:30-34,
  SessionRouteService+LLMSettingsFingerprint.swift:178-184).
- Per-sample deletion exists in the store (`deleteSample`, guards last sample) but is not routed.
- Blast radius: deletion touches ONLY the profile file. Transcript rows keep their
  `display_name`; a running session keeps its already-preloaded bank entry (preload happens once
  at `makeLiveDiarizer`; no revocation path — `coordinator.preloadFingerprints` has no
  mid-session caller). Next session simply won't preload it.
- UI: History panel → Voiceprints tab → per-profile delete
  (`frontend/src/components/HistoryPanel.tsx:236-256`); clear-all dialog kind
  `clear-voiceprints` wired to `clearFingerprintHistory()` (HistoryPanel.tsx:328).

## 8. HTTP surface (complete)

`Sources/Server/Routes/FingerprintRoutes.swift:5-52`, schemas
`Sources/Models/FingerprintModel.swift:3-44`:

| Route | Body | Response |
|---|---|---|
| GET `/api/fingerprints` | — | `{profiles: [{profile_id, display_name, sample_count, last_seen, created_at}]}` |
| POST `/api/fingerprints` | `{speaker_id, session_id, display_name}` | `{profile_id, display_name, saved}` |
| POST `/api/fingerprints/enroll` | multipart `{display_name, sample: <WAV>}` | `{profile_id, display_name, saved}` |
| DELETE `/api/fingerprints` | — | `{deleted_count}` |
| DELETE `/api/fingerprints/:profileID` | — | `{profile_id, deleted}` |
| PATCH `/api/fingerprints/:profileID` | `{display_name}` | `{profile_id, display_name, updated}` |

Frontend enrollment note: `frontend/src/components/useVoiceprintSample.ts` (4-second mic capture
auto-stop at 4000 ms, or WAV upload) and `rest.ts enrollFingerprint` exist but NO component
imports them at HEAD — the record/upload enrollment UI is currently unwired dead code; the only
live UI path into the bank is the rename-dialog "Save voiceprint" checkbox during a live session.

## Unknown / unmeasured

- No on-disk profile ground truth: `~/Library/Application Support/LiveTranscribe/fingerprints/`
  on m4mbp is EMPTY (only `.`/`..`), so the JSON shape is verified from code + unit tests, not a
  production artifact.
- Runtime accuracy of the 0.51 fingerprint threshold (hit/false-accept rates) — no evidence file
  measured; ADR-0013 records the resnet34 embedding as weakly separable on hard fixtures
  (same-speaker median cosine 0.2733 vs different-speaker 0.1483 on the YouTube fixture),
  suggesting the bank's precision is fixture-dependent and unvalidated.
- Whether `Defaults.modelHash` (`sha256:0904e497…`) equals a hash of the actual shipped
  `.mlmodelc` (it appears nowhere in `ProjectResources/Models/manifest.json`, which lists
  per-file hashes like `8d67064…`); provenance of that constant unverified.
- Behavior when two profiles share a display name case-insensitively already (save appends to
  the FIRST in `list()` order = most-recent `last_seen`; ordering-dependent, untested here).
- Calibration profiles (`Sources/Config/CalibrationProfile.swift` `SpeakerEmbeddingOverrides`)
  can override backend/dimension/hash at runtime; which profile is active on m4mbp's deployment
  was not determined (config snapshot not readable without running the app).
- Multi-lane live capture (mic + system audio): whether each lane gets its own SpeakerBank
  instance with separately-preloaded fingerprints (suggested by per-lane coordinator wiring) was
  not chased to file:line.
- Latency of per-utterance CoreML embedding on-device (diagnostics expose
  `embeddingLatencyP95Milliseconds` but no captured run was read).
- Whether stop-time post-session re-cluster (`applyPostSessionReClusterAtStop`) can reassign a
  row AWAY from a fingerprint-matched speaker after the fact (interaction not traced).
