# PROTOTYPE NOTES — streaming diarization feasibility (design doc §6)

Throwaway. Delete after verdicts are copied into `docs/design-streaming-diarization.md` §7.
Everything here is excluded from git via `.git/info/exclude` (active Ralph loop must not
see it).

## Questions and verdicts

### Speaker-reference v2 correction packet (`speaker-reference-v2/`)

The former top-level packet now lives under this standing bench. Its independent-ASR acoustic
existence verdict is implemented by production `acoustic_existence_evaluation` and protected by
negative controls; the duplicate one-off scorer was deleted. The retained scripts, notes, and
human-audit record are audit/reproduction material, not a second matcher implementation.

### Gate C — assembly correctness (`proto_c_assembly.py`)
Question: can an append-only per-lane assembler under outbox-retry semantics
(duplicates, reorder, drops, bursts) reconstruct session audio byte-exactly with
silence-filled manifested gaps and checkpoint/resume?

**VERDICT: PASS (2026-07-28).** 7/7 cases byte-exact vs reference, gap manifests match
dropped frames exactly, duplicates/stale idempotently dropped, and crash+resume at 40%
and 70% produced a byte-identical mixed tape (same sha as the uninterrupted run).

### Gate A — album vs overwrite (`proto_ab_identity.py`)
Question: does a quality-gated fingerprint album beat production's latest-span
overwrite, reaching >=90-95% causal live speaker accuracy?

**VERDICT: PASS (2026-07-29).** Best config (min_score 0.35, margin 0.1, admission
1.0 s): live prospective accuracy 96.4-99.5% per meeting, mean 98.5% across
K∈{2,3,4,6}×2 seeds. At the DEPLOYED margin 0.2 with sweeps: 95.7-99.3%, mean 98.4%.
Production's overwrite policy at its own best config: 51.7-87.4%, mean 66.4% —
quantitatively reproducing the sibling project's <80% failure. Album − overwrite ≈
+32 pp mean. Embed cost 332-343 ms/unit (single-thread CPU, production settings) —
fits the 2.5 s span cadence with ~7x headroom.

### Gate B — live→file convergence (`proto_ab_identity.py`)
Question: with retrospective sweeps rewriting history, does the live-vs-file-oracle
accuracy gap converge to ~0 (sibling project diverged), and does sweep cost fit the
35-40x RTF budget?

**VERDICT: PASS (2026-07-29).** The sibling project's signature (gap growing positive
over time) never appears in any of 8 meetings. 6/8: |gap| ≤ ~3 pp throughout. 3
meetings: retro BEATS the whole-file AHC oracle by 30-47 pp — naive offline
average-linkage clustering chain-merges similar voices while the quality-gated online
album holds 95-99%; i.e., live-with-album ≥ naive file mode, inverting the feared
live≪file gap. Sweeps also act as a robustness net: they rescue mis-tuned configs
(e.g. s=0.45 m=0.2: 91.5%→96.9% mean, min 76.7%→94.1%). Sweep cost ~0.1 ms at 600 s
scale (reassign+merge over cached vectors); extrapolated 3 h ≈ <10 ms — negligible vs
the 35-40x budget. Residual: mild ID fragmentation (6-9 canonical vs 2-6 true; extra
births hold ≤~4% of time) — the sweep merge pass plus production UX naming absorbs it.

### Real-audio replay (`proto_real_replay.py` + `proto_sweep_tuning.py`, 2026-07-29)
9 real interview clips (Lex Fridman / Acquired, golden reference.jsonl turns; m4mbp
LiveTranscribe corpora). Aggregate at grid-best (score 0.35, margin 0.1, adm 1.0 s):

- **album+sweep 95.2% mean / 87.4% worst-clip** — beats the whole-file oracle
  (94.5% / 72.7%). Album alone 94.0/85.6. Overwrite 90.6/65.8.
- **3-min clips: 97.5-99.5% everywhere** (incl. the Shapiro/Destiny crosstalk clip,
  99.3%). 1-min clips are the cold-start floor (87.4% worst, 3 speakers in 60 s) —
  consistent with the authorized birth-floor/deferred-labelling amendment.
- **Deployed `min_match_score` 0.5 caps album+sweep at 90.7% mean / 70.7% min on real
  audio** → recalibration toward 0.35 is measured as REQUIRED, not optional.
- **`SWEEP_MERGE_THRESHOLD` 0.70 is safe**: max TRUE cross-speaker centroid sim across
  all 9 clips = 0.259 (same-gender co-hosts included). Enormous margin; merges never
  false-fire.
- Two harness lessons worth keeping: (1) an initial "sweep hurts on real audio"
  finding was a harness bug — no terminal sweep at meeting end; production's
  end-of-session pass is the correct design and the bench now mirrors it. (2) my
  merge-false-positive hypothesis was cleanly falsified by measurement (all variants
  identical) before it could become a steering error. Prototype-first caught both.
- **Q1 birth floor (candidate 55) costs real audio nothing and buys it a speaker
  count** — `proto_real_replay.py`, `simulate(birth_floor=admission)`, 9 golden clips
  at grid-best 0.35/0.1/1.0. Canonical speakers minted **3.56 → 3.00 mean**, worst clip
  **5 → 4**, on clips holding K=2-3 voices; album+sweep accuracy is **95.2 % mean /
  87.4 % worst clip either way, identical on every clip to one decimal**. So the floor
  removes speakers a reader should never have seen without removing a single correct
  label, and the "a 1.0 s floor starves labelling on messy conversational turns" risk
  did not materialise: no clip dropped to zero births and no clip's score fell.
  *Two limits, both running the same way.* (a) This loop only sees units that cleared
  the 0.5 s evidence floor, so the case that dominated production — a local speaker the
  encoder was **never asked about**, 14 of one certification run's 16 canonicals — is
  not representable here; 3.56 → 3.00 is a **lower bound**. (b) These clips are 60-180 s
  and never approach the 16-speaker cap, so none of the *accuracy* gain that saturation
  costs a long meeting can appear. On the 600 s LibriSpeech meetings, where capacity
  does saturate, the same fix moves live accuracy **93.4 % → 99.1 %** and canonical
  count **16 → 4.00** (`tests/test_live_identity_accuracy.py`, production objects).
  Residual over-birth survives on 4 of 9 clips (4 canonicals for 3 voices, 3 for 2), so
  the floor bounds the unenrollable births, not all of them.

### Updated regression fixture `youtube_rtfl_first_90s` (`proto_fixture_90s.py`, 2026-07-29)
Operator flagged the golden was updated on m4mbp at 10:53; fetched AFTER that update.
(The two main corpora were md5-verified identical local-vs-remote — no stale goldens.)
Hardest clip in the collection: K=4 in 90 s including a single-appearance speaker,
decisecond boundaries, 2.4 s of sub-floor micro-turns. Results:

- grid-best: overwrite 57.6 / album 92.4 / **album+sweep 93.7** — beats the whole-file
  oracle (87.6) by +6.1 pp. Deployed score 0.5 caps at 81.2 even with sweep.
- birth floor 1.0 s: minted speakers 7 → 5 (true 4), accuracy unchanged at 93.7% —
  consistent with the Q1 finding.
- Kept OUT of the 9-clip binding aggregate (95.2%) deliberately; reported standalone.

### Library extension: 5 m + 30 m tiers (`proto_corpus_5m30m.py`, 2026-07-29)
8×5-min + 2×30-min real cases from the full benchmark corpus (goldens aligned from the
shows' own timestamped transcripts; m4mbp source of truth). Standalone — binding 9-clip
aggregate unchanged.

- **30 m (the production-shaped horizon): album+sweep 94.7-96.4% at deployed-margin
  (mean 95.5), 92.9-94.7 at grid-best.** Overwrite collapses to 37-62% at 30 m —
  duration amplifies the overwrite disease, exactly as the 600 s synthetic predicted.
  Total sweep compute for a 30-min session: 2.4-6.4 ms (≈30 sweeps). Trajectories are
  stable/recovering, no divergence; gap to a strong offline oracle ≈2.5 pp.
- **New hard class found: same-gender co-host pairs (Acquired's Ben+David).** On
  acquired_alphabet 5 m even the whole-file oracle scores 59.4% — an
  embedding-separability ceiling, not a policy failure; album+sweep beats the oracle by
  +29 pp (88.6) there. 5 m aggregate: swp 91.4 mean / 86.3 min (grid-best).
- **Margin tradeoff is duration-dependent**: margin 0.2 wins at 30 m (95.5 vs 93.8) but
  pre-sweep album craters to 10.8% on the similar-voice clip (abstain starvation;
  sweep rescues to 60.3). Grid-best margin 0.1 is the safer worst-case. Threshold
  decisions should stay measured-per-change; consider duration-adaptive margin (fog).
- **Production mitigations for the hard class, in priority order**: (1) lane provenance
  — in real usage the "similar pair" is usually local-mic vs remote-system, which the
  two-lane design separates structurally before embeddings are even consulted
  (dual_lane_diarization corpus exists on m4mbp for validating this); (2) larger
  embedder A/B (resnet293-LM sits in the local HF cache) — fog.

### Retained live-tape differential (`proto_tape_differential.py`, 2026-08-02)

Question: why does exact `c2e6248` score 91.35% on the clean 5-minute Acquired
corpus but 55.07% through the live Mac→server path?

**VERDICT: ROOT CAUSE PROVED.** The retained system lane itself scores 61.61% with
truth-derived intervals; the mixed lane scores 54.66%, so the failure precedes live
ASR/span policy. Clean speaker-centroid cosine is 0.261; after system capture it
collapses to 0.911. `NativeLaneWireStream.downmix` assumes channel-major samples,
but `copyFromAudioBufferList` flattens a multi-channel `AudioBuffer` without
deinterleaving it. A 512-frame interleaved-stereo simulation matches the retained
spectrum at 0.941 correlation (centroid 401 Hz vs 396 Hz observed). Holding corpus,
truth intervals, pinned encoder, and thresholds fixed, only correcting channel indexing
produced **62.36% RED → 91.35% GREEN → 62.36% RED**. Mic bleed is negligible;
system→mixed waveform correlation is 0.979.

Smallest fix: normalize every `AudioBuffer` to channel-major samples while its
`mNumberChannels` layout is still known, before constructing
`NativeCapturedAudioBuffer`; preserve the existing downstream downmix contract. Add
interleaved-stereo, planar-stereo, and resample-through-frame-assembler regressions.
F4b remains **OPEN** until a new retained live run on the fixed app clears its gate.

## Fidelity notes
- Embedder: PRODUCTION class `_OnnxWeSpeakerEmbedder` via `WeSpeakerResNet152LmAdapter`,
  loaded from the repo file, with the pinned ONNX (sha verified = spec.state_sha256).
- Live semantics mirrored: 2.5 s span cap (mid-utterance cuts), 0.6 s silence split,
  0.5 s min evidence, per-span local→canonical one-to-one matching with
  score/margin gates, abstain-on-ambiguity, birth on low score, 16-speaker cap.
- Deployed anchors: margin 0.2 (live runtime), tier_b_similarity 0.70 / margin 0.20
  (batch defaults) — grid brackets these.
- Data: synthetic meetings from LibriSpeech dev-clean (K∈{2,3,4,6}, 2 seeds, 600 s,
  30% short backchannel turns, fast turn-taking pauses so multi-speaker spans occur).

## Known limitations (carry into design doc §8 if verdicts pass)
- No overlapped speech (LibriSpeech is single-speaker read speech); no noise/reverb.
  Real conversational recording replay is a follow-up before production sign-off.
- In-span local diarization assumed correct (isolates the identity layer — MOSS's
  in-span quality is a separate, already-shipped component).
- Sweep here reassigns evidence units + merges close canonicals; production sweep adds
  re-VAD of the tape (more evidence, should only help).

### L2 Stage 0 A0 guardrail boundary (`scripts/ralph-l2-afk`, 2026-08-03)

Question: can Campaign A start from an isolated keeper worktree with a fail-closed
corpus gate, strict path/iteration fences, single-writer ownership, and terminal
promise handling before any A1 corpus work?

Command: `scripts/ralph-l2-afk/launch.sh --dry-run --evidence-dir scripts/ralph-l2-afk/evidence`

**VERDICT: PASS (21/21).** Campaign-A paths are accepted; product Python, macOS,
ops, product tests, and unlisted paths are refused. Iteration 10 is accepted and 11
is refused. Dirty trees, unexpected HEAD, corpus-hash drift, and a second writer are
refused. With the literal `UNFROZEN` pin, an actual gated iteration exits 2 with
`corpus_manifest_unfrozen` and `<promise>BLOCKED</promise>`.

Raw evidence:

- `scripts/ralph-l2-afk/evidence/a0-dry-run.json` — SHA-256
  `cf5a3401fbd5f8ee83a60889e7eafae8ee50cc62fcbba692003c2ea7a3991bc6`.
- `scripts/ralph-l2-afk/evidence/a0-dry-run-transcript.txt` — SHA-256
  `b8224da1e840eabc039e1d2a5767624dd4583ded62346c70612cbf2bec9e870e`.
- `scripts/ralph-l2-afk/evidence/A0_EVIDENCE.sha256` — SHA-256
  `ab5b196d14c55bb4c93e087143eae81f06b9d876018ba8212cff049f8580487c`.

Execution note: immediately after creating the isolated worktree, the first plan
cherry-pick mistakenly ran in the dirty main checkout because the command retained
that checkout as its working directory. It created commit `4c0d8ca`, touching only
the plan file. The branch was restored with `git reset --mixed ce6154cb...`; only
the newly added plan file was deleted. The main checkout's prior HEAD and complete
dirty status were then rechecked and matched the preflight exactly. The cherry-pick
was rerun correctly in the isolated worktree as `42a992a`. No main-checkout change
from A0 survives.

### L2 Stage 0 A1 frozen-input boundary (`l2-stage0`, 2026-08-03)

Question: can Campaign A freeze a leakage-resistant bench corpus and model boundary,
with deletion-capable long-case validation, an unopened blind holdout, and an exact
launcher corpus pin, without changing any unapproved reference truth?

Command: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/validate_inputs.py --json-output prototypes/streaming-diarization/l2-stage0/evidence/a1-validation.json`

**VERDICT: PASS.** The accepted corpus contains 2 development, 4 validation, and
3 blind-holdout cases; 10 cases remain explicitly exploratory. The only accepted
long case is `5m-acquired-alphabet`, using post-audit reference SHA-256
`28dc9a5b80098db58a261b4bfa73e2975acac31ef36e7e8f057c514d8bdc0759`
and deletion-capable acoustic evidence. No other reference was edited. The launcher
pin and corpus-manifest SHA-256 are both
`b612a45e05d44a3904559d02fd0a435bc1fbdef09e832a6664122a4616d672d3`.
The candidate config exposes only the holdout-manifest hash and refuses an early
open with `holdout_open_before_candidate_freeze` and `<promise>BLOCKED</promise>`.

Red-first proof: 5 tests produced 7 expected failures before implementation,
covering audio/reference/model byte mutation, transcript-only acoustic evidence,
runtime golden-path leakage, and pre-freeze holdout access. Green boundary proof:
5/5 passed. The alphabet reference/cache rebuild pair is recorded in
`evidence/vector-rebuild.json`.

Raw evidence:

- `prototypes/streaming-diarization/l2-stage0/evidence/a1-validation.json` — SHA-256
  `9068c875702a3b524fc5dd5bd549ab38c44361d3f65d2bb0748a78fb669d24a5`.
- `scripts/ralph-l2-afk/evidence/a1-red-first-transcript.txt` — SHA-256
  `09c16a81b2c131125a5062df431cd9e36704489a12e1fc0d01dc34d58c4c622b`.
- `scripts/ralph-l2-afk/evidence/a1-green-boundaries-transcript.txt` — SHA-256
  `90e29b7380b60eeb2e3a9736df18f579ccf8e68e8ceff84aa1877c7ce8f3116e`.
- `prototypes/streaming-diarization/l2-stage0/evidence/vector-rebuild.json` — SHA-256
  `50590a9c9863776e9900908c6abae68cc3a314b237afead379a668711a507ceb`.
- `prototypes/streaming-diarization/l2-stage0/evidence/a1-holdout-refusal-transcript.txt`
  — SHA-256 `a40a44dcc9ca289c46bebfe8d15d0ef1a2bef0d438c8f520a12a3d23bc8b3c21`.
- `prototypes/streaming-diarization/l2-stage0/evidence/A1_EVIDENCE.sha256` — SHA-256
  `5112f4ab5a9ec4f07f0408d53f3313fecbd8fc52484cec651f631224c7b644fe`.

Reference-truth questions for later operator authorization are consolidated in
`prototypes/streaming-diarization/l2-stage0/operator-questions-A1.md`; none blocks
A1 because every affected case is excluded from acceptance.

Commit-granularity deviation: the supervisor authorized A1 as its own atomic commit
before A2, refining plan §5 commit 2 so the long-running L1 reproduction consumes a
clean, hash-pinned manifest commit; A2 will land separately.

### L2 Stage 0 A2 predeclaration (`l2-stage0`, 2026-08-03)

Before any L1 measurement, A2 is restricted to the six accepted development/validation
cases in `l1-control-spec.json`, with two runs per case and exact semantic repeatability
(zero metric tolerance). The corrected-alphabet speaker-accuracy target is 0.9135 with
an absolute 0.001 band, predeclared from the two accepted unchanged-path results.

The supervisor intentionally overrode A2's literal “every accepted case” wording to keep
all three blind-holdout cases sealed. `a5-holdout-procedure.json` predeclares that the
single A5 opening occurs only after candidate freeze and runs all three arms—L1 control,
ledger-only control, and the frozen L2 candidate—in the same opening session. L1 runs
twice per holdout case; no tuning follows the opening.

### L2 Stage 0 A2 L1 reproduction verdict (`l2-stage0`, 2026-08-03)

Command: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/run_l1_control.py --evidence-dir prototypes/streaming-diarization/l2-stage0/evidence/a2-l1-runs --json-output prototypes/streaming-diarization/l2-stage0/evidence/a2-l1-summary.json --transcript-output prototypes/streaming-diarization/l2-stage0/evidence/a2-l1-transcript.txt`

**VERDICT: BLOCKED.** The first gated case, `1m-acquired-nfl`, failed the
predeclared production-fixture fidelity gate: the frozen reference replans to 26
evidence units while the frozen vector cache contains 29. The runner exited 2 with
`l1_fixture_unit_count_mismatch`. No alternate span constant, threshold, cache, arm,
or case was tried; no determinism or accepted-alphabet score is claimed.

The A2 red check proves `run_l1_control.py` refuses a blind-holdout case before
reading its case files with `l1_holdout_before_candidate_freeze` and
`<promise>BLOCKED</promise>`. All three holdout cases remain sealed for the single A5
opening predeclared above.

Raw evidence:

- `prototypes/streaming-diarization/l2-stage0/evidence/a2-l1-summary.json` — SHA-256
  `c637fffa161548ad8fbe5c426e06d3578ffe6e2952b44ca96114bffb68566cac`.
- `prototypes/streaming-diarization/l2-stage0/evidence/a2-l1-transcript.txt` — SHA-256
  `e0fd362bc1a1d4f30022f390d4896258f8a9b15e38b9400b8dc701a6c17d44a4`.
- `scripts/ralph-l2-afk/evidence/a2-red-holdout-transcript.txt` — SHA-256
  `e4303438fa4c6f7bba07e4935f03bcfd037fa5804413812a7d83fcdd75c854a1`.
- `scripts/ralph-l2-afk/evidence/a2-green-tests-transcript.txt` — SHA-256
  `93d4c64ebd44675a5ea172b2e6da5cb4b89fe6f869321ec3b179209cf28bb6cf`.
- `prototypes/streaming-diarization/l2-stage0/evidence/A2_EVIDENCE.sha256` — SHA-256
  `e0747b97ec5750ed5b78f13114668c3a8668685c732f4cdb5448b5768543da14`.
