# ADR-0002: Two-tier diarization with a fingerprint album and retrospective sweeps

- Status: **Accepted** (2026-07-29) — design accepted by product owner 2026-07-28;
  prototype gates A/B/C passed, evidence in `docs/design-streaming-diarization.md` §7.
  Enrollment-floor amendment accepted 2026-07-30.
- Deciders: product owner (Gao) with Claude (architecture session, 2026-07-28);
  peer audit input from Codex (`AAgent/260728-moss-audio-flow-explain/`).

## Context

MOSS performs batch (non-streaming) transcription+diarization at 35-40x real time, but
its per-request capacity is bounded by model working memory: `MOSS_MAX_MODEL_LEN=16384`
tokens, audio ≈25 tokens/s, `MOSS_MAX_NEW_TOKENS=12000` reserved for output → ~150 s of
audio per request. This bound is architectural (context arithmetic), not configuration
that can be relaxed to hours. Consequently no single MOSS request ever sees a whole
meeting, and cross-request speaker continuity must come from an external identity layer.

Today's live path keeps canonical speaker IDs across ≤2.5 s VAD spans but stores only
the **latest span's embedding** per speaker
(`app/live_provider_bundle.py` `_reconcile_committed_vectors`: replacement, not
aggregation), so one noisy short utterance can destroy a good voice reference. Batch
mode reconciles 150 s windows by time overlap only (Tier-A); embedding Tier-B is
disabled in deployment. Server-side PCM is pruned after span commit (60 s retention
cap), so no retrospective processing is possible.

A sibling project attempted the same live-diarization goal and failed at <80% speaker
accuracy: its live path used only embeddings available up to time T and never
retrospectively updated historical assignments, so live accuracy **diverged** from
whole-file accuracy instead of converging. The acceptance bar here is ≥90-95% live
speaker accuracy and demonstrated live→file convergence.

## Decision

Adopt a two-tier architecture: keep the low-latency live span path for provisional
output, and add three components that exploit the 35-40x GPU headroom:

1. **Durable session audio assembly ("tape recorder")** — append every acknowledged
   frame to per-lane (mic, system) + mixed session logs with silence-filled, manifested
   gaps. Assembly is the substrate for retrospective work and crash/resume.
2. **Quality-gated fingerprint album** — per canonical speaker, retain top-k exemplar
   embeddings (admission: ≥2 s clean speech, sufficient match margin; identity trusted
   after ~5-10 s accumulated) and match against a duration-weighted centroid. Replaces
   latest-span overwrite. Injected via the existing `canonical_embedding` hook so the
   matcher and abstain/birth semantics are unchanged. The album is the compressed
   context handed forward: later processing never re-hears earlier audio.
3. **Retrospective sweep ("clean-up pass")** — periodically, on uncertainty events, and
   at session end: re-embed/re-cluster the assembled tape (diarization only — **no
   re-ASR**), constrained-seeded by live labels, and rewrite historical speaker
   assignments. Corrections surface as silent transcript revisions (server-side
   revision log retained). Batch mode's disabled Tier-B is replaced by this same album
   engine, unifying live-final and batch identity.

## Alternatives considered

- **Re-run MOSS from inception (0→t) each refresh** — rejected: MOSS still only hears
  150 s windows, so full-context accuracy never materializes inside the model, while
  cost grows O(T²) (~5 min GPU per refresh at hour 3 vs constant ~4 s incremental).
- **Enrollment-prefix "voice lineup" inside MOSS** (splice known speakers' clips before
  each window) — deferred as a hard-case experiment: consumes listening budget
  (~3 s × speakers per window) and needs audio surgery; album achieves matching outside
  the model at near-zero cost.
- **EMA centroid** — rejected: no outlier rejection; early bad enrollment corrects
  slowly.
- **Live-only fix (album without tape/sweep)** — rejected as terminal state (kept as
  implementation step 1): without retrospective rewrites, live accuracy repeats the
  sibling project's divergence failure.

## Consequences

- Server retains meeting audio (~0.3 GB/hr; TTL configurable) — a privacy/retention
  posture change from prune-after-commit.
- Transcript becomes a living document until session end: consumers must tolerate
  versioned label rewrites (portal already polls state at 1 Hz).
- Live-path change is localized to the evidence provider's reference-vector policy;
  matcher thresholds (`min_match_score`, `min_margin`) need recalibration against the
  album's centroid statistics.
- New background workload must yield GPU to live spans (embedding sweeps are
  CPU-capable via ONNX).
- Implementation order: album → tape recorder → sweep → batch unification; each step
  independently shippable and validated by prototypes A/B/C before production work.

## 2026-07-30 enrollment-floor amendment

Matching, birth, and enrollment are separate decisions. The matching evidence floor
remains 8,000 samples (0.5 s), birth remains 16,000 samples (1.0 s), and only album
enrollment rises to 32,000 samples (2.0 s). Matching uses the duration-weighted centroid
of the quality-gated bounded bank.

The hash-pinned nine-clip gate re-embedded every clip under the deployed 0.5 s span plan
and drove the production identity objects: **93.50% mean / 82.14% minimum**, all three
3-minute clips **>=96.11%**, zero residual sweep corrections. Coupling birth to the new
2.0 s enrollment floor was rejected: one cold-start clip fell to **49.4%**.

## 2026-08-01 retrospective leave-one-out amendment

A sweep must not use the observation it is judging as evidence for that observation. Before
this amendment, an early birth's album reference was the exact retained vector that created it;
its self-cosine was therefore 1.0 and later context could never repair the birth unless the
stronger two-bank merge rule also fired. That rule correctly excludes provisional evidence, so
short-lived duplicate canonicals remained permanent.

Sweep matching now recomputes a candidate reference with the judged observation removed. Live
matching, the 0.35 score, 0.1 margin, 0.5 s matching floor, 1.0 s birth floor, and 2.0 s enrollment
floor are unchanged. On the hash-pinned five-minute `acquired_alphabet` fixture, the production
path moved from **86.94%** final accuracy and six canonicals to **91.35%**, four final canonicals,
four corrections, and zero residual corrections. David/Ben recalls were **94.60% / 89.28%**.
The nine-clip production gate did not regress: **93.50% mean / 82.14% minimum**, all three
3-minute clips **>=96.11%**, zero residual corrections.

## 2026-08-03 as-built sweep-level amendment

This amendment resolves a contradiction in the original Decision prose without rewriting it.
Component 2 said the album was compressed context and “later processing never re-hears earlier
audio”; component 3 said a sweep would re-VAD and re-embed the tape. Both cannot describe one
sweep. They describe two different levels:

- **L1 sweep — shipped:** rematch the retained embedding ledger against the current quality-gated
  album, using leave-one-out references for the observation under judgment; merge compatible
  canonicals and revise historical speaker labels. It never reads tape audio, never re-runs VAD,
  never re-embeds PCM, and never re-runs ASR. The measured 6→4-canonical, 91.35% result in the
  preceding amendment is L1 evidence.
- **L2 sweep — future:** read the opt-in retained tape, resegment/re-VAD/re-embed it, then revise
  speaker assignments. It may re-hear audio only for diarization evidence and must **never re-run
  ASR**. No production L2 path or acceptance evidence exists yet.

The “never re-hears earlier audio” statement governs live matching and shipped L1. The original
re-VAD/re-embed language remains the L2 target. Claims of tape-driven convergence therefore remain
future until L2 is built and measured; shipped L1 claims stay bounded to embedding-ledger rematch.
