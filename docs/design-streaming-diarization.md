# Streaming Diarization Design — "Listen once, remember voices, tidy as you go"

Charted 2026-07-28 (product owner + Claude wayfinder/grilling session; Codex audit as
peer input). Decision record: `docs/adr/0002-two-tier-diarization-fingerprint-album.md`.
Session artifact (superseded by this doc): `AAgent/260728-moss-streaming-architecture-map.md`.

## 1. Goal

Live transcription+diarization over LAN where a 3-hour interview costs constant compute
per new audio bite, speaker labels converge to batch quality as the meeting progresses,
and **live speaker accuracy is ≥90-95%** — the explicit bar a sibling project missed
(<80%, live diverging from file mode because historical assignments were never
retrospectively updated).

## 2. Verified constraints (do not re-litigate)

- **150 s per MOSS request is hard**: `MOSS_MAX_MODEL_LEN=16384`, audio ≈25 tokens/s,
  12,000 tokens reserved for output (`ops/moss.env`). 3 h ≈ 270K audio tokens — no
  configuration fits hours into one request. System-level workaround already exists:
  150 s windows / 120 s stride (`app/windowed_transcription.py` `plan_windows`).
- **Windows carry no context**: each request contains only its own audio; stitching is
  post-hoc (`_stitch_segments` + Tier-A overlap). Whole-meeting speaker consistency is
  therefore *always* an external identity layer — reprocessing from inception buys no
  in-model context.
- **Live identity today overwrites**: `_reconcile_committed_vectors` stores the latest
  span vector per speaker (`app/live_provider_bundle.py`); the optional
  `canonical_embedding` history hook exists and is unused in production — it is the
  designated injection point.
- **PCM is pruned** after span commit (60 s `max_retained_samples` cap,
  `app/live_session.py`) — nothing retrospective is possible until assembly exists.
- Server throughput ≈35-40x real time (RTX 4070 Ti, product-owner measurement).
- Live transport (0.5 s JSON POSTs, acks, 15 s outbox) is settled — ADR-0001.

## 3. Architecture

Five components; 1 and 3 already exist.

1. **Mac client (unchanged)** — 0.5 s sequenced, acknowledged packets per lane.
2. **Tape recorder (new)** — server appends every acknowledged frame to durable
   per-session logs: mic lane + system lane + mixed track (~0.3 GB/hr total). Dropped
   frames become silence with a gap manifest so wall-clock offsets stay true. Raw PCM +
   JSON index; WAV rendered on demand. Tee point: the mixer's sealed-interval commit.
   Doubles as crash/resume checkpoint (with album + committed transcript).
3. **Fast lane (mostly unchanged)** — VAD spans ≤2.5 s → MOSS → provisional labels in
   seconds. Only change: reference vectors come from the album.
4. **Fingerprint album (new, core)** — per speaker: top-k exemplar embeddings
   (WeSpeaker resnet152-LM, 256-dim, the pinned Tier-B asset), admitted only for ≥2 s
   clean speech with sufficient margin; matching against duration-weighted centroid;
   identity provisional until ~5-10 s accumulated. Lane provenance (mic vs system) is
   a strong local/remote prior. The album is the **compressed context handed forward**
   — a few MB replacing hours of audio; hour-2 processing never re-hears hour 1.
5. **Clean-up sweep (new)** — every few minutes + on uncertainty events (births,
   abstain streaks, low margins) + at session end: re-VAD/re-embed/re-cluster the tape
   (constrained, seeded by live labels), rewrite historical assignments, bump
   transcript revision. **Never re-runs ASR.** Live spans always preempt GPU; sweeps
   are CPU-capable (ONNX).

Corrections policy: silent self-correction; server keeps a revision log; the saved
final transcript is the fully swept one. Batch mode replaces disabled Tier-B with the
same album engine (one identity engine, two entry points).

## 4. Why live→file convergence holds here (the sibling project's failure)

The sibling project's live accuracy diverged from file mode because (a) identity used
only embeddings available at time T and (b) historical assignments were immutable.
This design attacks both: the album accumulates best-evidence voiceprints (T-growing
quality), and sweeps rewrite history against the current album. Convergence is not
assumed — it is prototype gate B.

## 5. Implementation order (after prototype gates pass)

1. Album in the live path (kills the overwrite bug; hook exists; recalibrate
   `min_match_score` / `min_margin`).
2. Tape recorder (assembly + gap manifest + retention TTL).
3. Sweep + versioned silent corrections.
4. Batch Tier-B → album unification.

Execution vehicle: Ralph PRD (`scripts/ralph-afk`), coordinated with the active loop.

## 6. Prototype gates (feasibility before development)

All three run before production implementation; results recorded in §7.

- **A — Album vs overwrite (live accuracy).** Causal simulation on labeled
  multi-speaker audio using the production WeSpeaker embedder: current overwrite
  policy vs quality-gated album. Metric: cumulative live speaker accuracy.
  **Gate: album ≥90-95% and materially above overwrite.** Sweep admission thresholds,
  k, weighting.
- **B — Convergence.** Live-causal album at time T vs whole-file clustering oracle,
  with and without periodic retrospective sweeps. Metric: accuracy gap over meeting
  time; sweep wall-clock cost. **Gate: gap trends to ~0 with sweeps (divergence =
  redesign); sweep cost fits the 35-40x headroom.**
- **C — Assembly correctness.** Replay out-of-order/dropped/duplicated 0.5 s frames
  (outbox retry semantics) into the appender. **Gate: byte-exact reconstruction,
  stable offsets under gaps, checkpoint/resume mid-session.**

Test material: synthetic meetings composed from public per-speaker speech (exact
ground-truth turns; controllable speaker count, turn length, pauses, overlap, noise)
plus at least one real conversational recording for realism. Live mode is the priority
scenario (2.5 s span granularity, 0.5 s minimum evidence).

## 7. Prototype evidence

(To be filled by prototypes A/B/C.)

## 8. Open questions (fog)

- Sweep cadence + album parameters — calibrate on prototype data, then real recordings.
- Cross-meeting persistent album (recognize returning interviewer) — product+privacy.
- Boundary re-ASR for words cut at 2.5 s seams (text quality; orthogonal).
- Enrollment-prefix lineup inside MOSS as hard-case verifier.
- Speaker cap (16) and span cap (2.5 s) tuning once identity is stable.
- Retention TTL / privacy posture for stored session audio.
