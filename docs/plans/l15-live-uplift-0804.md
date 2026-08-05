# Campaign L1.5 — live-mode identity uplift on the audited corpus (draft for execution)

Date: 2026-08-04. Author: supervisor (delegated authority; operator directive: "make
breakthrough improvements in the live-mode"). Baseline: main `08f1426` (product tree ==
deployed `9089b332`). Predecessor: Stage-0 BLOCKED verdict + addendum (sealed), human-audit
attestations (docs/handoffs/human-audit/).

## 1. Revised R1/Stage-0 assessment under the audited references

1. **The BLOCKED verdict STANDS.** The v2 reference edits are word-level (five word fixes
   across two files); no timestamps or speaker windows changed, and identity scoring grades
   speaker windows, not words. Nothing in the audit refutes the holdout result.
2. **What the audit DOES change: the measurable corpus.** Before: 9 gated cases, all short,
   holdout near-saturated, zero 30-minute cases. After promotion: up to 17 gated cases
   including at least one certified 30-minute case (jamie-dimon; bill-ackman pending Q5) —
   the production-shaped class becomes measurable for the first time.
3. **The undervalued result:** the ledger-only control (bounded clustering + 5% rewrite
   budget over the vectors the live system ALREADY retains) gained ~+0.9 pp over production
   L1 on the blind holdout — equal to the full tape candidate, with NO tape, NO retention,
   NO finalizing lifecycle, NO new privacy surface. It was run as a control, never optimized,
   and never holdout-gated on its own merits. It is the cheapest credible live-mode win.
4. **Also banked and reusable:** lane-provenance separation measured +8.1 pp on the
   similar-voice counterfactual (prior prototype; dual-lane corpus exists on m4mbp);
   duration-adaptive margin finding (0.2 wins at 30 m, 0.1 safer short); the A3-proven
   lifecycle model (if ever needed); the planner-frame comparison rule; the D8 lesson.

## 2. Campaign L1.5 — three candidate families, no tape

Target: a measured, default-off upgrade to the EXISTING live sweep policy
(`LiveIdentitySweeper` / `SweepLedger.sweep()` — already runs mid-meeting and at finalize;
publishes through the existing `SweepRevision` → `LiveSession.revise_labels` seam, the exact
minimum seam the Stage-0 inventory identified). No new lifecycle, no tape, no retention.

Candidate families (each preregistered in its OWN commit BEFORE first run — D7 lesson):
- **F1 — ledger-only bounded clustering + rewrite budget** (promote the control to candidate;
  budget/thresholds swept on dev only, frozen before holdout).
- **F2 — lane-provenance prior**: weight identity evidence by capture lane (local-mic vs
  system) as a soft prior — never a hard key; validate against the m4mbp dual-lane corpus.
- **F3 — duration-adaptive margin**: sweep margin scheduled on elapsed meeting time.
F2/F3 may compose with F1 in a final preregistered combination arm.

Integrity requirements (review lessons, binding):
- **D8-safe inputs**: candidate runtime units derive ONLY from runtime-visible signals
  (production span planner over audio/ASR outputs); the golden-path audit covers the FULL
  evaluator→candidate input chain, with the reviewer's label-perturbation test as a red
  check (change truth labels → candidate runtime shape must NOT change).
- Frozen dev/validation/holdout splits over the ENLARGED corpus; holdout must include a
  certified 30-minute case; opened once, after family+threshold freeze.
- Same production-planned frame for all arms; L1 baseline = A2's calibrated instrument.
- Gates (predeclared): candidate beats L1 by ≥1.0 pp mean on the target-error subset; no
  gated case regresses >0.5 pp; FP-speaker-seconds/DER not worse anywhere; determinism;
  two-sided mapping preserved; sweep compute stays within the existing live budget
  (sweep p95 wall-time on 30-m cases ≤ 2× current; no new model, no GPU).
- Supervisor rulings archived at ruling time; independent adversarial review of the final
  package before any keeper merge (both monitors' lessons now standing practice).

## 3. Stages

- **L0 — corpus close (in flight)**: Q3/Q5 diffs + operator confirmations; manifest revision
  promoting audited cases (v2 references pinned); cache rebuilds; validators green.
- **L1 — bench campaign** (prototype-only, `prototypes/streaming-diarization/l15/`):
  families F1→F3 per above; verdict `READY_FOR_PRODUCT` or `BLOCKED` with sealed evidence.
- **L2p — product implementation** (only on READY + independent review): sweep-policy
  upgrade behind a hash-covered default-off config; focused/full/stress gates; keeper;
  deploy dark; paired live-mode measurement (L2-off vs on, F1-style user-visible p95
  unchanged); enable = separate decision with operator visibility.
- STOP conditions: any gate miss after one preregistered optimization pass per family;
  scope creep toward tape/lifecycle/new models; evidence of input leakage.

## 4. Why this can be the breakthrough

The live product's weakest visible behavior is mislabeled speakers accumulating in long
meetings — exactly what the +0.9 pp ledger-only result already dented blind, what lane
provenance attacks structurally on the hardest (similar-voice) class, and what the
duration-adaptive margin addresses at the 30-minute horizon. All three compose inside the
sweep the system already runs, publishing through the seam the architecture already owns.
Small surface, measured gains, live-mode by construction.
