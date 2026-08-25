# PROTOTYPE NOTES — live-vs-file gap, identity component (H4)

Throwaway. Preregistered question and gates: `PREREGISTRATION.md`. Delete once the verdict is
copied wherever the H4 decision lands.

Command (one, ~3 min, no model decodes, no live session, no deployed backend):

```bash
.venv/bin/python prototypes/live-file-gap-identity/proto_identity_levers.py
```

Inputs: the frozen baseline `remeasure-20260824T160130` traces + the 1-min corpus + the
production WeSpeaker ONNX. Outputs: `proto_identity_levers.results.json`.

---

## VERDICT: **G1 FAIL (unreachable). G1′ PASS, G2 PASS for `C1adopt + C2b`.**

Identity is **not** where the live-vs-file gap lives, and identity work on this corpus is
*saturated* by one small change pair.

### Replay fidelity (the thing that makes every number below trustworthy)

The offline replay reproduces the deployed run's published labels **exactly**: 30/30, 28/28,
26/26 segments across the trio, using production `assign_speakers` / `FingerprintAlbum` /
`LiveIdentitySweeper` / `sweep` and the production encoder over the exact published intervals.
The baseline replay also reproduces the deployed sweep's inertness (0 corrections, identical
dispositions). Secondary case `acquired_jamie_dimon`: 31/32 (see the anomaly below).

### Levers (trio mean; every lever is label-only — extents, and therefore `miss`, never move)

| lever | spk_acc | Δ | DER | conf_s | S00_s | S00_n | G1′ headroom |
|---|---|---|---|---|---|---|---|
| baseline (deployed) | .8236 | — | .1764 | 1.82 | 1.37 | 3.67 | — |
| C1-merged (window merge) | .8265 | +.0029 | .1735 | 1.64 | 0.35 | 0.67 | 11 % **REGRESSION** |
| C1adopt-prev (causal) | .8304 | +.0068 | .1696 | 1.41 | 0.85 | 1.33 | 26 % |
| C1adopt-both | .8336 | +.0099 | .1664 | 1.22 | 0.77 | 1.00 | 38 % |
| C2a cadence 60→20 s | .8236 | **+.0000** | .1764 | 1.82 | 1.37 | 3.67 | 0 % |
| C2b sweep margin .10→.05 | .8337 | +.0101 | .1663 | 1.21 | 0.60 | 2.67 | 39 % |
| C2c ledger floor → 0 | .8254 | +.0018 | .1746 | 1.71 | 1.26 | 3.33 | 7 % |
| C2b + C2c | .8356 | +.0119 | .1644 | 1.10 | 0.49 | 2.33 | 46 % |
| **C1adopt + C2b** | **.8437** | **+.0201** | **.1563** | **0.61** | **0.00** | **0.00** | **77 %** |
| C1adopt-prev + C2b (fully causal) | .8405 | +.0169 | .1595 | 0.80 | 0.08 | 0.33 | 65 % |
| ORACLE-labels (ceiling) | .8498 | +.0262 | .1502 | 0.25 | 0.00 | 0.00 | 100 % |

`missed_speaker_seconds` is **8.77 s/case in every row**, including the oracle. That is the whole
story: the file arm's .8979 is unreachable from here because .0542 of the .0743 gap is speech the
live arm never emitted.

### Gate results

* **G1 (≥ .89 trio, no regression) — FAIL, and unreachable.** The perfect-label ceiling is
  **.8498**. No identity lever, correct or oracular, can reach .89. Preregistered before running.
* **G1′ (≥ 50 % of the .8236 → .8498 headroom) — PASS** for `C1adopt+C2b` (77 %), `C1adopt-prev+C2b`
  (65 %). FAIL for every single lever alone.
* **G2 (S00 −50 %, no new confusion) — PASS** for `C1adopt+C2b` (S00 1.37 s → **0.00 s**, −100 %;
  confusion falls on *all three* cases: 3.65→1.28, 1.02→0.00, 0.78→0.56 s), `C1adopt-prev+C2b`
  (−94 %), `C2b` (−56 %), `C2b+C2c` (−65 %).
* **Zero regression**, per case, for every `adopt`/`C2b` combination. Only `C1-merged` regresses.

**All 11 relabels `C1adopt+C2b` makes are correct** against the reference (8 by adoption, 3 by the
sweep). Zero wrong relabels, zero adoption conflicts.

---

## What each lever taught us

### C1-merged — measured and **rejected**

Assigning over endpoint-merged windows (gap ≤ 0.35 s, cap 10 s) does cut `S00` (1.37 → 0.35 s) but
**collapses `lex_bill_ackman` to one canonical speaker** (`canonical=1`, 4 × `kept_ambiguous`):
the 0.02 s seam between span 12 and span 13 merges Lex's 30.0–32.5 s turn with Bill's 33.0 s turn
into one blended window, so the second voice is never born. Accuracy regresses .7765 → .7645 and
confusion *rises* 3.65 → 4.37 s. **A merge rule with no speaker-change guard is worse than the
per-span policy it replaces.** This is why C1 was refined rather than shipped.

### C1adopt — the refinement that works

Only a unit the **evidence floor** silenced (zero embeddable speech, so the album was never asked)
adopts its nearest labelled neighbour's identity, if that neighbour is within 0.6 s (the endpoint
silence split). A unit that *had* evidence and was declined keeps its abstention — an abstention is
a decision, not a hole in the evidence. 8/8 fragments adopted, 8/8 correct, 0 conflicts. Cost: a
label rule, **no extra embedding, no extra decode**. The `both`-sided form needs the *next*
labelled segment (≈ 1 span ≈ 2.5 s late, or ride the existing label-revision publication path);
the `prev`-only form is fully causal at zero added latency and still captures 65 % of the headroom.

### C2a — scheduling is **not** the blocker (prediction confirmed exactly)

`SWEEP_INTERVAL_SECONDS` is 60.0 and `maybe_sweep` is paced by the *span's start*, so in a 60 s clip
the maximum meeting time reached is 57.5 s and **no cadence sweep ever fires** — the one sweep that
runs is `finalize_identity`'s terminal sweep. Dropping the interval to 20 s fires two extra sweeps
per case and proposes **zero** additional corrections: the album only grows, so the terminal sweep
already sees the strongest album there will ever be. Cadence changes are worthless here.

### C2b — the one correction the sweep was one hair away from making

`lex_bill_ackman` span 13 (32.50–34.95 s, the only abstained span in the trio) scores **.435 vs
speaker-0001 (Bill, correct)** and **.379 vs speaker-0002** against the final album. Both clear
`min_match_score` .35; the margin is **.056 < .10**, so `assign_speakers` raises
`ambiguous_identity` and the sweep answers `kept_ambiguous` — the same ruling the live path made at
.424/.379. Relaxing the **sweep's** margin to .05 (the live path untouched) fires exactly one
correction, moves 2.32 s of speech from `S00` to the right speaker, and lifts that case
.7765 → .8068. **Small sample: one correction on one case.** Ship only behind a green
`tests/live_identity_accuracy.py` 9-clip run — the settled 95.2 % album+sweep result was measured
at margin .10 and must not move.

### C2c — the sweep's ledger is blind to the units that went wrong

**9 of the 11 `S00` segments in the trio are shorter than the 0.5 s evidence floor, so they were
never embedded, never entered the sweep ledger, and are structurally invisible to the sweep.** That
is the real reason the sweep is inert, and it is duration-independent — it explains the 5-minute run
reproducing `label_revision_version = 0` just as well as the 60 s runs. Recording them anyway
(embedding below the floor, ledger-only, live path byte-identical) buys almost nothing on its own
(+.0018): the fragments mostly score below `min_match_score` and come back `kept_unmatched`. Two
further facts fell out of it:

* The production frontend **cannot embed below ≈ 0.12 s at all** — it raises
  `Tier B embeddings are not finite unit vectors` (measured: 0.04/0.06/0.08/0.10 s fail, 0.12 s and
  up succeed). `lex_javier_milei`'s 0.06 s `S00` fragment is physically unembeddable.
* Lowering the ledger floor is therefore strictly worse than the adoption rule for the same job.

---

## Flagged anomaly — a sweep correction that did **not** reach the scored artifact

For the trio the `identity_finalized` service event reports `{version 0, spans 0, units 0}`, which
matches this prototype's replay: the sweep genuinely proposed nothing, and
`label_revision_version = 0` is honest.

For the secondary case `acquired_jamie_dimon` the same event reports
**`{identity_revision_version: 1, identity_revision_spans: 1, identity_revision_units: 1,
identity_revision_refusals: {}}`** — a revision was computed *and applied* — yet the `terminal`
snapshot in the same trace carries `session.label_revision_version: 0` and `revised_transcript:
null` on every committed span, and the scored hypothesis still shows the uncorrected `S00`
(`[15.76,16.46] "And as you all know,"`, exactly the correction this prototype's replay makes).

So `label_revision_version = 0` in a trace is **not** by itself proof the sweep found nothing, and
any sweep fix measured end-to-end may not show up in the artifact at all. Resolve this before
spending effort on C2b. Not investigated further here (out of H4 scope, secondary case, read-only
constraint); the evidence above is the whole of it.

---

## Recommendation

1. **Stop treating identity as a live-gap lever.** The identity ceiling is +.0262 speaker_accuracy
   (35 % of the .0743 DER gap); the other 65 % is missed speech and does not move.
2. If identity is worked anyway, the whole prize is captured by **`C1adopt-prev` (causal fragment
   adoption)** — a label rule, no new compute, no latency — optionally plus the `both`-sided form
   ridden on the existing label-revision path. That alone is +.0068/+.0099 and −44 % `S00`.
3. **`C2b` (sweep-only margin .10 → .05) is one constant** and is the other half of the best result,
   but rests on a single correction on a single case. Gate it on the 9-clip golden bench.
4. **Fix the revision-visibility anomaly first**, or a sweep change cannot be measured honestly.
5. Do **not** ship window merging without a speaker-change guard.
