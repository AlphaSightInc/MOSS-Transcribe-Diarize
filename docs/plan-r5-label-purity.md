# Round 5 — is one provider label one voice? (prototype plan v2, 2026-10-01)

Status: PLAN v2, after adversarial review (10 findings, all accepted; §10 maps each to its change). Prototype only —
no production change until a candidate passes every gate and the user approves.
Decision: user D7 = O2. Executors: four Codex agents (gpt-6.1-sol, high reasoning) in tmux panes 6.1–6.4, one worktree
each (`…-wt-r5-p1…p4`, branches `gemini/r5-p1…p4`, base `gemini/r4-ui`). Lead: Claude (MOSS:5.1).

## 1. Structural question

After Stop, a long recording is re-transcribed in 15-minute chunks (900 s, 30 s overlap). Inside a chunk the provider
names voices with chunk-local labels. `LongFinalStitcher` (≥ 15 min) and `FinalWordPolicy` (< 15 min) decide which
labels are one person from two kinds of evidence:

- **same person** — the labels' voice fingerprints are similar (WeSpeaker cosine ≥ .65). A label's fingerprint is the
  mean of its **first three** spans of ≥ 2 s, each cut to 10 s (`FinalWordPolicy._intervals`): at most 30 s, all early;
- **different people** — the two labels alternate inside one chunk (a-b-a, gaps ≤ 2 s) → their merge is vetoed.

Both use a label as if it were one voice. Measured, it sometimes is not:

| Symptom | Case | Number |
|---|---|---|
| One person split in two (veto from a counterfeit alternation) | 65.5-min clean-up and File pass, chunk 3: the host's two labels reused for two new voices for 21 s | long60-part DER .165 vs .049 without those three turns |
| Two different people merged | recorded K4 s0 (label purities 75 % / 84 %); fresh K4 s0 | cosine .741, no veto |
| Rule B (veto needs ≥ 2 alternations) | bench | repairs the 65.5-min case, merges different speakers in 2 cases — rejected |
| Rule C (a turn under .46 vs its label becomes a new label) | bench | 13 cases gain speakers; 2.8 % of correct turns score under .46 — rejected |
| Rule V (alternation counts only if its turns match their labels) | raw labels | drops the veto for 7 of 38 different-speaker pairs, all with a mixed label — rejected |

**Question.** Which is the smallest sufficient explanation and repair of these failures:
(H-sample) the label fingerprint is merely badly sampled (first 30 s), or
(H-mixed) a label really carries two voices, so its speech must be re-divided before any merge or veto uses it?
"Mixed labels are only a symptom, fix the sampling" and "leave it" are both allowed verdicts.

## 2. Minimum primitives

- **Observation** — one short window of one label's voiced audio inside one chunk, with its fingerprint. A window never
  crosses a label change. It records: chunk, label, start/end, **voiced seconds** (production VAD, not timestamp span),
  an **overlap flag** (another label's words fall inside it), and — where a complete reference exists — the true
  speaker and that speaker's share of the window. Windows, not turns, because a turn can already hold two voices (the
  bench has a 95 s turn that opens with another voice). Window length is not assumed: see G0.
- **Voice group** — a set of observations judged one voice by a stated grouping rule. Every candidate must state its
  rule in full; "self-consistent" is not a rule.
- Derived, not primitive: **purity** of a label = share of its voiced time in its largest voice group. It is a
  measurement used for reporting, never a gate on what may be repaired.

No language-, speaker-count- or corpus-specific constants. Every threshold is justified on DEV data with its margin.

## 3. Invariants (each with its operational meaning)

1. **Single-voice labels keep their speech together.** For a label whose truth-tagged observations are all one
   speaker, the candidate puts all of them in one group. Merging that group with other labels later is allowed
   (assignment is compared up to renaming).
2. **No new false merge.** Scored on final groups, pair by pair: two groups-with-different-true-speakers must not end
   in one final group unless shipped rule A already merges them on the same input (baseline errors are listed, not
   hidden). Speaker count is reported but is not the test — a false merge plus a false split keeps the count.
3. Text, word timing and chunking are untouched; only the speaker of a word may change.
4. Deterministic given the same provider output and audio.
5. **Ambiguous evidence never creates a speaker.** Windows that are overlap-flagged or under the voiced-seconds floor
   cannot found a new group; they follow or stay.
6. One primitive, two call sites (short-meeting policy and chunk stitcher), or a stated reason why not.
7. Live path unchanged.

Invariants are claimed only for the measured inputs listed in §6.

## 4. Roles (one per pane)

**E — evaluator (pane 6.4, the only pane with the provider key). Not a candidate.** Builds and freezes the bench (§5–6):
observation tables, truth, scorer, adversaries, case-by-gate eligibility; measures G0 and prevalence; runs the one paid
pass; runs every candidate's frozen command on HOLD data.

**P1 — re-divide mixed labels (pane 6.1).** Group each label's observations; when a label holds two or more voice
groups, each with enough voiced support, split it at window resolution (each word takes the group of the window that
covers it). Then run the unchanged merge + veto rules on the resulting labels.

**P2 — move stray speech, keep the provider's labels as the model (pane 6.2).** Each label gets a **clean core** (its
observations that agree with each other; the window under test and windows that fail the core test are excluded). A
window moves only if it clearly mismatches its own core and clearly matches another label's core; windows that match
no core and have their own support become a new label; everything else **abstains** (keeps its name, counted). All
decisions are computed from the original cores and applied once — no iterative re-estimation (two mixed labels must
not confirm each other's errors).

**P3 — no relabelling: the control arm (pane 6.3).** Two variants, assignment untouched:
- **C0 — sampling control.** Label fingerprint from voiced windows spread over the whole label instead of the first
  three spans. Tests H-sample alone.
- **C1 — group-level evidence.** Merge on clean-core fingerprints; an alternation vetoes the two *voice groups* that
  alternate, not the two labels (so a minority voice's alternation is kept as evidence about that minority voice).
  Known limit by construction: wrongly named speech stays wrongly named — P3 cannot pass G-name; it shows how much of
  the damage is repairable with evidence alone.

P1 and P2 consume E's observation tables (same fingerprints for everyone; candidates add no embeddings unless they
state and count them).

## 5. Order of work (independence)

1. **Stage 0 — E builds; candidates pre-register.** E publishes the observation schema and one DEV sample first.
   P1–P3 commit `NOTES.md` (question, hypothesis, grouping rule in full, falsifier, parameters with planned values)
   **before** seeing bench numbers, and code against the schema.
2. **Freeze.** E commits scorer, truth, eligibility list, DEV/HOLD split and the finite adversary set, and records the
   commit in its status file. Later changes need the lead's approval and are listed in the verdict.
3. **Stage 1 — tune on DEV only.** Candidates never read HOLD files.
4. **Stage 2 — HOLD.** Each candidate hands E one frozen command (commit id). E runs it on HOLD and publishes the
   scorecard. A candidate changed after seeing HOLD results is a new version; every version and every provider draw is
   reported, never the best one.
5. **Stage 3 — only for a passing candidate, only with the user's OK:** validation on real late-joiner audio that no
   candidate has seen (new provider calls, ≈ $0.30; §7), then production change with regression tests, full suites and
   a long-meeting re-check on the MacStudio.

## 6. Bench, eligibility and gates

Shared location (outside every worktree): `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P70/purity-bench/`.

**Data and what each item can support** (E fills in the counts and freezes the list; a case that cannot support a gate
is `UNKNOWN` for it, never a pass):

| Item | Kind | Supports |
|---|---|---|
| 8 raw provider responses, synthetic meetings K2/K3/K4/K6 × seeds 0,1 (LibriSpeech voices, complete truth) | raw words + audio | all gates; seed 0 = DEV, seed 1 = HOLD unless E's counts require another split |
| 65.5-min fixture, **new raw pass** (paid) | raw words + audio; long60 part has complete truth; Acquired part truth is partial | G-repair and G-name **after** E annotates the newcomer interval 2588–2640 s (who speaks when) from the public source; HOLD |
| 65.5-min saved turns (the known failure) | approximate replay (saved names hide raw labels) | DEV illustration only; reported as approximate |
| 27 P53 clips | pair-level only: centroids, alternation counts, truth relation; no turns | pair audits only; cannot run P1/P2 |
| Overlap mixtures (0 dB, −10 dB) and mic fixture, rebuilt recipes | audio + saved turns | invariant 5 (overlap must not become extra speakers) |
| Adversaries, $0, finite and listed before the freeze | label swaps injected into raw labels with known truth; minority speech of 5/10/20/60 s; minority made only of < 2 s turns; a single-voice label recorded through two channels | G-protect, G-name, invariants 1 and 5. Stated limit: injected swaps do not reproduce how the provider answers shifted audio — that is Stage 3 |

DEV and HOLD must each contain ≥ 1 mixed label and ≥ 1 exercised protective case (below); if the data cannot give
that, E says so before the freeze and the lead decides.

**Gates.** A candidate PASSES only if, against shipped rule A on the same inputs, on HOLD:

| Code | Gate | Pass rule |
|---|---|---|
| G0 | the observation carries identity | Before anything else, E measures same-voice vs different-voice fingerprint separation by voiced window length (2, 3, 5 s) on truth-tagged data, clean and overlap-flagged separately. If no length ≤ 5 s separates (equal-error rate > 10 %), window-level repair is infeasible: P1/P2 stop, verdict is C0/C1 or "leave it" |
| G-name | wrongly named speech goes down | seconds of speech carrying a group whose dominant true speaker is someone else, over **all** speech including turns < 2 s and minority speakers: no case worse than A by > 0.5 % of its speech; total strictly lower. Reported per minority speaker |
| G-der | no harm | no case's DER worse by > .005; mean not worse |
| G-merge | invariant 2 | zero new different-speaker merges in final groups; lost vetoes audited pair by pair (every label/group pair, whatever its cosine) |
| G-protect | protection is exercised | at least one case with two different voices, merge-eligible similarity (≥ .65) and a single alternation must exist in the scored set and stay apart. If none exists: **UNMEASURED → no ship** |
| G-repair | the 65.5-min host is one speaker | long60-part DER ≤ .060 on raw chunk words. If the new pass does not reproduce the label reuse: not exercised → UNMEASURED on raw; the approximate replay is reported separately and does not count as a pass |
| G-single | invariant 1 | zero single-voice labels divided |
| G-amb | invariant 5 | overlap fixtures and the two-channel adversary gain no speaker |
| G-adv | finite adversary set | no gate above violated on any listed variant; report the breaking point |
| G-cost | bounded | on the 65.5-min meeting on the MacStudio: added wall time ≤ **30 s** (clean-up measured 140 s today), added peak memory ≤ 300 MB; embeddings, reuse, grouping time reported |

Prevalence (E, $0): how often mixed labels occur in the real public recordings on disk. If ≈ 0 outside spliced audio,
"leave it" is the likely verdict.

## 7. Spend

Estimate basis $0.005 per audio-minute including output (bench figure; invoice may differ — stated as an estimate).
- Stage 0–2: one raw pass over the 65.5-min audio = 3930.9 s + 4 × 30 s overlap = **$0.338**; one retried 900 s chunk
  +$0.075. **Cap $0.42.** Calls are sequential; before each physical attempt the script reserves that attempt's cost and
  stops if spent + next > cap. At most one retry in total.
- Stage 3 (needs the user's OK): ≤ 4 calls of ≤ 900 s on new late-joiner audio, **cap $0.30**.
Only public audio is sent. The key is read from `…-wt-r5-p4/.env.local` into memory, never printed or logged.

## 8. Method for every pane ("/prototype")

Throwaway code under `prototypes/gemini-live/label-purity/<e|p1|p2|p3>/` in the pane's own worktree; one command to
run; prints full state; contract in `NOTES.md` committed before the first measurement; production code path where
possible (production WeSpeaker encoder and ONNX, production `LongFinalStitcher` / `FinalWordPolicy` / `parse_words`);
verdict with numbers in `NOTES.md`; no production or test file changed; local commits only, no push. A measured
rejection is a valid result and must be stated plainly.

## 9. Risks

- R1 Too few mixed labels with truth to separate candidates — E reports the counts before the freeze.
- R2 Short windows may not carry identity — G0 decides before any candidate work is judged.
- R3 Overlapped speech looks like a mixed label — invariant 5, G-amb.
- R4 The trigger may be rare in real meetings — prevalence; "leave it" is allowed.
- R5 The new raw pass may not reproduce the label reuse (provider is not repeatable) — then G-repair is UNMEASURED on
  raw words and a ship decision needs Stage 3.

## 10. Review findings → changes

| Finding | Change |
|---|---|
| F1 a turn can hold two voices | observation = voiced window, not turn (§2); G0 |
| F2 "≥ 95 % pure untouched" protects the error; short turns ignored | purity is reporting only; G-name over all speech; G-single is about truly single-voice labels |
| F3 protection may be vacuous | G-protect must be exercised, else UNMEASURED; pair-by-pair veto audit in G-merge |
| F4 data cannot support every gate | eligibility table; newcomer interval annotated before use; replays marked approximate |
| F5 freeze does not give independence | §5: freeze before tuning, DEV/HOLD, every draw reported, Stage 3 on unseen real audio |
| F6 P2/P3 reuse contaminated evidence | clean cores, abstention, one-shot updates (P2); group-level vetoes keep minority evidence (C1); P3 declared unable to pass G-name |
| F7 cause not established; P4 is not a candidate | H-sample vs H-mixed; C0 sampling control; evaluator role |
| F8 invariants not operational | §3 |
| F9 duration ≠ voice evidence | voiced seconds, overlap flag, two-channel adversary, invariant 5 |
| F10 cost unbounded | §7 reservation and caps; G-cost limits |
