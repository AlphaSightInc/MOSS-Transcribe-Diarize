# Round 5 — label purity before stitching (prototype plan, 2026-10-01)

Status: PLAN (prototype only; no production change until a candidate passes the gates and the user approves).
Decision: user D7 = O2. Executors: four Codex agents (gpt-6.1-sol, high reasoning) in tmux panes 6.1–6.4, one
worktree each (`…-wt-r5-p1…p4`, branches `gemini/r5-p1…p4`, base `gemini/r4-ui` @ `5cdf4fe6`). Lead: Claude (MOSS:5.1).

## 1. Structural question

After Stop, a long recording is re-transcribed in 15-minute chunks (`TerminalTranscriber`, 900 s chunks, 30 s overlap).
Inside a chunk the provider names voices with chunk-local labels. `LongFinalStitcher` (≥ 15 min) and
`FinalWordPolicy` (< 15 min) decide which labels are one person from two kinds of evidence:

- **same person**: label voice-fingerprint centroids are similar (WeSpeaker cosine ≥ .65);
- **different people**: two labels alternate inside one chunk (a-b-a) → their merge is vetoed.

Both rules assume **one provider label = one voice**. That assumption is sometimes false: the provider reuses an
existing label for another voice (measured: P53 K4 label purities 75 % / 84 %; the 65.5-min run's chunk 3, where two
newly arrived voices received the host's two labels for 21 s). Then the centroid is contaminated, alternations can be
counterfeit, and some turns carry the wrong name. Evidence so far (`prototypes/gemini-live/aba-veto/NOTES.md`,
`~/Documents/Codex/2026-09-28/moss-gemini/evidence/P69/r4-long/`):

| Symptom | Case | Number |
|---|---|---|
| Host split in two (veto from a counterfeit alternation) | 65.5-min live clean-up and File pass | saved DER .165 vs .049 without the three turns |
| Two different speakers merged (contaminated centroids) | P53 K4 s0; fresh K4 s0 | cosine .741, no veto |
| Rule B (≥ 2 alternations) | bench | repairs 65.5-min, merges different speakers in 2 cases — rejected |
| Rule C (split turns under .46 to own label) | bench | 13 cases gain speakers (2.8 % of good turns fall under .46) — rejected |
| Rule V (alternation counts only if turns match labels) | raw-label pass | outcome gates pass; drops the veto for 7/38 different-speaker pairs with a mixed label — rejected |

**Question:** what is the smallest step, applied before any merge or veto, that makes "one label = one voice" true
enough — and what should happen to the speech that does not belong to its label?

## 2. Minimum primitives

- **Turn**: contiguous words of one chunk-local label (already produced by `speaker_turns`).
- **Turn fingerprint**: WeSpeaker embedding of a turn's audio; trusted only for turns ≥ 2 s of voiced audio (the
  existing voiceprint evidence bar). Shorter turns carry no identity evidence and must follow, not lead.
- **Label purity**: the share of a label's fingerprinted speech time that belongs to its dominant voice.
- **Dominant voice of a label**: the largest self-consistent group of its turn fingerprints.

Nothing else is introduced unless a prototype shows it is necessary. No language, speaker-count or corpus-specific
constants; thresholds must be justified on the bench and stated with their margin.

## 3. Invariants

1. A pure label is never changed (no new speakers from pure labels — rule C's failure).
2. Two true speakers are never merged because of the new step (the K4 protection must hold or improve).
3. Text, word timing and chunking are untouched; only speaker assignment of turns may change.
4. Deterministic given the same provider output; bounded extra embeddings (state the count per meeting).
5. Applies identically to the short-meeting policy and the chunk stitcher (one primitive, two call sites) or says why not.
6. Live path unchanged (this is the whole-recording clean-up and File/URL path).

## 4. Candidates (one per pane; same bench, same gates)

- **P1 — split impure labels (pane 6.1).** For each label, test whether its ≥ 2 s turn fingerprints form two
  self-consistent groups (duration-weighted); if so split the label into sub-labels and run the unchanged rules.
  The decision is per label (group level), not per turn (rule C's mistake).
- **P2 — reassign stray turns (pane 6.2).** Keep the provider's labels as the model; move a ≥ 2 s turn to another
  label only when its fingerprint matches that label's leave-one-out centroid clearly better (margin) than its own;
  a turn that matches no label becomes a new chunk-local label. Short turns follow their neighbours' outcome only if
  the evidence says so; otherwise stay.
- **P3 — purity-aware evidence, no relabelling (pane 6.3).** Leave labels alone; compute each label's dominant voice;
  merges use dominant-voice centroids, and an alternation vetoes only when it is between the two labels' dominant
  voices. Turns outside the dominant voice keep their name (known limit) — measure what that costs.
- **P4 — bench, prevalence and adversary (pane 6.4).** Owns the shared bench and gates (§5), the one paid raw pass
  over the 65.5-min audio (cap $0.40), a measurement of how often impure labels occur in the real public recordings,
  and adversarial inputs at $0 (splice offsets 10–120 s before a chunk boundary built from saved raw outputs; label
  swaps injected into real raw labels with known truth). Scores P1–P3 independently when they publish.

## 5. Bench and gates (owned by P4, frozen before any candidate is scored)

Data ($0 unless stated): the 8 raw provider responses in `P69/r4-long/bench-aba/raw/`; the 27 P53 clips with recorded
raw labels, centroids and truth; the 65 saved turn sets; the 65.5-min fixture + **one new raw pass (paid, ≤ $0.40)**;
adversarial variants derived from these. Shared location (outside any worktree):
`~/Documents/Codex/2026-09-28/moss-gemini/evidence/P70/purity-bench/`.

A candidate PASSES only if, against shipped rule A on the same inputs:
- G1 no scored case's DER worsens by more than .005, and the mean does not worsen;
- G2 no case's speaker count moves away from truth;
- G3 the 65.5-min host is one speaker (DER ≤ .060 on the long60 part) on raw chunk words, not only saved turns;
- G4 the K4 different-speaker merge does not get worse, and no new different-speaker merge appears anywhere
  (audit every label pair, as in `raw_audit.py`, not only outcomes);
- G5 pure labels untouched: 0 changes on labels with purity ≥ .95 across the bench;
- G6 adversarial set: no gate above is violated on any variant; report the breaking point if one exists;
- G7 cost: extra embeddings per meeting stated and ≤ the number of ≥ 2 s turns; wall time on a 65-min meeting stated.

Run-to-run provider variation: where a case was sampled more than once, report each sample; never pick the best.

## 6. Method for every pane ("/prototype")

Throwaway code under `prototypes/gemini-live/label-purity/<p1|p2|p3|p4>/` in the pane's own worktree; one command to
run; print full state; state the question, hypothesis and falsifier in `NOTES.md` **before** the first measurement
(commit it); measure on the production code path where possible (real encoder, real `LongFinalStitcher` /
`FinalWordPolicy`); record the verdict with numbers in `NOTES.md`; no production or test change; local commits only.
A candidate that fails says so plainly — a measured rejection is a valid result.

## 7. After the prototypes

Lead compares P1–P3 on P4's scorecard, recommends one (or none) to the user, and only then is production changed
(`gemini_long_final.py`, `gemini_final_policy.py`) with regression tests built from the recorded 65.5-min and K4
patterns, the full suites, and a real long-meeting re-check on the MacStudio.

## 8. Risks

- R1 The bench may be too small to separate candidates (few impure labels with truth) — P4 reports the count first.
- R2 Fingerprints on 2–4 s turns are noisy; a candidate may only work with longer turns — state the minimum.
- R3 Overlapped speech looks like an impure label — candidates must not "fix" overlap into extra speakers.
- R4 The trigger may be rare in real meetings (prevalence unmeasured) — P4 measures it; if ≈ 0, the answer may be
  "leave it".
