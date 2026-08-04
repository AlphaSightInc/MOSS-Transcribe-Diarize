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

### L2 Stage 0 A1.2 derived-cache remediation authorization (`l2-stage0`, 2026-08-03)

The supervisor classified the A2 `l1_fixture_unit_count_mismatch` as an A1.2
input-fidelity failure: stale derived caches against frozen reference hashes and the
current production span planner. It is not a candidate-arm gate failure and does not
authorize threshold or reference-truth changes. The blocked A2 evidence above remains
the immutable superseded attempt.

Authorized remediation is derived-data-only and versioned: audit/rebuild development,
validation, and exploratory caches through production `EndpointPolicy` and
`WeSpeakerResNet152LmAdapter`; never overwrite source bench caches. Audio/reference truth
remains byte-identical. Blind-holdout references/caches remain unopened. Their identical
rebuild path is pinned into `a5-holdout-procedure.json` and may run only inside the single
A5 opening, after candidate freeze and before all three arms.

Command: `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/rebuild_caches.py --scope non-holdout --apply-manifest --audit-output prototypes/streaming-diarization/l2-stage0/evidence/a12-cache-provenance-audit.json --transcript-output prototypes/streaming-diarization/l2-stage0/evidence/a12-cache-rebuild-transcript.txt`

**VERDICT: PASS.** All 16 non-holdout cases rebuilt under
`cache-v2-production-endpoint`; all 16 caches match their own exact production
`EndpointPolicy` replan. Unit-count deltas range from 0 to +105 and are fully recorded
per case with old/new hashes. Frozen audio/reference hashes did not change. The scoped
A1 validator passed 16/16, explicitly reporting `holdout_case_files_opened=false` and
the three sealed case ids. The A5 procedure is re-pinned at SHA-256
`3d745f92d941985d95c7351caf3c430b2f43209cbb4bb7c20f716bc73d1b3464`;
it requires the same hash-pinned rebuild script/module before all three arms inside the
single opening.

One green-suite attempt correctly failed its source-path audit because the editable
environment resolved production `live_endpoint.py` from the main checkout. That raw
failure is preserved under label `a12-renewed-green`. Repo-root import precedence was
then asserted; labels `a12-renewed-green-fixed` and `a12-renewed-green-final` passed
11/11. This changed no production, input, cache, or threshold behavior.

Raw evidence:

- `prototypes/streaming-diarization/l2-stage0/evidence/a12-cache-provenance-audit.json`
  — SHA-256 `05f3249e1d8b5472f73a2e1158884032c425a44223a503bf61bc4bb938054ab3`.
- `prototypes/streaming-diarization/l2-stage0/evidence/a12-cache-rebuild-transcript.txt`
  — SHA-256 `b73217d3d1b7d8594138d57065ebb4d639a93212b3b9e1b11956287f97e0911e`.
- `prototypes/streaming-diarization/l2-stage0/evidence/a12-renewed-a1-validation-final.json`
  — SHA-256 `edf75b145f015e7fd490d5ef2d7dcec162e6f34ed25f211e8a1db99d35d62472`.
- `prototypes/streaming-diarization/l2-stage0/evidence/a1-a12-renewed-green-final-transcript.txt`
  — SHA-256 `9b86b5ce72d94b289a548a3955206178820070b1752ad457f96bfebf5db857fd`.
- `prototypes/streaming-diarization/l2-stage0/evidence/a12-red-holdout-cache-rebuild-transcript.txt`
  — SHA-256 `10b95e7bca08a0aa37b276ffd91fe9aa5b5ccde4e3439eb3c0afd39cc306ef7a`.
- `prototypes/streaming-diarization/l2-stage0/evidence/A12_EVIDENCE.sha256`
  — SHA-256 `40ec1acf8d49146c10d4c4d2f6ee897bbc7d42a6b57edc3df2caf6dd4ab9bce4`.

### L2 Stage 0 renewed-A2 runner-path correction (`l2-stage0`, 2026-08-03)

The first renewed-A2 invocation wrote the first `1m-acquired-nfl` run JSON, then
raised before recording any metric or gate verdict because a relative evidence path was
passed to `Path.relative_to()` against the absolute worktree. The partial JSON and
launcher-PTY traceback are preserved under `evidence/a2-l1-renewed-runs/` and
`evidence/a2-renewed-path-crash*`; this attempt is `NO_VERDICT`.

Correction: resolve all relative output paths beneath the asserted worktree before the
measurement loop. No input, production policy, cache, threshold, score, or holdout state
changed. Renewed A2 will use new `a2-l1-renewed-fixed*` paths; no evidence is overwritten.
`evidence/A2_PATH_FIX_EVIDENCE.sha256` seals 7/7 files and has SHA-256
`0135dc06705ee3c66a1bbe48844cd4c0ffbf482fc13b0126ea8f31021e00c476`.

### L2 Stage 0 renewed A2 L1 reproduction verdict (`l2-stage0`, 2026-08-03)

Command: `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/run_l1_control.py --evidence-dir prototypes/streaming-diarization/l2-stage0/evidence/a2-l1-renewed-fixed-runs --json-output prototypes/streaming-diarization/l2-stage0/evidence/a2-l1-renewed-fixed-summary.json --transcript-output prototypes/streaming-diarization/l2-stage0/evidence/a2-l1-renewed-fixed-transcript.txt`

**VERDICT: BLOCKED.** All six development/validation cases ran twice and matched
semantic SHA-256 exactly. The corrected acquired-alphabet score was 0.916765 versus
the frozen 0.913500 target: absolute delta 0.003265 exceeded the predeclared 0.001000
band, failing `l1_accepted_alphabet_band_failed`. The campaign stops here under plan
§6. No retry, tuning, threshold change, alternate arm, or holdout opening occurred.

Raw summary SHA-256:
`fa10723978db7828622f5ef2c590a4a9ea1616fa74ce1d55c730387007733dee`.
Raw transcript SHA-256:
`9f7828a2886efd3447c9c04806298397f0871c181c358749ca7c03f70d6237b3`.
`evidence/A2_RENEWED_EVIDENCE.sha256` seals 30/30 files and has SHA-256
`9839f3fb65d9f0642e9e31ddd050c9cd100b7bdb58251ea4d66146e241b7a5e4`.

### L2 Stage 0 accepted-anchor fidelity diagnosis (`l2-stage0`, 2026-08-03)

Command: `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/run_anchor_fidelity.py --output-dir prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity`

**VERDICT: BLOCKED — no anchor score produced.** The probe hash-asserted the exact
c650-era runner (`8719c18…`) and exact archived 92-unit alphabet cache
(`fd13bacb…`), while leaving official corpus/spec/launcher pins unchanged. The runner
exited 1 before run 1: the archived NPZ contains `rows`, `vec_idx`, and `vecs`, but
current `validate_cache()` requires `span_bounds` and `span_reasons`; NumPy raised
`KeyError: 'span_bounds is not a file in the archive'`. No summary, score, or run JSON
was created.

This is instrument incompatibility, not evidence for the partition-effect hypothesis.
Per supervisor instruction: no second run, causal decomposition, dual-anchor record,
gate clarification, tolerance change, cache modification, planner variation, or re-pin.
Holdout remains sealed; A3 remains unstarted.
`evidence/ANCHOR_FIDELITY_EVIDENCE.sha256` seals 12/12 files and has SHA-256
`ff76c726bd9642bdd14e253932ab13c1416ecb5dd6803d5ad40ce0888436d3c6`.

### L2 Stage 0 legacy-ingest anchor diagnosis verdict (`l2-stage0`, 2026-08-03)

Command: `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/run_legacy_anchor_fidelity.py --output-dir prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/legacy-measurement-v2`

**VERDICT: BLOCKED.** Before measurement, the diagnosis audit proved that
`planned_span.reason` is used only to populate `FrozenSpan.reason` and traces, while
the downstream preparation/provider/scorer path has zero `span.reason` reads. A tiny
synthetic case produced identical scores, labels, and revisions with a real reason and
`legacy_unavailable`. Red-first tests proved named refusal for corrupt/truncated
archives, missing archive/row fields, and non-monotonic row bounds.

The first adapter invocation (`legacy-measurement-v1`) produced no score: official
fixture fidelity caught a one-sample duration reconstruction difference at unit 77.
That no-score evidence remains preserved. The adapter was corrected to reconcile
sample-aligned pieces to the archived row duration; no tolerance, planner setting,
cache, reference, official runner, or pin changed. The dedicated red/green regression
and the reason-independence audit then passed again.

The corrected adapter ran the archived 92-unit cache twice. Both scoring projections
were byte-semantically identical (`a6a64040…`) and both scored `0.954974`. The immutable
accepted anchor is `0.913500 ± 0.001000`; absolute delta `0.041474` fails
`legacy_anchor_band_failed`. Archived cache SHA-256 was
`fd13bacb3ee8397354c0ae55a8b9534db9df56b13dce73c0b956d7cdf3947be5`
before and after. Therefore partition effect is **not proved**. No causal decomposition,
dual-anchor record, gate clarification, anchor move, A2-completion commit, or A3 work
was performed.

Raw evidence:

- `evidence/anchor-fidelity/span-reason-independence-audit-post-duration.json` —
  SHA-256 `fc0eadfa2585cde9e549bd55c05b79b59018050889f64e7ca76b9a075301016c`.
- `evidence/anchor-fidelity/legacy-red-validation-transcript.txt` — SHA-256
  `b2cb4a811c45fb16ec0f089025c6dba87abe1b76fc2b06dec1bbfda15d0e2779`.
- `evidence/anchor-fidelity/legacy-red-duration-transcript.txt` — SHA-256
  `f47bcce82d5853df2f37eb51843e96922242bd966d11ffb83594ba010608272d`.
- `evidence/anchor-fidelity/legacy-green-post-duration-transcript.txt` — SHA-256
  `839051b6aeb0599c8c80d131a4efa488cecf09c3048cee022b504df3010709d2`.
- `evidence/anchor-fidelity/legacy-measurement-v1/failure.json` — SHA-256
  `c5616475bb140f86b3995181d5447141567a4c92fb3b88a6ebdc59952353d644`.
- `evidence/anchor-fidelity/legacy-measurement-v2/summary.json` — SHA-256
  `f095bdf3f608a1e5e6dffacd8dbc0dfdf3f08b73d59ff56ed9905af05ff093f0`.
- `evidence/anchor-fidelity/legacy-measurement-v2/measurement-transcript.txt` —
  SHA-256 `172d56da70fbc8d51424195bbf3ac1618e4883521e62ba1a77cebb7573e2f2da`.
- `evidence/anchor-fidelity/legacy-measurement-v2/LEGACY_MEASUREMENT_EVIDENCE.sha256`
  — SHA-256 `58b12ce154e679bd54280d909a66a75237777e3c9d672747642c9bc935e60e69`.
- `evidence/anchor-fidelity/a12-owning-commit-verification.txt` — SHA-256
  `8adaf14810a061f75efaedea11ed1207c30d07ee7ad0d5c8cfa6e5b795d7ea52`.

### L2 Stage 0 instrument fidelity H1 — scorer definition (`l2-stage0`, 2026-08-03)

Command: `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/h1_rescore_sealed_labels.py --output-dir prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/h1-scorer-v1`

**VERDICT: H1 REFUTED.** Without replaying identity or sweep policy, the exact 92
sealed final labels from legacy-measurement-v2 were converted back into their 93
hypothesis intervals and passed directly to production
`score_live_speaker_accuracy()` (`live_speaker_accuracy.py:148`). The result exactly
matched every sealed metric, including speaker accuracy `0.954974`, two-sided mapping,
and per-speaker correctness. It did not reproduce immutable `0.913500 ± 0.001000`
(delta `0.041474`), so scorer definition is not the divergent stage. Proceed to H2.

Raw result SHA-256: `a6aadd07f1db4f6d125481fd0e6b6a2518e1496d1cb4783b11b5a6a90cc7c3a5`.
Raw transcript SHA-256: `502972f0df7735abf30c97386d4797e615eadc3bc8d2eddae088798c72221d88`.
`H1_SCORER_EVIDENCE.sha256` seals 8/8 files and has SHA-256
`c024dbb7b43128c7068f58b4bdd95625d6b1a2517c223e64a4d1fc9ad8024e54`.

### L2 Stage 0 instrument fidelity H2 — identity constants (`l2-stage0`, 2026-08-03)

Command: `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/h2_compare_constants.py --output-dir prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/h2-constants-v1`

**VERDICT: H2 REFUTED.** The runner and deployed keeper contract match side by
side for score `0.35`, margin `0.1`, album admission `2.0`, birth floor `1.0`,
hard cap `40000`, and max speakers `16`. Production `hash_config()` over the
runner identity payload reproduced deployed `identity_config_hash`
`4b7c94eddf0d566bd7870ce7fbe6464d3a5f75d80371c0eb4dd36fb64fec9b89`.
The deployed source revision also matches keeper `9089b33210401111865da7abc160ab0bcb4aa266`.
No identity-constant divergence exists; proceed to H3.

Raw result SHA-256: `578db1b03b6c8bf6418132fd538b54eb6b1212f7d28761cb76b90eeac5371940`.
Raw transcript SHA-256: `bb93e693028098784ad9fee3795f3c33a5d5c09d0dfb7e2f1df49882c1b84a23`.
`H2_CONSTANTS_EVIDENCE.sha256` seals 8/8 files and has SHA-256
`99d202f62bc7bc0e53273f5ec5ad014057d1f5acf9d872f7d7094e2e0fd9b663`.

### L2 Stage 0 instrument fidelity H3 — first causal divergence (`l2-stage0`, 2026-08-03)

Commands:

1. `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/h3_compare_policy.py --output-dir prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/h3-policy-v1`
2. `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/h3_explain_first_divergence.py --output-dir prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/h3-first-divergence-v1`

**VERDICT: DIVERGENT STAGE IDENTIFIED; HARD STOP BEFORE H4.** The raw H3 comparison's
coarse verdict named the H3 policy bucket, but the sealed causal follow-up narrows the
first difference to **pre-assignment legacy transcript ingest**, not score/margin,
abstention, birth, or sweep policy. On exact archived unit 23/span 19, the existing
live-policy mirror assigns canonical 0 (best `0.353387770`, runner-up `0.173633452`,
no abstain). The renewed runner instead returns `failed/unparseable_transcript` before
evidence scoring.

Cause: legacy duration reconciliation moves the piece start back one sample
(`legacy_ingest.py:170-199`) but leaves the enclosing span start at the archived-row
rounded bound (`legacy_ingest.py:214-223`). Runner rendering
(`run_l1_control.py:350-373`) therefore emits
`[-0.000062][S01]w[0.580312]`. Production parsing returns zero segments
(`live_span_bounds.py:37-54`), and the preparer fails before assignment
(`live_identity.py:101-106`). This is the first per-unit divergence. No official
runner, adapter, cache, pin, tolerance, or anchor changed; H4 was not run.

The existing mirror over the same 92 archived rows returns `1.000000000` live and
final unit-weighted accuracy with two canonicals, while the sealed renewed runner
returns `0.954974`; therefore this H3 run also does not reproduce immutable `0.913500`.
Anchor-fidelity diagnosis remains BLOCKED pending supervisor ruling.

Raw H3 comparison SHA-256: `f28a1bfb3248210f2502600e3ae5bb4ef0abbc45d430740ed94f52338acaa017`.
Raw H3 comparison transcript SHA-256: `ea0744b6bbfa4173deb26d2adeef4e31e32986aa5bfeb6de8e4bcabaff65ab8b`.
`H3_POLICY_EVIDENCE.sha256` has SHA-256
`a4619fcb555e1b5475da7252a2982a76c6a2f83c93ff47356a8e9b55dad19d1f`.
Raw causal result SHA-256: `8f46fbe9c5fc0e96f7c8d41a24732e890f3a3683843445f327f569d6d71f1920`.
Raw causal transcript SHA-256: `260c22d4593f6b7e0564a0004881566530a51598cee3c484a5118cb53a008957`.
`H3_FIRST_DIVERGENCE_EVIDENCE.sha256` has SHA-256
`d128449f277d2c340ae8390cfa61c9c11f495a21b5b559a09a9b92011a41a866`.

### L2 Stage 0 legacy-ingest adapter v3 verdict (`l2-stage0`, 2026-08-03)

Commands, in order:

1. `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/quantify_v2_contamination.py --output-dir prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/v2-contamination-v2`
2. `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/run_legacy_ingest_tests.py --test test_legacy_ingest.LegacyIngestTest.test_archived_unit_23_span_19_parses_and_reaches_assignment --transcript-output prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/adapter-v3-red/unit23-transcript.txt --json-output prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/adapter-v3-red/unit23.json`
3. `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/run_legacy_ingest_tests.py --test test_legacy_ingest.LegacyIngestTest.test_all_92_archived_units_render_into_parseable_preparations --transcript-output prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/adapter-v3-red/all92-transcript.txt --json-output prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/adapter-v3-red/all92.json`
4. Repeat commands 2-3 with output directory `adapter-v3-green-v2`, then run the full `test_legacy_ingest.LegacyIngestTest` class and `test_span_reason_placeholder_is_score_independent` through the same test runner.
5. `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/run_legacy_measurement_v3.py --audit-output prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/adapter-v3-green-v2/span-reason-audit-v3.json --output-dir prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/legacy-measurement-v3`

The sealed v2 quantification found three failed spans (`19`, `26`, `61`) and five
affected units: `23` (0.580375 reference seconds), `31` (1.261875), `32`
(1.040125), `72` (2.1596875), and `73` (0.3403125), total 5.382375 seconds.
Every unit had null live/final labels, zero hypothesis intervals, and zero ledger
records; four were otherwise embedding-eligible. Named mechanism:
`pre_assignment_censoring_as_null_hypothesis`. Reference time remained in the score
denominator as missed time, so omission itself supplied no direct scalar inflation;
the contamination was censorship of the policy decisions under test. The first
quantifier invocation failed on a diagnosis-only report-field typo; its raw failure
remains sealed before the corrected output.

Red-first reproduced unit 23/span 19 as `failed/unparseable_transcript` and found the
same property failure on units 23, 31, 32, 72, and 73. The authorized adapter change
now derives each diagnosis span bound from its reconciled piece minimum/maximum, so
no rendered piece starts outside `[0, span_duration]`. The first green attempt, which
reconciled only on the end side, correctly stopped at unit 83 with named
`legacy_unit_reference_mismatch`; preserved. Final exact-unit, all-92 property,
reason-independence, and full adapter suite passed (8/8; zero
`unparseable_transcript`). Official runner, production files, archive, pins,
tolerances, and anchor remained unchanged.

**VERDICT: BLOCKED.** Legacy-measurement-v3 byte-verified archived cache
`fd13bacb3ee8397354c0ae55a8b9534db9df56b13dce73c0b956d7cdf3947be5`
before and after. Two runs were deterministic: both speaker accuracy `0.983449`,
both scoring-projection SHA-256
`26beda58f5e690a6ff3c37d28f5b33e163ba2084e9f1271bbfbb55744f6fee47`.
Absolute delta from immutable `0.913500` was `0.069949`, outside `±0.001000`;
`legacy_anchor_band_failed`. Runner-policy divergence is back in play. Per ruling,
H4/deeper diffing, decomposition, dual anchors, gate clarification, A2 completion,
and A3 were not run.

Raw evidence:

- `instrument-fidelity/v2-contamination-v1/V2_CONTAMINATION_FAILURE_EVIDENCE.sha256` — SHA-256 `c42eb22652d617ad84b6e3486b19953e7025443371f6fb0e03d9c500bf850a47`.
- `instrument-fidelity/v2-contamination-v2/V2_CONTAMINATION_EVIDENCE.sha256` — SHA-256 `bcc667941906a847fd2d030fac3bb3416268486c0f5d569438404bc22a1f6ba6`.
- `instrument-fidelity/adapter-v3-red/ADAPTER_V3_RED_EVIDENCE.sha256` — SHA-256 `74bee1d413b1edcdbf96e52956a29b6b2be93812a206faa8b841c4e41ad14884`.
- `instrument-fidelity/adapter-v3-green/ADAPTER_V3_GREEN_ATTEMPT1_FAILURE.sha256` — SHA-256 `da7862989131d4106b4d7638b77751b59c593d86e75160abe6992f21e1057a6b`.
- `instrument-fidelity/adapter-v3-green-v2/ADAPTER_V3_GREEN_EVIDENCE.sha256` — SHA-256 `a52ea7f7d5a71ee0d0bf62a90eb3a9f1e63c2f20420184d53171f873531b914a`.
- `legacy-measurement-v3/LEGACY_MEASUREMENT_EVIDENCE.sha256` — SHA-256 `cdfc86d75527d998b1225c453a834b2eed4bb45c6a899745c308116f1b04920a`.
- `legacy-measurement-v3/v3-wrapper-result.json` — SHA-256 `15f149260d0423402c09b9c85fd90d0dfdf7978c356fe9018a398568f2babb77`.

The source hashes referenced by accepted H1-H3 historical manifests now differ only
because of this supervisor-authorized adapter/test correction. The old-to-new hashes
and unchanged-boundary assertions are sealed in
`instrument-fidelity/authorized-source-drift-v3.json`.

Command-record erratum: the exact separately rerun reason-independence method in
command 4 was
`test_legacy_ingest.LegacyIngestTest.test_span_reason_placeholder_does_not_change_score`;
the earlier `test_span_reason_placeholder_is_score_independent` wording was a NOTES
transcription error only. `adapter-v3-green-v2/reason-transcript.txt` preserves the
exact successful command.

### L2 Stage 0 original-vs-renewed causal-policy diagnosis (`l2-stage0`, 2026-08-03)

**Production bindings.** `run_l1_control.py` does not reimplement preparation or
assignment. It imports `BoundedCausalIdentityPreparer`, `FingerprintAlbum`, and
`WeSpeakerLiveEvidenceProvider` at lines 21-40; constructs them at 246-265; and calls
`preparer.prepare(..., base_snapshot=snapshot)` at 361-375. Production preparation is
`moss_transcribe_diarize/app/live_identity.py:89-166`; line 123 calls the production
matcher through `_assign` at 229-240 and `assign_speakers` at 297-355. The runner's
379-388 only decodes returned diagnostics into evidence arrays. Provider scoring at
`live_provider_bundle.py:567-631` reconciles the previously committed span at line 575,
then scores only the canonical speakers in the current base snapshot. Prior assignments
reach the album through 726-765. No renewed assignment-policy copy exists.

The first unchanged-source invocation disclosed that the dirty main checkout's local
alphabet cache is a different 55-row artifact (SHA-256 `327f3328…aa68a`), not the
authorized 92-row archive. That output is preserved as wrong-input, non-acceptance
evidence. The unchanged source instrument was then invoked against the exact archived
cache SHA-256 `fd13bacb…47be5` with policy `album`, sweep enabled, score `0.35`,
margin `0.1`, admission `2.0`, birth floor `1.0`, merge `0.7`, sweep cadence `60.0s`,
speaker cap `16`, sticky delta `0.0`, and keep-uncertain false. Source
`proto_ab_identity.py` remained byte-identical at SHA-256 `e4e8305c…1791`.

**VERDICT: EXPECTED ORIGINAL ANCHOR NOT REPRODUCED; WORKING HINDSIGHT HYPOTHESIS
REFUTED; STOP.** The unmodified original returned live and final accuracy
`0.9999999999999999`, not `0.9135`. Per-unit normalization
`0→speaker-0001`, `1→speaker-0002`, `-1→null` produced zero live mismatches and zero
final mismatches across all 92 rows (83 eligible, 9 ineligible). There is therefore no
first divergent unit and no divergent album state to report. At the first joint album
checkpoint, unit 2/span 1, both see exactly one prior enrolled identity from unit 0 and
both birth the second identity. Original live equals final; renewed live equals final;
renewed changed-duration fraction is zero and all sweep correction lists are empty.
No final-album hindsight affected either result.

The numeric bridge is scoring scope, not policy: original `accuracy()` defaults to
eligible rows only (`proto_ab_identity.py:351-355`) and scores `1.0`; asking that same
unchanged scorer to include all rows scores `0.9833507161`. Production reference-time
scoring gives renewed `0.983449` with `174.141506s` matched, `2.930806s` missed, and
zero confused seconds. Neither path approaches immutable `0.9135` on these inputs.
The premise required to name a renewed policy line is absent. No fix, H4, anchor change,
A2 completion, or A3 work was performed.

Commands:

1. From source bench `prototypes/streaming-diarization`, run Python with
   `PYTHONDONTWRITEBYTECODE=1`, import unchanged `proto_ab_identity as H`, set
   `H.SWEEP_EVERY=60.0`, load the exact archived NPZ, and call
   `H.simulate(cache, policy="album", min_score=0.35, margin=0.1, admission=2.0,
   sweep=True, merge_thr=0.7, sticky_delta=0.0, keep_uncertain=False,
   birth_floor=1.0)`; stdout was teed to
   `instrument-fidelity/original-instrument-v2/stdout.json`.
2. `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/compare_original_renewed.py --json-output prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/original-renewed-diff-v1/result.json 2>&1 | tee prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/original-renewed-diff-v1/transcript.txt`

Raw evidence:

- `instrument-fidelity/original-instrument-v1/stdout.json` — SHA-256 `8527c3999293a274d696e6f8935d1f1049197ff9edba39c54b6af2d8b5561afe`.
- `instrument-fidelity/original-instrument-v1/classification.json` — SHA-256 `0035ed66d0ab383ff3742a1be96ad6ecfcc97ff11cb64ba58531df9fea850b79`.
- `instrument-fidelity/original-instrument-v2/stdout.json` — SHA-256 `337ca2c1f912568634fea6a68984d60901acc06567cee435d1106b833c92e519`.
- `instrument-fidelity/original-instrument-v2/config.json` — SHA-256 `2b6f6998291c21ff74cb9f551be826e2b83f9d48a39354252cd3d4867348cbcf`.
- `instrument-fidelity/original-instrument-v2/source-integrity-postflight.txt` — SHA-256 `dfbac9c4c23dc2a0cc9b29332ad4c4fb5cc174de5c618165e8fc9ea51b7cef36`.
- `instrument-fidelity/original-renewed-diff-v1/result.json` and `transcript.txt` — each SHA-256 `42200525b8626bb0bc8a583217ecb791df92219573a5300402a9e534b03e344e`.

Two diagnosis-only script defects (wrong repository parent, then lowercase JSON literal)
failed before result serialization, were corrected without touching inputs or official
files, and remain preserved in the differential evidence directory.

### L2 Stage 0 archived-cache truth-frame gate (`l2-stage0`, 2026-08-03)

Command:
`PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/prove_archive_truth_frame.py --output-dir prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/frame-diagnosis-v2 2>&1 | tee prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/instrument-fidelity/frame-diagnosis-v2/transcript.txt`

**VERDICT: BLOCKED — supervisor stale-frame synthesis REFUTED; required immediate
STOP.** The exact cache-row builder (`load_reference` → `plan_spans` →
`(span, truth-speaker)` grouping) reconstructed 92 rows from corrected reference
`28dc9a5b…0759`. All six columns of all 92 rows match archive `fd13bacb…7be5`
exactly: zero mismatched rows, per-column mismatch counts `[0,0,0,0,0,0]`, and
maximum absolute delta `0.0`. Those columns are span id, truth-speaker index, unit
start, unit end, eligible duration, and eligibility flag.

The stale reference `27c9b96e…ebbe` reconstructs 55 rows, so it cannot match the
92-row `fd13` archive. It instead matches the separate source-bench cache
`327f3328…a68a` exactly across all 55×6 values. The contemporaneous A1 record
`evidence/vector-rebuild.json` independently says old reference `27c9…` / old cache
`327f…`, then new corrected reference `28dc…` / new cache `fd13…` with 92 rows.
Archive bytes were `fd13…` before and after both probes.

The probe hard-refused with named error
`frame_gate_archive_matches_corrected_reference`, `<promise>BLOCKED</promise>`, and
exit 2. Per supervisor instruction, no A2.3 gate re-scope, consolidated anchor verdict,
dual-anchor completion record, A2-completion commit, or A3 work was performed.

The first identical probe produced the same decisive result but its `tee` opened
before the script-created output directory. Its result and copied inputs remain sealed;
the unchanged v2 rerun pre-created the directory and preserved full stdout.

Raw evidence:

- `instrument-fidelity/frame-diagnosis-v2/result.json` — SHA-256 `d45a963c2e385d734cfc5003da774ed4804816b05720fc89dd4deb4f3e5358f1`.
- `instrument-fidelity/frame-diagnosis-v2/transcript.txt` — SHA-256 `b1ab44d128d0b941c1aca7b0c4d4760f1e22b3e1eebf089e9bbf46018274f2b4`.
- `instrument-fidelity/frame-diagnosis-v2/inputs/stale-reference-27c9b96e.jsonl` — SHA-256 `27c9b96e86cce3be86a3ce06dd64c1710e2c94e72a01c30339e953db94b8ebbe`.
- `instrument-fidelity/frame-diagnosis-v2/inputs/corrected-reference-28dc9a5b.jsonl` — SHA-256 `28dc9a5b80098db58a261b4bfa73e2975acac31ef36e7e8f057c514d8bdc0759`.
- `instrument-fidelity/frame-diagnosis-v1/result.json` — SHA-256 `6694be3ff6daca3e3d7a1b3378b3a1be232a987583c96f11bcb0393620aeef17`.

### L2 Stage 0 consolidated anchor diagnosis and A2 completion verdict (`l2-stage0`, 2026-08-03)

Command: `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/verify_a2_completion.py --json-output prototypes/streaming-diarization/l2-stage0/evidence/a2-completion-verdict.json --transcript-output prototypes/streaming-diarization/l2-stage0/evidence/a2-completion-verdict-transcript.txt`

**VERDICT: A2 COMPLETE; A3 NOT STARTED.** The first A2 run correctly blocked on
stale derived-cache unit count. The authorized A1.2 versioned rebuild then produced
six development/validation cases × two runs on frozen inputs; all twelve runs were
exactly deterministic. The renewed corrected-alphabet baseline is `0.916765` and is
the instrumental L1 comparison base for A5. The blind holdout remains sealed.

The complete diagnosis chain is retained, not rewritten. The renewed A2's old
`0.913500 ±0.001000` gate first blocked. Replaying the 92-unit `fd13bacb…` archive
required a diagnosis-only legacy adapter: v2 scored `0.954974`, but its ingest defect
censored five units/5.382375 seconds before assignment as null hypothesis, a direct
score **deflation**, not inflation. The corrected v3 adapter passed the unit-23 and
all-92 preparation properties and scored deterministic `0.983449`. H1 was refuted
because production rescoring of sealed labels was identical; H2 was refuted because
all deployed identity constants and config hash matched; H3's apparent first policy
divergence was the adapter defect, and post-fix triangulation refuted causal/hindsight
divergence: the renewed runner calls production preparer/assignment, performs zero
sweep corrections, and the unchanged original instrument scores `1.000000` on the
same 92 rows. Thus partition change as the sole explanation, scorer mismatch,
constant mismatch, renewed-policy overstatement, and retrospective assignment are
all refuted.

The frame proof corrects the supervisor's premises on the record. Premise
“`fd13bacb…` is the accepted anchor's own measurement input” was wrong in the
load-bearing sense: it has corrected truth but proto truth-planned segmentation, not
the live/production planner frame. Premise “`fd13bacb…` is stale-reference data” was
also wrong. Exact row comparison proves: source cache `327f3328…` is the 55-unit
stale-reference/proto frame; `fd13bacb…` is A1's 92-unit corrected-reference/proto
truth-pure frame; `6fe79ce7…` is the 101-unit corrected-reference/production-planned
frame. The easy 92-unit frame saturates at `0.983449–1.000000`; only the 101-unit
production-planned frame mimics live segmentation and yields `0.916765`, near the
immutable accepted live pair `0.913500/0.914400`. **Established finding: L1 accuracy
is planner-frame-dependent.** The July-era 55-unit stale-frame `~0.886` observation
versus today's differing-config `1.000000` saturation is flagged as curiosity for the
operator packet, not an anchor or acceptance claim. The `fd13bacb…` attribution and
all three frame identities must also appear in that packet.

Supervisor-authorized calibration clarification, dated 2026-08-03: (a)
intra-instrument repeatability remains `±0.001` (`±0.1 pp`) and passes with observed
zero delta/exact semantic hashes; (b) cross-instrument anchoring compares the
production-planned corrected-frame baseline to both immutable live values using PRD
Gate H's predeclared `±0.005` (`±0.5 pp`) band. Observed deltas are `0.003265`
(`0.3265 pp`) and `0.002365` (`0.2365 pp`), so the gate passes. Applying the
same-instrument `±0.1 pp` repeatability band across instruments and planner frames was
a category error; that cross-frame use is retired, not the immutable live numbers.
PRD §10 acceptance gates are untouched. This is an instrument-calibration pin change
owned by the supervisor, not threshold/tolerance shopping.

A5 rule: all three arms—L1, ledger-only, and frozen L2—must run and compare on the
same production-planned per-case cache created inside the single sealed-holdout opening.
Cross-frame arm metrics are never comparable. The procedure is pinned at SHA-256
`6989d0ffdcdf2316b5c7c8549da226a00c2fa60b2ae9a712367d12b4d03d3902`.
Dual anchors are explicit and non-overwriting: live `0.913500/0.914400` remains
immutable production truth; bench `0.916765` is the instrumental A5 comparison base.

Sealed evidence chain (manifest SHA-256): first block
`e0747b97ec5750ed5b78f13114668c3a8668685c732f4cdb5448b5768543da14`;
A1.2 rebuild `40ec1acf8d49146c10d4c4d2f6ee897bbc7d42a6b57edc3df2caf6dd4ab9bce4`;
path-only correction `0135dc06705ee3c66a1bbe48844cd4c0ffbf482fc13b0126ea8f31021e00c476`;
renewed A2 `9839f3fb65d9f0642e9e31ddd050c9cd100b7bdb58251ea4d66146e241b7a5e4`;
direct anchor incompatibility `ff76c726bd9642bdd14e253932ab13c1416ecb5dd6803d5ad40ce0888436d3c6`;
legacy-ingest diagnosis v1/v2
`ea4abf34f872de651fa261fb8a237a8756b3e4a804c725022459e432972674c5` /
`70391fd90b088cf679b761b7532781d3c39f9f4f562ec62c6697b13f8c675ad1`;
contaminated legacy measurement v2
`58b12ce154e679bd54280d909a66a75237777e3c9d672747642c9bc935e60e69`;
H1/H2/H3/H3-causal
`c024dbb7b43128c7068f58b4bdd95625d6b1a2517c223e64a4d1fc9ad8024e54` /
`99d202f62bc7bc0e53273f5ec5ad014057d1f5acf9d872f7d7094e2e0fd9b663` /
`a4619fcb555e1b5475da7252a2982a76c6a2f83c93ff47356a8e9b55dad19d1f` /
`d128449f277d2c340ae8390cfa61c9c11f495a21b5b559a09a9b92011a41a866`;
v2 contamination failure/correction
`c42eb22652d617ad84b6e3486b19953e7025443371f6fb0e03d9c500bf850a47` /
`bcc667941906a847fd2d030fac3bb3416268486c0f5d569438404bc22a1f6ba6`;
adapter v3 red/attempt-1/final/boundary
`74bee1d413b1edcdbf96e52956a29b6b2be93812a206faa8b841c4e41ad14884` /
`da7862989131d4106b4d7638b77751b59c593d86e75160abe6992f21e1057a6b` /
`a52ea7f7d5a71ee0d0bf62a90eb3a9f1e63c2f20420184d53171f873531b914a` /
`331584b7b0794ef5cb8abd26f9d56f0d90b905b66338dbaacd19f36c76a7c005`;
corrected legacy measurement v3
`cdfc86d75527d998b1225c453a834b2eed4bb45c6a899745c308116f1b04920a`;
original/renewed triangulation
`430bc7514d6049387f4120de5fbff4c506a3ed20cf9c7dbe5cc8ba1ecbd682ff`;
frame proof `63f2b6e0c85cd6f5b87ea58e4e222219202f26f818608bc626fd4856f1253322`;
and consolidated A2 completion
`9118d88326e261899f30120aa9a448a91a9bb72936741ac82725b055bca9c387`
(158 files). Raw completion verdict SHA-256 is
`7380a3020c44a0fc85b619456b56b5541cba86117efbb79fcde0702d16bfe4df`;
raw transcript SHA-256 is
`4ccab8e42fcd3bb02b09a25c12aac5ce01c845a7656e280c5685962b74c47de2`.

Historical A12 manifest provenance was independently preserved by:
`git -C /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-l2-stage0 show 19983e34c75dbe4e9a27b09494ff742db943e5e9:prototypes/streaming-diarization/l2-stage0/evidence/A12_EVIDENCE.sha256 | rg 'run_l1_control.py|test_l1_control.py'`, yielding runner
`22ee9a8f…5752` and test `ce6c1cbb…e86f`; hashing each file from that commit reproduced
those values exactly. The sealed command/output record is SHA-256
`8adaf14810a061f75efaedea11ed1207c30d07ee7ad0d5c8cfa6e5b795d7ea52`.

### L2 Stage 0 A3 lifecycle-ownership verdict (`l2-stage0`, 2026-08-03)

Command: `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/evaluate_lifecycle.py --json-output prototypes/streaming-diarization/l2-stage0/evidence/a3-verdict/lifecycle-verdict-v2.json --transcript-output prototypes/streaming-diarization/l2-stage0/evidence/a3-verdict/lifecycle-verdict-v2.txt`

**VERDICT: PASS; choose `finalizing`.** The prototype proves
`active -> closing -> finalizing -> closed`, with
`active -> closing -> finalizing -> failed` and
`active -> closing -> aborted` branches. All eight predeclared invariants passed
red-first behavior tests: capture authority ends exactly at stop acknowledgement;
view authority and one terminal revision remain observable; the tape is sealed and
read-leased; one bounded queue owns all finalizers and at most one CPU finalizer runs;
timeout, cancellation, shutdown, degraded tape, and both tokenized and genuinely
raised exception paths release the lease exactly once and fall back to L1; abort does
not enqueue or start L2; TTL zero refuses a leased tape and reaps it after release; and
a new live meeting captures while an older finalizer is active. Queue overflow also
refuses atomically without partially revoking capture or acquiring a lease.

All three negative controls failed their intended invariant and were detected: the
current `active -> closing -> closed` shape publishes a revision after view authority
is gone; one-thread-per-session reaches three concurrent CPU finalizers with no queue
owner; early tape release leaves lease count zero and permits TTL-zero reaping before
read. The final full suite passed 13/13. Therefore the plan's decision rule selects
the visible `finalizing` state; a persisted job/result API is not required by A3, and
L2 is never run synchronously inside stop. Holdout remained sealed. No product,
service, deployment, host, TCC, volume, or retained-audio action occurred.

Raw invariant matrix and full state trace:
`evidence/a3-verdict/lifecycle-verdict-v2.json`, SHA-256
`ff18d660fecd3a2f4e4e75b4aa14fd3bc6571213254332460cb084cb2953eb5a`.
Verdict transcript SHA-256:
`b11ddbd110821ca79d79cff282da4e7dafdec8fba96f24f8a59d03c10f69114f`.
Full-suite JSON/transcript SHA-256:
`665ee6d8ad30973facac7b12ecff5316023f3ae0b9a6c0901dd05a34b0d81d7f` /
`aa983f41b542ea878ad5793465d90b0f5c25fcbe9276c8099ddf303dd102a045`.
`evidence/A3_EVIDENCE.sha256` seals 68 files and has SHA-256
`a8b333309f389c77a07c409d6efc9ef1946461938f8a882910d7a844b16a9998`.

Commit-granularity deviation: supervisor authorized A3 as its own atomic commit,
continuing the A1/A2 refinement of plan §5. This preserves §5's independently
testable/revertible invariant; A3 is not held with A4 resource measurement work.

A3 final proof-strength addendum: the 68-file v1 seal and 13-test v2 verdict above
remain preserved. A post-green audit added two red→green mutation-sensitive checks:
queue overflow now refuses without partial state/lease mutation, and an actually
raised finalizer exception (not only an outcome token) releases once and falls back
to L1. A third red→green supplement proves abort of an already queued finalization
removes the job, releases its lease once, and never starts L2. Final full suite:
14/14 PASS. Authoritative matrix/state trace:
`evidence/a3-verdict/lifecycle-verdict-v3.json`, SHA-256
`c3f10e9dc5c47c1d5a01a047dd3b444245d375e2e58b5a4766a5d560655d3ffe`;
transcript SHA-256
`b11ddbd110821ca79d79cff282da4e7dafdec8fba96f24f8a59d03c10f69114f`.
Final full-suite JSON/transcript SHA-256:
`27f3139362ce79c31e569dd44d5e6012f444c73b04ba6c7e11c72350f86e18f8` /
`1d772587f4fcda1c0a8949f82940dd3a9ed9e0c20de599b393775665f2cf4e8a`.
`evidence/A3_EVIDENCE_V2.sha256` seals 76 files and has SHA-256
`7bb6810c085e2eb3b41ec6d73c70530744c9618ddfb5eac23c8103f8cc45a5ee`.
The decision remains `finalizing`; holdout remains sealed; A4 remains unstarted.

A3 authoritative-seal addendum: a final literal-audit added the queued-finalization
abort proof after the v2 seal. The new red reproduces the leaked queued lease; green
removes the job, releases exactly once, leaves `l2_started=false`, and makes the queue
empty. Earlier v1/v2 seals remain historical; their four source rows reflect later
red→green strengthening. The authoritative current-tree seal is
`evidence/A3_EVIDENCE_V3.sha256`: 76/76 verify, SHA-256
`e2e3e3445f2a9b6a8623b28accfdbf58a8da3af19762d4b19e8424eac9876758`.
The authoritative verdict remains `lifecycle-verdict-v3.json` at SHA-256
`c3f10e9dc5c47c1d5a01a047dd3b444245d375e2e58b5a4766a5d560655d3ffe`.
Reproduce it with the command above, replacing both `lifecycle-verdict-v2` output
stems with `lifecycle-verdict-v3`.

### L2 Stage 0 A4 preregistered measurement frame (`l2-stage0`, 2026-08-03)

Question: can one nice'd, one-thread production CPU embedder on the deployed
i7-14700F satisfy the fixed resource gates while the A3 single-worker lifecycle
keeps post-drain stop acknowledgement and new-session admission responsive?

Before the first A4 measurement, the frame is frozen as follows. Use the frozen
`30m-acquired-jamie-dimon` WAV only as resource bench audio; never read its reference.
Read it sequentially in 40,000-sample/2.5-second chunks, materialize at most one
scratch WAV at a time, and call production `_OnnxWeSpeakerEmbedder` with the pinned
model, `CPUExecutionProvider`, and ONNX intra/inter-op threads both one. "Cold" means
a new production ONNX session with uncontrolled OS page cache; "warm" immediately
reuses that session. Measure 25, 100, 300, and 1,800 seconds in both states. The RTF
and 180-second gates use the worse of the measured cold/warm 1,800-second runs;
shorter-run 30-minute projections are diagnostic. RSS is process peak/current; each
chunk records logical PCM/decoded/scratch bytes plus `/proc/self/io` read counters.

Lifecycle values are explicitly prototype-frame proxies: post-canonical-drain L2-off
close versus A3 `acknowledge_stop()`+bounded enqueue; actual production
`LiveSession`+`LiveV2Session` construction/snapshot/release under no, queued, and
active single-finalizer states; actual queue wait/finalizing/publication timestamps.
Campaign B still owns the product-path live-latency gate. Fixed A4 gates remain RTF
`<=0.10`, 30 minutes `<=180 s`, no whole-tape materialization, maximum one active
finalizer, contention p95 `<4000 ms`, and stop-ack p95 overhead `<=100 ms`.

No optimization pass is authorized by this base frame. If the RTF gate misses, seal
the base result first, append one exact bounded interval-selection/caching design
before executing it, run that design once, and stop if it misses. No second pass,
tolerance change, or work on the live canonical pump.

### L2 Stage 0 A4 sole optimization preregistration (`l2-stage0`, 2026-08-03)

The sealed base result is `evidence/a4/base/a4-runtime-base.json`, SHA-256
`f5a06998cddcee91b536750a3c988c1650d2b0601d877fc6c4a92ea1c7c39796`.
Exactly two cost gates missed: the cold 30-minute run was `180.210634953 s`, RTF
`0.1001170194`; its warm reuse was already `178.537065659 s`, RTF `0.0991872587`.
Chunking, concurrency, contention latency, and stop acknowledgement all passed.

The one authorized optimization is now frozen as `eager-prewarmed-session-v1`:

- cache exactly one production `_OnnxWeSpeakerEmbedder` session in the sole CPU
  finalizer worker, keyed by the pinned model/source hashes, CPU provider, one/one
  ONNX threads, frontend version, and 40,000-sample cap;
- at worker startup—not in stop and not on the live canonical pump—load and exercise
  that exact session once with one 2.5-second scratch chunk, discard the vector, and
  report warm-up wall/RSS separately;
- invalidate/refuse on any key/hash/settings mismatch; never cache audio, vectors,
  candidate results, or more than one model session;
- run all 720 production-size chunks for the 30-minute tape. No speech interval is
  removed and no result from the warm-up is reused;
- repeat the exact 25/100/300/1,800-second matrix with two consecutive finalizers per
  duration using the eagerly warmed session. The unchanged RTF/180-second gates use
  the worse of the two measured 1,800-second finalizers.

This is the single preregistered optimization pass allowed by A4. A miss stops the
campaign; there is no second pass or gate adjustment.

### L2 Stage 0 A4 resource-envelope verdict (`l2-stage0`, 2026-08-03)

Reproduce the sealed verdict from raw evidence:

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/evaluate_runtime.py && PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/write_a4_evidence_manifest.py && shasum -a 256 -c prototypes/streaming-diarization/l2-stage0/evidence/A4_EVIDENCE.sha256
```

**VERDICT: BLOCKED; STOP CAMPAIGN A.** On the actual i7-14700F WSL deployment
CPU, the sealed base 30-minute pair was cold `180.210634953 s` / RTF
`0.1001170194` and warm `178.537065659 s` / RTF `0.0991872587`. Only the fixed
RTF/time gates failed. The one preregistered `eager-prewarmed-session-v1` pass then
ran every chunk unchanged; its two 30-minute finalizers were `180.294477612 s` /
RTF `0.1001635987` and `179.533264497 s` / RTF `0.0997407025`. The worse run
still exceeds both RTF `<=0.10` and 30 minutes `<=180 s`. No second pass, gate
change, or candidate work is permitted. A5/A6 did not start; holdout stayed sealed.

Full base cold/warm wall seconds and RTF: 25 s `4.015644/0.160626`,
`2.509545/0.100382`; 100 s `10.853254/0.108533`, `10.014125/0.100141`;
300 s `30.705834/0.102353`, `29.934316/0.099781`; 1,800 s
`180.210635/0.100117`, `178.537066/0.099187`. Full optimized first/reused
finalizer values: 25 s `2.520144/0.100806`, `2.516306/0.100652`; 100 s
`10.014872/0.100149`, `9.955873/0.099559`; 300 s
`29.998517/0.099995`, `29.816650/0.099389`; 1,800 s
`180.294478/0.100164`, `179.533264/0.099741`. Shorter-run 30-minute
projections and the separately reported cache warm-ups remain in raw JSON.

The other four gates passed in the final pass: each of 1,780 reads was exactly
40,000 samples, with 80,000 source PCM bytes, 160,000 decoded bytes, and an 80,044
byte scratch WAV; no whole tape was materialized. Cached-run embed `rchar` was
80,163-80,179 bytes/chunk and physical `read_bytes` was zero from page cache; the
base first cold chunk separately exposes model loading (up to 97,247,142 `rchar`
and 225,239,040 physical bytes). Peak worker RSS across both passes was 711,372,800
bytes. Measured maximum active finalizers was one. Final optimized queue waits were
`0.010196/2.516813 s`, finalizing times `2.516529/2.503222 s`, and final-visible
times from enqueue `2.537222/5.020376 s`. New-session proxy p95 was
`0.010915/0.010575/0.011320 ms` for no/queued/active finalizer; post-drain stop-ack
p95 overhead over L2-off was `0.001229 ms`. These latency values are A3 prototype
proxies; the product-path Campaign-B gate was not claimed.

Host safety held before, during, and after both nice-10 runs: all three services
remained active but idle; zero live creates/frames/heartbeats since the current
service start; zero nonterminal batch jobs; deployed tree stayed clean at
`9089b332`; source/model/audio hashes stayed exact. WSL exposed 22 GB memory and
8 GB swap; cpufreq governor and CPU thermal sensors were unavailable, recorded as
such; auxiliary GPU temperature was 31 C before and 28 C after. The exact 60,891,052
byte remote scratch was removed only after all raw results were copied back; the
deployed tree was never written.

Raw base JSON/transcript SHA-256:
`f5a06998cddcee91b536750a3c988c1650d2b0601d877fc6c4a92ea1c7c39796` /
`e6627e21a851fd15610fa683bb503e5864a5ed2c29b03978946c8cd981f366d3`.
Raw optimized JSON/transcript SHA-256:
`8f7714eaf45504dadbc11cb1afec38fff1503ba8c22ad5112cf374fb0058de1a` /
`8b83f6378ee62a37d66ca3f22bd6ebc156c5d8c5afdd6023ecbd7030edc7514b`.
Host-before and host-after/cleanup SHA-256:
`91ce7858444106dfd1f2e77951f458a9cbdcd014efef2fa5f0a14de770071201` /
`051ad016a93ba6a6c85cb4640773aa4f89c9a1c2aa06bdd5dc6a5cf667b91a21`.
Consolidated verdict JSON/transcript SHA-256:
`5861323145436792f81cbf3e7ac4011e8be93fe2550d4857fa239a89a082da15` /
`acc138910ecee2b533b8ecc835cc62da368b5a5f670ab87044271e1e1b039ea5`.
`evidence/A4_EVIDENCE.sha256` seals 26 files, SHA-256
`1e0125fe94d56a0d8a9eac4bb56893accb59a74025ee8dc5510be6b9a2fe958d`.

Commit-granularity deviation: supervisor explicitly authorized A4 as its own atomic
commit, continuing the A1/A2/A3 precedent rather than plan section 5's combined
lifecycle/resource commit. This keeps the failed gate and its sole optimization
independently testable and revertible.
