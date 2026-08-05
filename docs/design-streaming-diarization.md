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

The numbered architecture below is the 2026-07-28 target. This matrix is the controlling
2026-08-03 as-built status; “new” labels in the original prose are historical.

| Capability | As built | Target | Gate/status |
| --- | --- | --- | --- |
| Fingerprint album | **Shipped:** quality-gated bank, duration-weighted centroid, 2.0 s enrollment | keep bounded/quality-gated | 9-clip floor 93.50% mean; long clips >=96.11% |
| Retained tape | **Shipped, opt-in/off by default:** per-lane/mixed working substrate | source for L2 diarization | ADR-0003 governs root/TTL/cap/reaping |
| L1 sweep | **Shipped:** embedding-ledger leave-one-out rematch/merge and label revision | retain as cheap first pass | acquired fixture 91.35%, 6→4 canonicals |
| L2 sweep | **Not built:** L1 does not re-hear tape | tape resegmentation/re-VAD/re-embed; never re-ASR | future measured cycle required |
| Crash behavior | **Partial:** startup reaps abandoned tapes; no full live-session/checkpoint resume | explicit resumable session state if authorized | startup-reap tests only; do not claim crash/resume |
| Batch identity | **Not unified:** batch and live remain separate engines | one identity engine, two entry points | future compatibility + quality gate |
| Retention policy | **Decided:** ADR-0003, opt-in root, zero default post-session TTL, declared cap | deployment-specific positive TTL/cap optional | policy tests + deployment declaration |

Sweep vocabulary is fixed by ADR-0002's 2026-08-03 amendment: L1 is shipped and consumes only the
embedding ledger; L2 is future and may re-hear retained audio for diarization, never ASR.

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

- **Corpus-truth correction (2026-08-03).** Forced alignment alone was rejected as an
  existence proof: adding a fabricated but schema-valid transcript line still passed. The
  replacement validator binds a deletion-capable local-token score to a transcript-independent
  ASR pass and to the corpus audio hash. On the authoritative 90-second control, a present line
  scored 1.000 while the two known absent lines scored 0.200 and 0.000; the measured gate is 0.65.
  The first candidate v2 and every score built on it remain superseded. The accepted audit froze
  post-audit v2 SHA-256 `28dc9a5b80098db58a261b4bfa73e2975acac31ef36e7e8f057c514d8bdc0759`:
  R1/R2/R3/R5/R6 are present; R4 keeps David activity at 161.8–163.411, represents its leading
  burst as uncertain nonlexical activity, and retains only the acoustically supported lexical text.
  Two fresh unchanged-`3232375` live runs scored 91.35% and 91.44%, both two-sided.

- **Capture-layout malformed-input policy (2026-08-03).** A production-seam prototype compared
  fail-closed, truncate, and zero-fill. Valid rectangular audio was byte-identical; unequal member
  lengths made truncation lose a valid frame and zero-fill change a truthful 1.000 tail to 0.500.
  Producers therefore emit an empty typed discontinuity for every malformed layout.

- **Real-audio gate — PASS (2026-07-29).** 9 real interview clips (Lex Fridman /
  Acquired golden corpora from m4mbp, `proto_real_replay.py`): album+sweep **95.2%
  mean / 87.4% worst-clip**, beating the whole-file oracle (94.5%/72.7%); all 3-min
  clips 97.4-99.5% including a 3-speaker crosstalk clip; 1-min clips form the
  cold-start floor, matching the birth-floor amendment's rationale. Measured
  requirements that fall out: deployed `min_match_score` 0.5 caps real-audio accuracy
  at 90.7% mean (recalibrate toward 0.35, recorded decision); `SWEEP_MERGE_THRESHOLD`
  0.70 is safe (max true cross-speaker centroid sim 0.259 across all clips); the
  terminal end-of-session sweep is load-bearing, not optional.

- **L2 Stage-0 feasibility — BLOCKED at blind holdout (2026-08-04).** Campaign A
  used production-planned spans, the pinned production WeSpeaker frontend, and three
  same-frame arms: production L1, ledger-only control, and a frozen tape candidate.
  The recorded six-case development/validation gains were +1.860557 pp over L1 and
  +1.432022 pp over ledger-only, with 13.025/24.854125 L1-unreachable seconds
  recovered. Independent review found those numbers are truth-flattered upper bounds,
  not valid blind feasibility measurements: `run_candidates.py:401` loads the golden
  reference, `production_cache.py:166-218` partitions units by true speaker, and
  `candidate_engine.py:827-835` pools tape-window evidence over those intervals. A
  controlled golden-label change A,B→A,A changed runtime shape from two units to one.
  The source audit covered `candidate_engine.py` only and missed the evaluator-to-
  candidate input boundary.

  The candidate was frozen before one recorded holdout opening. On three holdout
  cases the truth-conditioned tape arm scored 0.972477 versus L1 0.963303 and
  ledger-only 0.972477: +0.917431 pp over L1 and +0.0 pp over ledger, below the
  required +1.0 pp over each. Because even this flattered upper-bound path failed,
  the terminal `BLOCKED` decision stands and is strengthened; the scores do not
  certify a blind candidate. No rerun or post-freeze tuning occurred. No product L2
  path or Campaign B implementation is authorized. Development evidence manifest:
  SHA-256 `8f965003322fe6cf616796385e4b08cb07da0fe0f8d47fd1c70705bb62657f34`;
  single-opening holdout evidence manifest: SHA-256
  `15eb5f5f2c788802ecce4156c26d1f0819f7aafa2b1df744b8209a3a1a0e44dd`.
  Corrective record: `L2_STAGE0_VERDICT_ADDENDUM.md`; addendum-seal SHA-256
  `ad06409e9f842d6de236310820c06c59d77803edb54c8684ab767a7f691633f3`.

- **L2 Stage-0 lifecycle/resource facts (2026-08-04).** The prototype
  `finalizing` model passed all eight lifecycle invariants and all three negative
  controls. On the deployment i7-14700F under WSL, the operator-authorized
  warm/reused CPU finalizer measured RTF 0.0997407 and 179.533 s for 30 minutes;
  first-finalizer time was 180.294 s, 0.761 s over steady state and inside the
  one-time 5 s allowance. Reads remained bounded to 40,000 samples, one CPU
  finalizer was active, and the measured prototype contention proxies passed. These
  facts prove the tested lifecycle/resource shapes, not an accepted L2 accuracy arm.
  A3/A4 evidence-manifest SHA-256:
  `e2e3e3445f2a9b6a8623b28accfdbf58a8da3af19762d4b19e8424eac9876758` /
  `885ccd49875931ebdd47c7418dad80c32052bc87160c31a3ac2cc85ba604d1fe`.

- **Planner frame and seam result (2026-08-04).** L1 accuracy is
  planner-frame-dependent: the evidence distinguishes a 55-unit stale-prototype
  frame, a 92-unit corrected truth-pure prototype frame, and the 101-unit corrected
  production-planned frame. Only same-production-frame arm comparisons are valid.
  Frame result SHA-256:
  `d45a963c2e385d734cfc5003da774ed4804816b05720fc89dd4deb4f3e5358f1`;
  A2-completion evidence-manifest SHA-256:
  `9118d88326e261899f30120aa9a448a91a9bb72936741ac82725b055bca9c387`.
  Applying the two-adapter/deletion test after the holdout failure defers every
  proposed product seam. Seam-inventory SHA-256:
  `7ade72f68606902fb26ad0085787e9eedc32b10ee4539d20b65e8e101e63ad35`.

- **Corpus limits on this verdict (2026-08-04).** The blind holdout comprised
  three short, near-saturated cases; ledger-only and tape both fixed Keyu Jin to
  1.000 while the other two cases left little or no headroom. Both 30-minute cases
  remained exploratory and acceptance-ineligible pending the human audits in
  `operator-questions-A1.md` (SHA-256
  `81205f7f2f8f900b6bef0ae59516d28ba439aa78383fc0325968e9ab2c9b30bf`;
  A1 evidence-manifest SHA-256
  `5112f4ab5a9ec4f07f0408d53f3313fecbd8fc52484cec651f631224c7b644fe`).
  The `BLOCKED` decision therefore binds the current gated corpus; it does not
  measure or generalize to the unaudited 30-minute class.

- **Certification limits (2026-08-04 independent review).** The single opening is
  procedurally demonstrated by the guard, one recorded harness run, and absence of
  post-freeze tuning; it is not access-control-proven because holdout paths were
  plaintext in-tree from A1. Family v1→v4 preregistrations and results were
  co-committed, so NOTES sequencing and run transcripts support but do not
  independently seal ordering. These limits and corrected A3/A4 reproduction
  surfaces are in `L2_STAGE0_VERDICT_ADDENDUM.md`; sealed A5/A6 artifacts remain
  untouched. Addendum-seal SHA-256:
  `ad06409e9f842d6de236310820c06c59d77803edb54c8684ab767a7f691633f3`.

- **L1.5 live-mode uplift bench campaign — BLOCKED for product (2026-08-05).**
  Same-method numbers are planner-frame-dependent. The Stage-0 ledger control measured
  +0.4285 pp on development and +0.917431 pp on its blind holdout over truth-timed unit
  partitions. On L1.5's D8-safe production-endpoint-over-deployed-ASR runtime units, the
  exact sealed Stage-0 ledger arm and the newly written F1 arm produced identical labels,
  six proposals, six accepted changes, and only +0.0342058 pp over L1. The prior gains are
  therefore frame-flattered and are not evidence of a cheap live-mode uplift. Stage-0
  development/holdout raw SHA-256:
  `2842f66eae64843d8aa13c9e65c1f95f20a803489613c355c2a07bb1a40c71d5` /
  `43e9ff33e664331aa614bc748f5b6254a545c3252694a5522c90044c220e9966`;
  D8-safe differential evidence-manifest SHA-256:
  `c1973a7f8e65b60d46bebabc3e42c27c58429572ee4e56f27ffa30e4e4edb9a4`.

  The post-hoc regrouping method class is inert on this runtime frame: all 27 F1 grid
  configurations produced one aggregate outcome; the two-config trace showed three
  proposals from 75 eligible units because fixed cluster-to-canonical mapping starved the
  proposal stage before score, margin, or budget could bind. Parameter-diagnosis evidence-
  manifest SHA-256:
  `6646576bbbc46d16389deceb24bf04afd2b5bc308a3b0d5449ae6287a7d1729a`.
  Duration-adaptive live-pass margin also failed: development was -0.054220 pp, validation
  was unchanged, while its 30-minute sweep-compute p95 passed. F3 evidence-manifest
  SHA-256: `a0fac3d01565e7b25e0783b2e505102a3e31d3d733ff3fc289c5412acda5aed1`.

  F2 remains directional evidence only. On one unaudited dual-lane minute, the
  duration-weighted own-lane acoustic classification rate moved from 0.890916 without the
  prior to 0.915844, 0.940772, and 0.978163 at strengths 0.05, 0.10, and 0.20. It is not
  speaker-identity acceptance evidence. F2 evidence-manifest SHA-256:
  `800b0aa8144a4f80f453d82b960204ef44687ad56f312ae78fcdbbf2856030bb`.
  Acceptance-grade dual-lane evidence is the primary surviving lever: it requires multiple
  synchronized meetings, audited speaker/activity/overlap truth, lane-integrity controls,
  D8-safe same-frame arms, and preregistered dev/validation/single-open holdout gates. No
  family reached freeze, so the L1.5 holdout was never opened; its three cases retain blind
  evidentiary value. Family-verdict evidence-manifest SHA-256:
  `03bc9919c539c1fd4cc012333e6abcd85450bdbcee8e955f1986fdd75f19e942`.

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
- L2 tape resegmentation/re-VAD/re-embedding design and measured acceptance.

Retention TTL/privacy posture is no longer fog: ADR-0003 decided it. Full crash/resume and batch
identity unification remain targets, not shipped behavior.
