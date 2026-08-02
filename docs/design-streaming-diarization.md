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

Run 2026-07-28/29, `prototypes/streaming-diarization/` (throwaway, git-excluded;
verdict details in its `NOTES.md`). Production `_OnnxWeSpeakerEmbedder` +
`WeSpeakerResNet152LmAdapter` with the pinned ONNX (sha verified); production live
semantics (2.5 s span cap incl. mid-utterance cuts, 0.6 s silence split, per-interval
0.5 s evidence floor, one-to-one score/margin matching, abstain, birth, 16-speaker
cap). Data: 8 synthetic meetings from LibriSpeech dev-clean (K∈{2,3,4,6} × 2 seeds,
600 s, 30% short backchannel turns, fast turn-taking so multi-speaker spans occur).

- **Gate A — PASS.** Album (min_score 0.35, margin 0.1, admission 1.0 s, k=10):
  live accuracy 96.4-99.5% per meeting, mean 98.5%. At deployed margin 0.2 with
  sweeps: 95.7-99.3%, mean 98.4%. Production's latest-span overwrite at its own best
  config: 51.7-87.4%, mean 66.4% — reproducing the sibling project's <80% failure.
- **Gate B — PASS.** No divergence in any meeting (the sibling failure mode). 6/8
  meetings |live−file-oracle gap| ≤ ~3 pp; in 3 meetings the album+sweep beats the
  whole-file AHC oracle by 30-47 pp (naive offline clustering chain-merges similar
  voices; the quality-gated online album does not). Sweeps rescue mis-tuned configs
  (min accuracy 76.7%→94.1%). Sweep cost ~0.1 ms per sweep at 600 s; <10 ms
  extrapolated to 3 h. Embedding 332-343 ms/unit single-thread CPU — ~7x headroom
  under the 2.5 s span cadence.
- **Gate C — PASS.** 7/7 assembly cases byte-exact under duplicates/reorder/drops/
  burst loss; gap manifests exactly account for dropped frames; checkpoint/resume at
  40%+70% reproduced the uninterrupted mixed tape byte-identically.

- **Live retained-tape diagnostic — upstream capture bug proved (2026-08-02).** Exact
  `c2e6248` clean truth replay scored 91.35%; the retained system lane scored 61.61%
  and mixed scored 54.66%. The Mac boundary flattened an interleaved multi-channel
  `AudioBuffer`, while downstream downmix interpreted the flat array as channel-major.
  A 512-frame reproduction matched the retained spectrum at 0.941 correlation, and a
  one-variable downmix intervention scored 62.36% RED → 91.35% GREEN → 62.36% RED.
  This refutes album thresholds, sweep ordering, mixer contamination, and config drift
  as the primary cause. Fix the capture-boundary layout normalization, then rerun F4b;
  F4b remains OPEN until the fixed live path itself passes.

- **Formal live-corpus alignment decision (2026-08-02).** The certification driver
  recorded `CORPUS_START_SAMPLE` before launching `afplay`, which has no render-start
  handshake. Two consecutive captures placed identical decoded phrases 2.02-2.15 s
  apart; the first scored 75.15% at its declared origin but 91.33% after a label-blind
  reference-coverage alignment, while the second moved from 91.68% to 90.96%. The
  formal evaluator now chooses one deterministic global shift by reference speech
  coverage only, bounded to ±3.0 s in 0.05 s steps. Declared/aligned origins and
  unaligned metrics remain visible. Speaker labels do not participate in alignment;
  the gate separately requires a distinct mapped label for every reference speaker and
  reports each speaker's correctness. Canonical counts are diagnostic only. Identity
  thresholds and the 40,000-sample span cap remain unchanged.

- **Real-audio gate — PASS (2026-07-29).** 9 real interview clips (Lex Fridman /
  Acquired golden corpora from m4mbp, `proto_real_replay.py`): album+sweep **95.2%
  mean / 87.4% worst-clip**, beating the whole-file oracle (94.5%/72.7%); all 3-min
  clips 97.4-99.5% including a 3-speaker crosstalk clip; 1-min clips form the
  cold-start floor, matching the birth-floor amendment's rationale. Measured
  requirements that fall out: deployed `min_match_score` 0.5 caps real-audio accuracy
  at 90.7% mean (recalibrate toward 0.35, recorded decision); `SWEEP_MERGE_THRESHOLD`
  0.70 is safe (max true cross-speaker centroid sim 0.259 across all clips); the
  terminal end-of-session sweep is load-bearing, not optional.

Production decision (2026-07-30): min_score 0.35, margin 0.1, matching evidence
0.5 s, birth 1.0 s, enrollment 2.0 s, k=10 exemplars, sweep every 60 s + merge
threshold 0.70 + terminal sweep at session end. The hash-pinned production-plan replay
scores **93.50% mean / 82.14% minimum**, with all 3-minute clips **>=96.11%** and
zero residual corrections. Remaining caveat: in-span local diarization assumed correct
(isolates the identity layer; F1/F2's distinct-voice clauses cover it end-to-end).

## 8. Open questions (fog)

- Sweep cadence + album parameters — calibrate on prototype data, then real recordings.
- Cross-meeting persistent album (recognize returning interviewer) — product+privacy.
- Boundary re-ASR for words cut at 2.5 s seams (text quality; orthogonal).
- Enrollment-prefix lineup inside MOSS as hard-case verifier.
- Speaker cap (16) and span cap (2.5 s) tuning once identity is stable.
- Retention TTL / privacy posture for stored session audio.
