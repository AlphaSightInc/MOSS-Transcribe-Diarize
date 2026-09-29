# P4 — live speaker-identity collapse: mechanism and smallest guard (throwaway prototype)

## Contract before code

**Question.** With identical cached Gemini responses, the product-equivalent C1 overlap + C3 WeSpeaker
(E .46 / W .60) + 2 s birth registry collapses identity on some window schedules (Bill30m S15/L120
DER .510, S30/L90 .487; long60 S30/L90 .350; S20/L60 Bill .402; S20/L120 Bill .232 / long60 .301) while
S15/L90 and S15/L180 pass. With after-Stop clean-up OFF by default, a live collapse becomes the saved
transcript. Why does it collapse, and what is the smallest guard?

**Primitives.** Cached Gemini window observations + cached per-label WeSpeaker vectors (P61/P65 receipts);
the bench registry (`continuity/registry.py`, product parity checked in continuity/NOTES.md) replayed by
`continuity/measure.evaluate`; first-committed view scored by `c4.score_view` (H1-exact on accept6,
`common.score` on long form). Gemini 3.5 Transcribe is near-deterministic on identical audio, so
robustness is argued across schedules/recordings, not repeat draws.

**Invariants.** $0 (uncached window raises); registry thresholds unchanged; the guard may only change
which existing meeting ID a window label maps to.

**Falsifier / decision rule.** Adopt iff the guard fixes (IDs ≤ true+1 and DER ≤ .10) ≥ 3 of the
collapsed cases AND worsens no passing case (A0 S15/L180, A2 S15/L90 on accept6, E1, Bill30m, long60)
by > +.01 DER or > +1 ID.

**Tool decision.** Window-by-window replay with reference-dominant speaker per label exposes the first
wrong mapping; a 2-parameter sweep (T, M) bounds sensitivity.

## Run

```
cd <worktree>; PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
  prototypes/gemini-live/guard/run.py diagnose A5bill A3long60 S20L60bill   # identity trace
... run.py sweep     # v1 veto, T∈{.46,.60} × M∈{.05,.20}, all cases
```
Receipts: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P65/guard/` (`diagnose-*.txt`, `sweep.json`,
`variant-noforcedbirth.*`).

## Results (2026-09-29)

**Mechanism 1 — swap self-reinforced by overlap (5 of 6 collapses).** Example A5 Bill, window 61
[795,915] s: Gemini's own labels drift inside the window (spk:0 = 12 s Bill early + 19 s Lex late;
spk:1 = 16 s Lex early + 47 s Bill late). Overlap support comes only from the old region (spk:0→M1
27.3 s, spk:1→M1 30.2 s, spk:1→M2 16.3 s), so Hungarian picks spk:0→M1/spk:1→M2 and the newest
stride is committed swapped. From window 62 the swapped rows ARE the overlap evidence (spk:0 Bill→M2
support 43.2 s) although fingerprints disagree strongly (cos M1 .821 vs assigned M2 .366); the error
then persists and a new ID (M3) is born for the displaced voice. long60 S30/L90 fails the same way at
window 30 (Bill label→M2 cos .43 vs M1 .79; Lex label→M1 cos .78 vs M2 .42).

**Mechanism 2 — spurious birth (S20/L60 Bill, window 36).** A 2.0 s Lex reply outside the overlap
region has no ≥2 s span (no vector) and no overlap support → the 2 s birth rule creates M3; later
windows anchor Lex to M3 by overlap and no contradiction is visible (M3's centroid is also Lex).

**Guard (v1 fingerprint veto).** After the overlap-first assignment, a label with a vector whose
assigned ID has a centroid is *contested* when another ID's centroid cosine is ≥ T and exceeds the
assigned ID's cosine by ≥ M. If any label is contested, re-solve that window's assignment with
fingerprint weights (cos ≥ T, else 0) for labels that have vectors; labels without vectors keep their
original weights. Chosen T = .46 (the existing C3 threshold — no new threshold), M = .20.

| Case (first-committed) | Before DER / IDs | After (T .46, M .20) |
|---|---:|---:|
| A5 S15/L120 Bill30m (true 2) | .510 / 3 | **.079 / 3** |
| A3 S30/L90 Bill30m | .487 / 3 | **.051 / 2** |
| A3 S30/L90 long60 (true 5) | .350 / 6 | **.046 / 5** |
| S20/L60 Bill30m | .402 / 3 | **.097 / 3** |
| S20/L120 Bill30m | .232 / 2 | **.068 / 3** |
| S20/L120 long60 | .301 / 6 | **.060 / 6** |
| A0 S15/L180 Bill / long60 / E1 | .056/2, .048/5, 3 IDs | unchanged (0 vetoes) |
| A0 accept6 macro (H1 exact) | .0985 | **.0846** (Adam Frank .117→.034) |
| A2 S15/L90 Bill / long60 | .053/2, .046/5 | .053/3, .046/6 (+1 ID: one 10.6 s ID; 3 vetoes in 120/173 windows) |
| A2 accept6 macro / E1 | .1014 / 3 | .1014 / 3 |

M ∈ {.05,.20} identical at T .46; T .60 M .05 fails S20/L120 long60 (.146/7).
A "v2" (unknown centroid counts as 0) fixed S20/L60 DER to .051 but gave 4 IDs (fails). A
"no-forced-birth" refinement removed A2's extra ID but failed S20/L120 long60 (.146) and cost
+.008/+.006 DER on A2 Bill/long60 — rejected.

**Verdict: ADOPT v1 (T .46 = E, M .20).** Fixes 6/6 cached collapses; no passing case worse than
+1 ID / +0.00 DER. Mechanism 2 is only partly addressed (S20/L60 still .097 — passes the bar).

**Production shape.** `moss_transcribe_diarize/app/gemini_continuity_registry.py` `observe_window`:
between `linear_sum_assignment` and the birth loop, compute `_cosine(group_vectors[label],
self._centroids[mid])` for mapped labels; if any label is contested, re-solve with fingerprint weights
for labels in `group_vectors`. One new constant: veto margin .20 (T reuses `embedding_threshold`).

**Risks / unmeasured.** All 6 collapses come from one voice pair (Bill/Lex; long60 contains the Bill
30m audio), so generality across meetings is unmeasured. The guard stops propagation; the first
swapped stride (≤ S seconds) is still committed. Depends on fingerprint quality: conference-compressed
audio, similar voices, mic-lane echo and several local people (G1 O2 30 s windows) are unmeasured.
A2 gains one short spurious ID (10.6 s) on the Bill audio.
