# PROTOTYPE NOTES — streaming diarization feasibility (design doc §6)

Throwaway. Delete after verdicts are copied into `docs/design-streaming-diarization.md` §7.
Everything here is excluded from git via `.git/info/exclude` (active Ralph loop must not
see it).

## Questions and verdicts

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
