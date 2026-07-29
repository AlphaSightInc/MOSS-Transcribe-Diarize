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
