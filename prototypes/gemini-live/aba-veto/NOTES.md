# PROTOTYPE — the A–B–A merge veto: one alternation or two? (R4-N, P69 F3 follow-up, $0, no provider calls)

One command (worktree root): `PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r4-n.venv/bin/python prototypes/gemini-live/aba-veto/bench.py`
Receipts: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P69/r4-long/bench-aba/`.

## Contract (written before the bench ran)
1. **Structural question.** Clean-up merges two provider labels when their voices match (cosine ≥ .65) unless the
   two labels were seen talking to each other (A–B–A turns, gaps ≤ 2 s) — the "veto". In the P69 65.5-min meeting
   one alternation between two *reused* labels vetoed six correct merges (host named twice, long60-part DER .165
   instead of .049). Is one alternation enough evidence that two labels are different people?
2. **Minimum primitives.** (a) *label* — what one provider call names a voice inside its chunk; (b) *voice match* —
   cosine of two labels' WeSpeaker centroids (first three ≥ 2 s spans, ≤ 10 s each); (c) *alternation* — an A–B–A
   triple of turns with both gaps ≤ 2 s; (d) *veto* — a label pair that may never share a group. Nothing else.
3. **Invariants.** A rule may only change which pairs are vetoed; cosine threshold, spans, seam logic and chunking
   stay as shipped. Replays run the production `LongFinalStitcher` / `FinalWordPolicy` classes and the production
   encoder; the rule variants are copies that differ in the veto only and are asserted equal to production when
   set to the shipped rule.
4. **Rules.** A = shipped (1 alternation vetoes). B = veto at ≥ 2 alternations of the pair inside one chunk/call.
   C = before the merge, a turn ≥ 2 s whose own voice (first 10 s) scores cosine < .46 against its label's
   centroid becomes its own label (.46 is the existing "this voice is that speaker" floor in
   `gemini_live_runtime`; no new threshold); then rule A.
5. **Assumptions and unknowns.** The raw provider responses (word-level chunk-local labels) are gone: the
   prototype cache lived in the removed `…-wt-gemini-live` worktree. The bench therefore replays **saved turn
   sets** (label = chunk × saved name). Saved names are already merged groups, so (i) a replay can only show
   further merges; (ii) two raw labels that share a saved name hide their own alternation counts — rule B's
   effect on raw labels can be larger than measured here: **unmeasured**. Centroids come from saved turns, not
   words: approximate. Mic lanes and inputs whose audio is not on disk get the alternation count only.
6. **Falsifier.** Rule B is rejected if any gate below fails. Rule C is reported, never shipped from this bench.
7. **Tool decision.** Step 1 needs no audio: if no label pair has *exactly one* alternation in any chunk, rules A
   and B veto the same pairs and are the same program — recorded as identical. Only the remaining cases need the
   encoder. Rule C needs the encoder on every case with audio.

## Prior evidence read before these gates were written (settled, `window/NOTES.md` §final policy, P53)
`evidence/P53/final-policy-pair-audit.json` holds every raw-label pair with cosine ≥ .65 on the 15 tune + 12
test clips, with truth and alternation count. Exactly-one-alternation pairs: 3 same-speaker pairs (synthetic K2
s0 ×2, K3 s1) and **1 different-speaker pair (synthetic K4 s0, cosine .741)**; real clips: none.
`final-policy-tune.json` records K4 s0 without the veto: DER .2211 → .3302 and one false merge; K2 s0 improves
.3815 → .2157. The veto was adopted on this evidence. So rule B is expected to fail G2 on K4 s0 for the
short-meeting policy; the bench still reports every case.

## Gates (precommitted)
| Code | Gate | Pass rule |
|---|---|---|
| G1 | no harm | every case with a timed reference: DER(rule) − DER(A) ≤ **.005** |
| G2 | speaker count | every case with a known speaker count: \|groups − truth\| does not increase vs A. Recorded raw-label evidence counts: a P53 different-speaker pair that the rule un-vetoes is a failure |
| G3 | repair | the 65.5-min meeting: host intro + conversation in one group and long60-part DER ≤ .060 |
| G4 | fidelity | rule A replay reproduces the saved grouping (no extra merges) — otherwise that case is reported as unreliable, not as a pass |
**Decision rule.** B ships only if G1–G3 pass on every case, at a site (stitcher / short-meeting policy) where it
was measured; the K4 pair is the same rule at both sites (the stitcher applies it per chunk), so a G2 failure
there blocks both. Otherwise production stays as is and the numbers + what C needs are reported.

## Amendment after the first run (first-run receipts kept as `bench-aba/run1-*`; gates and rules A/B/C unchanged)
The first run (65 turn sets, 29 with audio) showed harness gaps, fixed before the run reported below:
- fixtures: the 308 s E1 runs (same audio + 6 s tail), 66 s accept6 runs and partial sends are now matched by text
  (prefix-aware); the two overlap mixtures and the mic fixture are rebuilt from their recorded recipes under
  `bench-aba/fixtures/` so their exactly-one pairs can be replayed; incomplete references are flagged.
- **raw-label section added**: P53 kept, for all 27 clips, each raw label's centroid, every pair's alternation
  count and the truth relation. Rules A and B are recomputed on those exactly (rule A reproduces the recorded
  grouping); DER under B is taken from the recorded no-veto arm when the grouping is the same, else unmeasured.
- **rule V added — exploratory, NOT precommitted, never a basis for shipping here**: an alternation counts only
  if none of its ≥ 2 s turns disagrees (cosine < .46) with its own label's centroid; then one alternation vetoes
  as today. Motivation: rule C's first-run result (it splits real turns and creates extra speakers).
- every turn ≥ 2 s is audited against its own label (and truth-tagged where a complete reference exists).
- the two overlap mixtures get their true speaker count (3: the host is the same person in both sources); the
  second run had left it empty, which hid a rule-B count regression from G2 (`run2-*` receipts).

## Verdict (2026-10-01, run 3 = `bench-aba/results.json`, table in `bench-aba/table.md`)
**Rule B is rejected; production is unchanged.** It repairs the 65.5-min meeting but re-opens the failure the
veto was introduced for. Rule C as specified is rejected too. The exploratory rule V passes every replay gate
and is the candidate to measure next.

Scope: 179 saved files = **65 distinct turn sets** (56 one-call "short policy", 9 chunked "stitcher"), 47 with
audio on disk. In 55 of 65 no label pair has exactly one alternation, so A and B are the same program there.

| Rule | G1 no harm (36 scored) | G2 speaker count (47 with truth) | G3 65.5-min repair | Raw labels (P53, 27 clips) |
|---|---|---|---|---|
| A shipped | — | — | DER .166, host split | reproduces all 27 recorded groupings |
| B ≥ 2 alternations | replays pass; **raw: K4 s0 .221 → .330** | **fail**: overlap 0 dB 3 → 2 (truth 3); **raw: K4 s0 merges two different speakers (cosine .741)** | pass: .049, host one group | 23 unchanged; K2 s0 .382 → .216 (3 same-speaker merges); K3 s1 4 → 3 labels (same speaker, DER unmeasured); K6 s0 9 → 8 (truth unknown) |
| C split < .46, then A | **fail**: 3 cases worse (long60 .048 → .068, .042 → .060, .344 → .404) | **fail**: 13 cases move away (long60 5 → 6–7, 65.5-min 9 → 11, K6 7 → 11) | **fail**: .069 > .060 | unmeasured (needs raw words) |
| V voice-checked veto (exploratory) | pass | pass | pass: .049, host one group | unmeasured (needs raw words) |

Where the rules differ from A on replays: B changes 4 turn sets (65.5-min ×2 repaired; K6 `s12` run 7 → 6 groups,
DER .339 → .316; overlap 0 dB 3 → 2). V changes 3 (the same without the overlap regression).

Why C fails: the .46 floor does not separate. Of 1,093 turns whose speaker matches their label's, 2.8 % score
below .46 against their own label (p1 .30, minimum .08 — a 95 s turn that opens with another voice), and each one
becomes a new speaker; of 62 truly mislabelled turns only 42 % fall below it.

Replay fidelity (G4): rule A's replay merges two saved names in 5 turn sets and splits one in 1 (turn-level
centroids differ from the word-level ones the run used). In the 65.5-min case the extra merge (Speaker 8 +
Speaker 10) lies outside the scored long60 part; replay A gives DER .166 there against .165 measured.

**What rule V needs before it can ship** (it keeps "one alternation vetoes" and only asks that the alternation's
turns sound like their labels):
1. the raw-label check this bench cannot do — K4 s0's single alternation must stay a veto under V. That needs the
   provider's word-level output for the 8 synthetic meetings (about 80 audio-minutes; the cache that held it was
   in the removed `…-wt-gemini-live` worktree) and the same raw-level run for the real tune/test clips;
2. a decision on its only parameter (.46 was reused, not tuned) with that data;
3. a cost bound: it embeds each ≥ 2 s turn of an alternation; limiting it to pairs whose merge the veto would
   block (cosine ≥ .65) keeps it to a handful of embeddings per meeting;
4. V does not rename the 21 s of Acquired speech that carry the host's names in the 65.5-min meeting.
Unmeasured throughout: raw labels behind one saved name (assumption 5), real overlapped speech, mic lanes beyond
the count scan, and whether live meetings with late joiners reproduce the label reuse.
The prototype stays here (not deleted) because step 1 reuses `bench.py` unchanged.
