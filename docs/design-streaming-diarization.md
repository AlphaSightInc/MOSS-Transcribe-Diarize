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

- **Durable named voice-profile matching — ACCEPTED (2026-08-26).** A fresh production-path
  prototype used the pinned WeSpeaker ResNet152 ONNX encoder, production live evidence units,
  and production `FingerprintAlbum` centroids over five speakers in two 30-minute English
  interviews. Three non-overlapping 5-minute enrollment windows preceded every probe. Across
  470 known probes, 470 leave-true-profile-out unknown scenarios, 1,880 different-person pairs,
  14 terminal album probes, and 1,530 operating points, the accepted cross-session rule is
  cosine `>= 0.46`, no runner-up margin, at least `1.0 s` eligible speech, and the
  LiveTranscribe-style L2-normalized arithmetic mean of stored named-session samples. It named
  441/470 causal probes correctly, abstained on 29, produced zero observed wrong names, abstained
  on 470/470 unknowns, and named 14/14 truth-aligned terminal albums correctly. LiveTranscribe's
  `0.51` was safe but lost four additional correct names; MOSS's within-session settings
  (`0.35` score, `0.10` margin, `0.5 s` floor) produced three wrong known names and three false
  names when the true profile was
  absent. Below either gate, or without an embedding, the durable matcher keeps `Speaker N`.
  Terminal end-to-end cluster-to-profile behavior and every population beyond the measured five
  speakers remain **unmeasured**. Reproduction and full denominators:
  `prototypes/streaming-diarization/voice-profile-matching/NOTES.md`.

- **Short provisional / longer joint-MOSS witness (2026-08-24) — rolling text PASS,
  speaker authority OPEN.** On three fully referenced real 60-second interviews, reducing
  the live hard cap from 2.5 seconds to one second cut mean first-word age 3.04→1.00 seconds,
  but worsened WER `.200→.377`, DER `.176→.457`, and endpoint inference RTF `.057→.115`.
  A truth-blind ten-second view every five seconds brought WER to `.146` from either base,
  proving that a longer joint-MOSS witness can overwrite the one-second provisional words.
  DER remained `.292` from the one-second base versus `.114` from the 2.5-second base,
  because the prototype still reconciled witness speakers through the base identity anchors.
  Every-seam five-second witnesses worsened WER and DER and are rejected. A terminal full-
  minute view scored WER `.104` / DER `.102`. No production cap change is authorized: next
  prototype must make the longer witness authoritative for its own speaker evidence while
  keeping the one-second lane explicitly provisional. Full contract and results:
  `prototypes/streaming-diarization/live-multiview-prototype/NOTES.md`.

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

- **Mixer lane-level experiment — no policy selected (2026-08-18).** A preregistered,
  committed-before-run experiment drove the real 59.584 s aligned Core Audio Tap and room-mic
  capture through the production `LiveCompatibilityMixer` and the live vLLM endpoint. System
  RMS was -19.577 dBFS versus microphone -34.954 dBFS (15.377 dB disparity). The current
  fixed-headroom mix scored 0.28324 word error rate / 42 missing words against the quiet-lane
  reference. A derived peer-RMS match (5.87275×, not hand-tuned) scored 0.31792 / 48 and clipped
  one input sample; neither arm reached the output limiter. It therefore fails the frozen
  5 pp WER-improvement and missing-word rules. Both lane references describe the same playback,
  so the one-capture result cannot attribute recovered text to a lane or define a general warning
  threshold. No normalisation, AGC, or fixed-offset production change is authorized. Raw result:
  `evidence/phase1/g3-attended/iteration-20-lane-level-aligned-prototype.json`; preregistration:
  `prototypes/streaming-diarization/lane-level-preregistration-v2.json`.

- **Mixer different-speech gain response — no production remedy selected (2026-08-19).** The v1/v2
  `RETAIN_IDENTITY` selection is historical and invalid: its total disparity was 25.741875 dB rather
  than the attended 15.377 dB; `SequenceMatcher` was not true LCS; per-lane WER charged other-lane
  words as insertions; and summed lane matches double-counted hypothesis tokens. The sealed v3
  experiment recalibrated synthetic attenuation to -4.635124658 dB, used a deletion-capable
  shuffle-edit recurrence that credits each hypothesis token once, and replicated the discovery
  gain on three distinct-speech validation corpora. Parity +3 dB improved discovery WER by 34.58 pp
  but validation gains were +19.51, +4.35, and -14.77 pp: **GAIN_ONLY_FAILED_REPLICATION**. A
  whole-clip separate-lane merge then improved all four corpora, but its live-path follow-up exposed
  the actual endpoint cost: k3 WER worsened 23.17 pp; 3/4 missed 0.80 identity accuracy; 3/4 had an
  unparseable lane span; and first/last-word p95 worsened on 3/4. Bounded queue, stop drain,
  two-session fairness, overlap, attribution, namespace, and capacity passed. Therefore no gain,
  normalization, AGC, limiter, warning threshold, or dual-lane production path is selected. Obtain
  fresh real attended lane evidence before another remedy. Raw results:
  `evidence/phase1/g3-attended/lane-balance-v3-20260819.json`,
  `evidence/phase1/g3-attended/separate-lane-decode-20260819.json`, and
  `evidence/phase1/g3-attended/live-dual-lane-20260819.json`.

- **Attended apparent over-split — not confirmed as a defect (2026-08-19).** The stopped
  29-span session remained queryable and its private vector journal preserved all five final album
  centroids. Raw cosine was -0.074202 for S01/S02; production correctly floor-clamped it to 0.000.
  Raw and production cosine were both 0.004914 for S04/S05. Both are far below the
  deployed 0.35 match floor and 0.70 sweep-merge threshold. More importantly, the source transcript
  identifies S04 as Lex Fridman's question and S05 as James Holland's answer: those are correctly
  separate people. The dynamic commercial behind S01/S02 was not retained, so that pair has strong
  acoustic evidence but no human-auditable truth. Do not tune match, margin, admission, birth, or
  merge policy from this observation. Reopen only if the ad audio/source proves one reader. Raw
  diagnosis: `evidence/phase1/g3-attended/attended-session-8049-speaker-split-diagnosis.json`.

- **Attended word-to-screen latency — attributed; no endpoint policy selected (2026-08-19).** The
  active attended path is the legacy `/live` portal at 500 ms cadence, not the React poller. A fresh
  23-advance M4 capture measured 2.399 s p95 last-sample age, 142 ms p95 paired fetch, and a 3.041 s
  last-sample analytic visible bound. Since 27/30 canonical spans ran to the 2.5 s cap, the additive
  first-sample bound is 5.541 s, matching the reported 3–5 s delay. Server events now measure queue,
  canonical processing, and commit-to-fetch on one monotonic clock; `/live` measures fetch through
  the actual post-DOM animation frame; `mtd-capture latency` v3 reports exact newest-span start/end
  ages on the capture clock. No absolute cross-host clocks are subtracted. A sealed real-speech
  cap/silence sweep selected no change: the quality-safe 2.0 s arm improved median first-word p95
  by 487.675 ms, 12.325 ms short of the frozen discovery gate, and increased unparseable output;
  shorter arms failed identity, WER, load, or parse guards. Keep 2.5 s cap / 0.5 s silence and the
  generated manifest hashes. Raw evidence:
  `evidence/phase1/g3-attended/live-latency-baseline-20260819.json` and
  `evidence/phase1/g3-attended/live-cap-silence-sweep-20260819.json`.

- **Deployed server-stage timing — exact release-compatible instrumentation (2026-08-19).**
  Production now runs server-only diagnostics commit `89fc48376ec2f855d4cac504cef4a2dc18ab2704`
  directly atop release `fb83ba5ee60c44688e2580a398bfa388dcf5e67a`. Deployment changed only
  manifest `source_revision`; every config hash and the sealed portal bytes remained unchanged.
  A 52 s real-vLLM probe accepted 208/208 lane frames, produced 21 committed advances, and kept
  two concurrent readers green. One-clock p50/p95 values were: queue 0.5/0.7 ms, canonical
  processing 587.0/766.2 ms, queued-to-processed 587.6/766.5 ms, and commit-to-server-events-read
  411.5/589.6 ms. Decode p50/p95 was 299/413 ms; no request hit the token cap. Queueing was
  negligible. Post-freeze work is about 1.36 s at p95; adding the 2.5 s hard-cap accumulation
  explains an approximate 3.86 s first-word path before browser DOM work. This strengthens the
  attribution but does not supersede the quality-gated `NO_POLICY_CHANGE` cap-sweep verdict.
  Actual DOM timing remains implemented/tested on `dev` only because the current production
  release byte-seals `live_capture_portal.py`; do not claim deployed browser-DOM evidence from
  this server probe. Raw artifact:
  `evidence/phase1/g3-attended/server-stage-timing-deployed-20advance-20260819.json`.

- **Fresh M4 exact-build rerun — system/latency pass; microphone remains an operator gate
  (2026-08-19).** M4MBP was restored online, checked out detached exact `aca1600`, rebuilt,
  reinstalled with its signing requirement unchanged, and retained both TCC grants. Its old
  MacStudio pairing failed transport and was rejected; fresh direct production pairing then
  drained cleanly. A 24-advance system-lane run measured a 0.904 s p95 last-word analytic visible
  bound and 3.376 s first-word bound, with 268 frames, zero retained frames, intact timeline, and
  no pump failure or session refusal. Four muted lane-separation canaries all proved that system
  capture survives output mute, but an external MacStudio room source did not produce its known
  microphone marker—even at maximum external output, with an ASR-stable marker, and with temporary
  M4 input gain 71→100%. Transport/lifecycle and system-lane latency pass; microphone, overlap, and
  perceived-delay acceptance remain fail-closed until a person near M4 speaks into its microphone.
  No gain, input-volume, mixer, span, or identity policy is selected. Raw redacted record:
  `evidence/phase1/g3-attended/m4-exact-build-rerun-20260819.json`.

- **Native microphone signal diagnosis — path healthy; external canary source was inaudible
  (2026-08-19).** A throwaway exact-PCM prototype validated JSON-safe per-lane RMS/peak aggregates
  at 0.332 ms per 8,000-sample wire frame; the production implementation exposes those aggregates
  only through same-user local status, never the heartbeat, and passed 205 Swift tests. Exact
  `08475d3` was rebuilt/reinstalled on M4 without changing its signing requirement or TCC grants.
  During a valid muted lane-separation run, the MacStudio external source reached M4's microphone
  at only -48.10 dBFS median / -45.40 dBFS maximum in the room window and did not raise the
  session maximum; the marker was not transcribed. In a deliberately confounded near-field control,
  M4's own speakers raised the same microphone path to -9.13 dBFS and `banana` committed in five
  spans. This proves microphone hardware → AVAudioEngine → downmix/resample → strict-v2 wire → ASR
  response, while refuting the external speaker geometry as attended microphone evidence. It does
  not prove lane separation or overlap because local speaker audio reached both lanes. No signal
  threshold, gain, input-volume, mixer, or identity policy is selected. A person beside M4 remains
  the irreducible microphone/overlap/perceived-delay gate. Raw redacted record:
  `evidence/phase1/g3-attended/m4-native-signal-diagnosis-20260819.json`.

- **Correct attended browser path — transcript recovery accepted (2026-08-19).** The operator's
  actual path is M4 Chrome → `https://macstudio.tailnet.aisight.us:7861/` → MacStudio's local SSH
  tunnel → Alienware vLLM; the native app and Alienware `/live` page are not this acceptance path.
  Chrome accepted 85 frames and froze nine spans during a failed run, but processed none. Direct
  streamed and non-streamed requests inside Alienware reproduced zero audio-response bytes while
  `moss-vllm.service` reported no running/waiting requests and the GPU stayed at 100% SM with only
  88 MiB free. The operator authorized restarting that dedicated service only. Its new process
  then transcribed a real 2.5 s clip through production `VllmRunner` in 0.849 s. The fresh attended
  Chrome session closed with 729,792/729,792 samples accounted, zero retained/pending work, and
  exactly 21 queued/started/processed spans. Queue wait was 0.766/122.350 ms p50/p95; decode was
  346.129/469.071 ms; queued-to-processed was 672.167/953.703 ms; no decode capped. The operator
  confirmed that transcript text appeared correctly while counting over the noisy background WAV,
  with both foreground counts and background speech visible. This closes the person-near-M4
  microphone/transcript gate without selecting any gain, mixer, span, identity, or threshold
  change. A separate perceived-delay grade was not stated. Raw record:
  `evidence/phase1/g3-attended/macstudio-m4-browser-recovery-20260819.json`.

- **W2 event-evidence boundary — harness repair required, no scheduler policy (2026-08-18).** The shared
  bench drove a complete, fair two-session lifecycle through the production asynchronous event writer and
  lifecycle evaluator. In all three trials, the writer had begun writing but the immediate read returned 0/48
  records and the evaluator failed closed; the existing writer-close barrier made all 48 records readable and
  fairness pass at skew 1. The next change must add a writer-owned drain barrier before evidence evaluation;
  it must not change fairness, stop-drain, latency, or scheduler values. Raw artifact:
  `evidence/phase1/w2-local-concurrency/iteration-33-writer-evaluator-boundary.json`.

- **W2 rendered-ownership wait — no reconnect policy selected (2026-08-19).** A live single-overload probe kept
  the production loopback live routes and read-only vLLM endpoint, but ordinarily polled each observer before
  allowing one reconnect. Its exploratory 120 s bound expired with both canonical own markers present and no
  foreign marker, yet one peer's rendered own marker still absent. Session-local 429, peer acceptance, retry,
  peer replay, and both clean stops passed. The probe therefore did not reconnect and fails closed; it is not
  evidence for moving reconnect later or lengthening a timeout. Raw artifact:
  `evidence/phase1/w2-local-concurrency/iteration-38-overload-rendered-ownership-wait/overload-rendered-ownership-wait.json`.
  It establishes no G4/G5 result or rendered-publication product defect.

- **Live-mode convergence campaign E0-E4 - the terminal live surface IS the paired file arm
  on the trio; no cap, prompt, model or file-mode change selected (2026-08-25).** On the three
  fully referenced 60-second interviews, the campaign's terminal live surface scores WER
  `.103946`, DER `.102111` and speaker accuracy `.897889` - the paired file arm's own values
  (file WER `.103946`) to six decimal places, a live-to-file distance of `0.000000` on all
  three axes - against a 2026-08-24 live baseline of `.199870` / `.176389` / `.823611`. The
  five-minute case moves the same way: WER `.146375` -> `.050616`, DER `.131533` -> `.057933`.
  The trio WER ladder is `.199870` baseline -> `.192294` bounded salvage (E1) -> `.131357`
  rolling 10 s / 10 s re-decode (E2) -> `.103946` terminal re-decode (E4), so rolling bought
  most of the gap and the terminal pass closed the remainder to zero. The identity is
  structural, not tuned: E4 hands the session's complete mixed tape to the same
  `WindowedRunner` object, with the same resolved inference options, that file mode uses, so
  on a meeting that fits one 150-second window "live" and "file" are one request. E0 repaired
  the instrument first (a replay client silently dropping `revised_transcript` and
  `label_revision_version`; three decode endings reported as one; a deployed scorer that
  credits a 60-second `xx` segment with text coverage `1.0000`), and E3 measured witness-owned
  speaker authority and **declined to ship it**: the arm ties on every gated axis (trio DER
  `.111278`, speaker accuracy `.888722`). That answers the open speaker-authority item left by
  the 2026-08-24 multi-view entry above - a longer witness owning its own speaker evidence
  changes no gated number, because the terminal pass re-resolves identities from the complete
  tape and never consults the ownership model.

  Costs, measured on the deployed service over five cases: combined real-time factor during
  capture max `.172669` against a bound of 1.0; terminal decode real-time factor mean
  `.032575` after capture stops; stop -> published final surface cold `2.574621` s, warm p50
  `2.586969` s, max `10.802953` s on the five-minute case; peak retained audio 9 600 000 bytes
  under a capacity the deployment declares, and no tape survives its session. What did NOT
  change carries as much of the verdict as what did: file mode byte-identical on every case,
  the 2.5 s span cap / 0.5 s minimum silence / prompt / model / greedy decoding untouched, one
  in-flight request per harness, terminal work never enters the capture clock, and the
  terminal pass replaces the surface exactly once (a second proposal is refused). Shipped:
  `moss_transcribe_diarize/app/live_span_bounds.py` (bounded salvage),
  `moss_transcribe_diarize/app/live_transcript_convergence.py` (rolling convergence, word
  revision, terminal finalizer, seam resolution),
  `moss_transcribe_diarize/app/live_arbiter.py` (refinement scheduling),
  `moss_transcribe_diarize/app/live_tape.py` (complete mixed tape) and
  `moss_transcribe_diarize/app/live_service_runtime.py` (asynchronous finalization), with the
  decisions recorded as `docs/adr/0005-live-text-finalization-authority.md` D1-D9 and
  `docs/adr/0003-live-session-audio-retention.md` D8.

  **Five gates are unsigned**, each needing an owner ruling rather than more code:
  `G2_live_transcript_reproducible` (the deployed decoder is not bit-reproducible at five
  minutes; all four 60-second cases are), `G_M1_1_trio_live_wer_bound` (`.192294` against a
  `.190` bound, traced to one decode flip that entered the instrument before salvage was
  written), `G_M2_4_correction_p95` (`8.756675` s against a 6.0 s bound - arithmetic, not
  slowness: a 6 s p95 needs window + stride <= 12 s and the preregistered grid's four
  geometries floor at 6.46 / 8.51 / 11.64 / 12.81 s), and `G-M4-3` / `G-M4-4` (on the
  three-minute case the faithful terminal surface `.126177` is the file arm's own number while
  the rolling surface it replaces scored `.122411`, so converging to file mode is there a
  small step back). Two findings outlive the campaign. The deployed
  `evaluation.calculate_diarization` pays a bonus for publishing the same audio twice: it sums
  the overlap of every (reference, hypothesis) pair, so `lex_adam_frank`'s file-arm `.053222`
  becomes `.066222` once the duplication is resolved, all of it `miss` - the §3.4 extent
  artifact in a new shape, duplication rather than padding. And 63 % of the remaining speaker
  error is segments straddling a reference turn, owned by text geometry rather than identity,
  with 27 % sub-0.5-second microfragments below the evidence floor; the next campaign should
  start from that decomposition, not from the confusion total. Every row is UNSIGNED and
  awaiting morning sign-off. Long form, with per-case tables and reproduction commands:
  `evidence/live-convergence-0824/CAMPAIGN_REPORT.md`; the plan's own ledger is §18 of
  `docs/plans/live-mode-convergence-implementation-20260824.md`; the instrument that keeps
  this paragraph honest is
  `prototypes/streaming-diarization/live-convergence/verify_design_verdict.py`. Scored exits:
  `evidence/live-convergence-0824/M0d-paired-reacquisition/` (E0, 4 of 5),
  `evidence/live-convergence-0824/M1-e1-exit/` (E1, 5 of 6),
  `evidence/live-convergence-0824/M2-e2-exit/` (E2, 7 of 8),
  `evidence/live-convergence-0824/M3-disposition/` (E3, 14 of 14),
  `evidence/live-convergence-0824/M4-e4-exit-2/` (E4, 12 of 14).

- **G4 rolling-refusal recovery and honest deployed 10/10 baseline — PASS (2026-08-25).** A
  truth-blind audit ran the existing overlap rule over every retained rolling proposal in two
  six-case passes: ordinary inputs were byte-identical `120/120`, normalized inputs applied
  `122/122`, no word or gated score regressed, and Jamie window 4 moved its later start exactly
  2,720 samples while preserving 24/24 words. Production now uses that producer-neutral resolver
  before rolling and terminal publication. A still-refused rolling proposal becomes explicit
  `proposal_refused`: its stable reason/count persist, retained PCM is released, base capture
  keeps exact accounting, and transcript bytes, commits, revision version, and canonical frontier
  do not move. `LiveSession` validation and ADR-0005 authority remain unchanged.

  The reviewed patch then ran 12 paced actual-live sessions over six real clips, two passes and
  1,239.987 audio-seconds. **G1-G7 all pass:** all 122/122 full 10-second windows applied in order;
  both Jamie runs completed windows 0-17; text/proposal refusals, PCM evictions, failed/stale
  windows, admission refusals, and terminal failures were zero; combined pre-Stop inference RTF
  was `.157340`, refinement queue depth was at most one, and endpoint queues drained to zero.
  The new settled pre-Stop baseline is macro WER `.140442`, content recall `.929636`, TBSA
  `.876970`, legacy DER `.161430`, matched-word speaker accuracy `.911512`, and reference-speech
  DER `.134804`. Pooled first-publication p95 is `3.652696 s`; changed-region correction p95 is
  separately `10.471099 s`, so the owner must now decide D-M2-3: bind `<=6 s` and prototype a
  shorter/partial geometry, or authorize 15/10 lexical with an explicit correction ceiling. Old
  15/10 shadows are historical only, not a promotion comparator. Full gates, per-case/category/
  weighted tables, raw paths, patch hashes, and the unsigned owner packet:
  `evidence/live-g4-recovery-20260825/REPORT.md` and `D-M2-3.md`.

- **15/10 lexical causal publication — REJECTED (2026-08-25).** After D-M2-3 signed O2, the
  production-path prototype replayed all 112 saved 15/10 windows across two six-case passes. The
  frozen batch algorithm reproduced saved content and settled speaker projection in 12/12
  case-runs, but it could not become an append-only live publisher: 46 selected words straddled an
  already-owned frontier and 24 more were wholly behind it. Every case-run reached the real
  session's `segment_outside_owned_interval` refusal. Moving such a word forward invents a time
  boundary; keeping its decoded start rewrites accepted authority. No measured rule authorizes
  either, so Goal 2 stopped at B1: no production implementation, deployment, or ABBA inference.
  Full cursor-, token-, straddler-, proposal-, seam-, and surface-level evidence:
  `evidence/live-15-10-lexical-20260825/causal-prototype.json`.

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

### WP18 file-mode wiring falsifier (2026-09-18)

The Account file constructor still uses overlap Tier A with embedding Tier B disabled;
its live-provider manifest reaches only the live runtime. The repo-recorded production
launcher and local measurement launcher share that construction. Enabling the pinned
existing Tier B in an isolated replay did **not** implement ADR-0002's batch album target:
three real windows / six minutes / three reference voices remained **7 identities → 7**.
Perfect embeddings likewise produced **3 identities for one voice**, **6 for two voices**.
The pairwise margin compares repeated occurrences of the same voice as competing
identities (cosine 1, margin 0); linked overlap components are excluded from candidates.
Stitching preserved the resolver's labels. No threshold or identity algorithm changed.
Wiring-only repair is falsified; album integration requires a separate measured design.
Reproduction and decisions: `prototypes/streaming-diarization/wp18-file-identity/NOTES.md`
and `evidence/mvpfix/wp18/`. This is a local diagnosis, not deployment acceptance.
### WP20 measurement — 2026-09-18: lane endpoint ownership is not the overlap remedy

On integrated WP17 (`de35ef36`), the full-reference overlap's nonzero boundaries
are identical under mixed and lane-local WebRTC endpointing (system 12/12, mic
10/10); canonical WER stays 18/106 and 9/53. Its immediate system gap is the
uncommitted tail, while the final 13/106 persists in a standalone lane decode.
Identical speech plus alternation's 25 s zero padding gives 9–11/106 instead.
No production endpoint/policy change promoted. The standing bench retains the
failed hypothesis, 24/48 s controls, exact stage counts, and limitations in
`evidence/mvpfix/wp20/NOTES.md`; lane-local scheduler timing remains unmeasured.

### WP19: file-window album composition (2026-09-18)

WP18 falsified pairwise occurrence matching: repeated observations of one voice
competed as different candidates. File mode now composes the existing
`assign_speakers`, `FingerprintAlbum`, and `LiveIdentitySweeper`: each window offers
one vector per local voice, matches canonical album references, admits evidence under
the manifest's existing rules, and a terminal sweep revisits earlier assignments.
No identity threshold, decoder/window plan, text, timing, live algorithm or saved
transcript schema changes. Embedding failure abstains without discarding words.

Production Account vLLM file composition defaults to `--file-identity album`.
`--file-identity legacy` restores the previous resolver (including disabled Tier B)
for one release. The manifest supplied through `--live-provider-manifest` supplies
the file album's identical measured policy and pinned encoder. Direct low-level
`IdentityResolver` remains the legacy implementation. Single-window decoding and
HF decoding remain unchanged: this repair addresses cross-window vLLM files.
The shared terminal-decoder composition retains its legacy resolver explicitly,
so changing the File default does not change Live terminal behavior.

A1 perfect vectors: 1 voice x 3 windows -> 1; 2 -> 2. A2 returning voice and unknown
short utterance tested; A4 admission, ambiguity and retrospective rescue use the
same live modules. Fresh decoder A3: 6 minutes -> 3 voices, 84/92 segments correct
(91.3043%), 322.11/338.04 truth-overlap seconds correct (95.2875%); 30 minutes -> 3,
420/464 segments correct (90.5172%), 1592.97/1684.98 seconds (94.5394%). No abstentions;
text/time unchanged. One global canonical-to-reference assignment, then per-segment
maximum temporal reference overlap; no per-window remapping or word-accuracy claim.
The resolver cannot repair incorrect diarization within a window.

Cost: 62.894428 seconds for three windows; 332.007926 seconds for fifteen, including
all pinned CPU embeddings. Eighteen serial vLLM requests, own tunnel 18119. These
are local corpus measurements, not a deployment or capacity qualification.

File enrollment previously returned unavailable. An explicit enrollment request now
reconstructs evidence from owner-bound retained MP3 and addressed canonical segments,
using existing admission and private-bank rules. No new persisted embedding/schema.
Saved audio is required; reconstruction costs embedding work on each enrollment request.
The MP3 prototype retained PCM voice agreement (cosine .969589); 5 s eligible, .6 s
refused. Save/reopen/export/rename/enrollment tested with real archive operations and
perfect-vector controls. Evidence: `evidence/mvpfix/wp19/`; bench: `prototypes/streaming-diarization/wp19-file-identity-album/`.
## 9. WP12 terminal lane latency measurement (2026-09-18)

A terminal lane job decodes its complete tape through the existing 150/120-second
file-window planner, then embeds the resulting speech to match the lane's settled
album. Unlike mono's overlap mapping, these lane jobs pay fresh acoustic matching
cost. On matched public-corpus parity input, original Stop-to-final was 11.803 s
at 24 s and 26.636 s at 60 s; mono was 1.970 s and 4.424 s. At 24 s only 1.829 s
was terminal decoding: approximately 6.79 s was terminal voice preparation.

The measured change runs the two independent terminal lane jobs concurrently,
then assembles results in lane order for one publication. Causal/rolling execution,
window geometry, identity thresholds and final-surface contract stay unchanged.
24/60 s prototype Stop-to-final became 7.715/16.175 s with unchanged 26/62 request
counts. All 142/351 ordered words retained their speaker assignments; 24 s saved
segments were identical, while 60 s punctuation/segmentation/timestamps differed.
This is an improvement, not latency acceptance: the 60 s case still exceeds 10 s.
180 s and 30-minute scaling are unmeasured under the 300-request WP budget.

WP1's 48 s alternation microphone interval is not a one-voice control: its supplied
reference names both Keyu Jin and Lex Fridman. The second birth retained the first
speaker's album; its score was 0.084412 versus the unchanged 0.35 threshold, with
1.56 s evidence clearing the 1.0 s birth floor. No lane evidence loss or threshold
repair is supported. A real-album regression separately verifies one returning
voice keeps its ID across silent lane gaps. Evidence and limits:
`prototypes/streaming-diarization/wp12-stop-identity/NOTES.md` and
`evidence/mvpfix/wp12/`.

Fresh-context matched instrumentation on the same 24 s parity input explains the
remaining difference (2026-09-18): mono Stop→final 1.880702 s, serial lanes
11.327668 s, accepted concurrent lanes 6.839325 s. Serial terminal begins
2.733792 s after Stop: 0.897933 s remaining rolling work, 1.108433 s queued causal
work, 0.722543 s tail work, and 0.002924 s final identity sweep. Mono has only a
0.369481 s tail job plus 0.001617 s sweep. No fixed sleep or lease delay.

Serial terminal voice preparation makes two speaker embedding calls containing
12 intervals / 43.53 audio-seconds, taking 6.704376 s. System contributes
8 intervals / 21.33 s; microphone 4 / 22.20 s. Mono embeds zero terminal seconds:
it maps labels by overlap with the existing transcript. Lane preparation already
reuses causal album vectors as references; it computes new probes from terminal
speaker intervals. Although 40.29 terminal audio-seconds overlap causal evidence,
none of the 12 intervals exactly equals a causal interval; neither whole embedding
call repeats any prior call. One 5.28 s interval repeats part of a rolling call,
whose individual interval vector was not retained. Album means cannot reconstruct
different interval encodings/averaging. Thus dominant cost is inherent to the
current acoustic-probe design; removing it requires a different evidence-mapping
design, not equivalent reuse of an existing probe. No such policy change made.
All 12 saved serial/concurrent segment dictionaries equal exactly in this pair.
Budget now authorized at 1200; 339 calls used. Optimization stopped per user's
inherent-cost instruction; 180 s remains unmeasured, not budget-blocked.

### WP12 follow-up: reuse mono's terminal mapping within each lane

**Current status: ACCEPTED by the lead after reference adjudication.** The
six requested 24/60 s comparisons pass. The 180 s attribution-equivalence failure
was adjudicated against the reference after the user rejected the premise that
the acoustic baseline was necessarily correct. All 54 restored assignments are
source-correct. The implementation has been the production lane path since
c410db8f; concurrent jobs and legacy mono behavior remain unchanged.

The user subsequently authorized changing the terminal evidence source to
mono's existing time-overlap assignment. The diagnosis above describes the old
algorithm's cost, not an unavoidable product cost. `finalize_lanes` now passes
each lane's settled pre-terminal surface and canonical speaker set to the same
`TerminalTranscriptFinalizer` used by mono. This includes accepted rolling
corrections, exactly as mono's caller does, but cannot use another lane's segments
or canonical speakers. The terminal decoder's local-speaker partition and the
existing one-to-one overlap assignment are retained.

Initially only a terminal segment with no labelled same-lane overlap received a
fresh acoustic probe. WP26 also probes an **unmapped** segment: overlap can exist
while an extra terminal local label loses the one-to-one assignment. Its PCM is
cropped to that segment; the existing revision reader,
evidence floor, matching thresholds and birth rules apply unchanged. Other-lane
evidence cannot cover this gap. A failed probe preserves the terminal words with
unattributed identity. No changes to QUALITY_BOUNDS, identity/sampling policy
values, decoder windows, causal/rolling preparation, or publication lifecycle.

WP26's retained 180 s system-lane replay reconstructs the causal album using the
original public PCM and recorded accepted intervals. Both previously unnamed Lex
turns (149.61–153.75 s, 160.68–161.40 s; 16 words) match speaker-0004 with scores
0.9405 / 0.4899 under unchanged 0.35 score / 0.1 margin. Production fallback replay
changes only these 2/56 assignments, reading 4.86 s of cropped audio; all words,
times and lanes remain identical. This is a replay of the retained post-mapping
proposal with reconstructed voice references, not a new live Stop run. Already
assigned overlap mappings remain authoritative; failed probes remain unattributed.
See `prototypes/streaming-diarization/wp26/NOTES.md` and `evidence/mvpfix/wp26/`.

**P5 scope decision remains open:** alternating remote voices within one system
lane require attribution and are supported. Two voices speaking simultaneously
inside that lane are already mixed into one waveform; this change cannot recover
words the decoder omitted. Retained synthetic mono-mixture measurements emit 184
words at parity but retain only 35/54 and 39/41 source-unique tokens. With the
second source 10 dB quieter, output has 134 words and retains 45/54 and 1/41;
with the first source quieter, 76 words and 0/54 and 36/41. These are historical
decoder-content witnesses, not word error rates or same-tab conferencing trials.
They demonstrate loss before speaker mapping. The live surface also permits one
owner per interval within a lane; overlap normalization cannot represent both
voices at once. Recommendation for P5: exclude reliable same-lane simultaneous
speech recovery from MVP acceptance; retain alternating-speaker attribution.
No separation model, new threshold, or change to overlap publication is introduced.

Before production edits, matched shadow comparisons exercised both mappings on
the SAME terminal decoder output and settled session state. All six cases passed:
24/60 s parity (13/28 segments), mic -10 dB (13/28), same voice on both lanes
(17/36). **135/135 segment dictionaries equal**, zero cross-lane assignments,
zero fallback audio. The acoustic control remained the saved output, and all six
saved/final agreements passed. This removes decoder nondeterminism from the
attribution comparison; it is not a human transcription-accuracy claim.

Three production-seam regression tests first failed on the acoustic implementation
and then passed: two covered-lane variants require no probes; a system gap requires
only its 3–5 s audio while simultaneous microphone evidence cannot cover it.
The focused lane/identity/session/coordinator/runtime/lifecycle set passed 191 tests.
The final Stop timings and full-suite results are recorded in root VERIFY-RESULT.md
and `evidence/mvpfix/wp12/overlap-*`.

Candidate Stop→final: 24 s **3.788534 s**, 60 s **7.490138 s**, 180 s
**16.964282 s** (mono 24 s reference 1.880702 s). Terminal embedding audio-seconds
fall from **43.08 / 111.90 / 335.52** to **0 / 0 / 0**. At 180 s, draining still
takes 4.794547 s and terminal processing 11.791761 s; the 10 s bar is not met.

The 180 s frozen-acoustic control uses the same decoder output and settled state
for both mapping methods. Acoustic preparation abstains for the whole system lane
on `same_span_cannot_link_conflict` (three local labels, two known system voices).
Overlap maps 54/56 system segments that acoustic leaves unassigned: 50 segments /
543 words to speaker-0001, 4 / 32 to speaker-0004. Two remain unassigned; mic 30/30
segments equal. Words, boundaries and lane ownership do not change. The original
any-case equivalence falsifier stopped work at 1073/1200 calls without tuning.

The subsequent reference adjudication confirms **all 54 restored assignments**:
50 Bill Ackman segments and four Lex Fridman segments. Reference rows 2 and 4 name
Lex; speaker-0004 is legitimate at 29.61–33.75, 40.68–41.40, 89.61–93.75 and
100.68–101.40 s. The same Lex turns at 149.61–153.75 and 160.68–161.40 s remain
unassigned (16 words). Reference timestamps are coarse: reviewed word-to-reference
associations and raw time overlaps are retained separately for every system row
in `reference-adjudication.json`. The acoustic whole-lane abstention was wrong;
this is not a single-voice fixture. The lead subsequently accepted the improvement
without tuning. The two remaining Lex turns have causal overlap but their third
terminal local label loses the unchanged one-to-one assignment against two known
voices. No fallback runs for those covered turns. Truly uncovered segments use
cropped acoustic probes and may separately abstain. Both limitations preserve words.
An independent 180 s single-voice regression now keeps all 36 terminal segments
attributed without probing. The uncovered-tail regression covers both successful
preparation and abstention; 24/60 s deterministic tests preserve all 13/28 accepted
row geometries with synthetic words, supplementing the real 135-row comparison.

One authorized mono-180 run on verified base archive 37979e53 takes **12.717313 s**:
1.282284 s before terminal, 11.025424 s decode, 0.000692 s overlap mapping,
0.002557 s publication-method wall time, zero terminal embeddings. The candidate
lane-180 critical decoder stage is 11.783398 s (system; mic 9.257648 s), following
4.794547 s before terminal. Whole-meeting decode dominates both: 69.5% and 86.7%
of observed lane/mono Stop time. Old lane instrumentation bounds mapping plus
other non-decode work to 3.45 ms/system and 2.97 ms/mic; it does not separately
measure those calls. Last terminal return to publication event is 2.875 ms.
These are single observations, not a 30-minute capacity claim. Current total
1165/1200 calls, including the original 14 invalidated calls; peak two. Production
behavior is accepted locally, not deployed. Current fresh-shell full gates:
VERIFY-RESULT.md. No new decoder runs were needed for productionization.

### WP28: file album interval scheduling (2026-09-18)

The file resolver's dominant cost was independent ONNX inference, not album
matching, session creation, or audio loading. On the same retained WP19 inputs,
the unchanged resolver took 60.177873 s / 313.204362 s for 3 / 15 windows;
107 / 575 interval probes embedded 391.32 / 2059.98 audio seconds including overlap.
Inference alone took 59.470240 s / 310.204913 s. One session was already reused.

The measured prototype ran four interval probes concurrently through that same
single-thread ONNX session: 17.715150 s / 91.808717 s, complete serialized output
byte-identical on both fixtures. Two workers took 30.714614 s on three windows.
Four perfect-vector controls (1/2 voices over 3/15 windows) were also byte-equal.
Four workers therefore become a file-encoder scheduling choice; live and legacy
encoders remain serial by default. Each call closes its pool before returning or
raising. Interval normalization and averaging retain input order. Album matching,
admission and sweep remain serial and unchanged. Every observation is retained;
`album_admission_seconds` remains eligibility, not a cap on embedding evidence.

This changes wall time, not required acoustic work or identity policy. Measured
four-worker process peak was 1.35 GB. Multi-file capacity and other hosts remain
unmeasured; these repeated public clips establish equality and cost, not a wider
accuracy or deployment claim. Regression includes exact pre-change result oracles
with transcript words replaced by synthetic placeholders. Evidence and command:
`evidence/mvpfix/wp28/`, `prototypes/streaming-diarization/wp28-file-resolver-perf/`.
