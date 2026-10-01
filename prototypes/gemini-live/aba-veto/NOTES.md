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
