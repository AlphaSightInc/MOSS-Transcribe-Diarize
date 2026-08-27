# Preregistration — guard-band 15 s / 7.5 s rolling variant (owner-proposed), 2026-08-25

Written before any decode. Owner's hypothesis: text near a decoded clip's edges is
unreliable (cut-off words), so publish only each window's middle. Proposed geometry
(absolute time): W0 decodes [0, 12.5] and owns [0, 10] (meeting start has no leading
cut-off, so no leading guard); Wk (k ≥ 1) decodes [7.5k − 2.5, 7.5k + 12.5] and owns
[7.5k, 7.5k + 10]. Every owned word sits ≥ 2.5 s from both decode edges (except W0's
leading region, which is the start of audio). Consecutive owned regions overlap by 2.5 s —
an agreement zone where BOTH sides are edge-safe.

## Arms (one decoder session, one scorer — `surface.score_surface`, the sweep's own)

1. `guard_anchor` — owner geometry; words kept if their midpoint lies in the owned region;
   the 2.5 s owned-overlap is reconciled by the sweep's exact-word anchor rule (`align`,
   drift ≤ 0.75 s, anchor nearest zone midpoint; fallback: cut at zone midpoint).
2. `guard_mid` — same trims, hard cut at zone midpoint (isolates the anchor's value).
3. `15_10_lexical_fresh` — the sweep's own `lexical_stitch` over THIS session's fresh
   15/10 decodes (controls decoder-flip noise between tables).
4. Recorded baselines carried over, not re-run: deployed 10/10 pre-stop-settled and the
   sweep's recorded 15/10 arms (`moss-recovered/moss-results.json`).

## Corpus and inputs

The sweep's six referenced clips (`evidence/live-policy-sweep-20260825/corpus/`),
pass-A actual sessions supplying each case's base surface and speaker timeline (pass A and
pass B actuals were byte-stable per the sweep). One discarded warm-up decode, then
strictly sequential decodes, fresh cache, quiet GPU (verified before start).

## Decision rule (fixed now)

The owner variant is "better" iff `guard_anchor` macro WER < `15_10_lexical_fresh` macro
WER AND no case is worse by > .02 absolute WER. DER / TBSA / matched-word speaker
accuracy / v2 recall reported beside, never substituted. Decode cost (requests, decoded
audio ×, wall) reported. Predictions: P1 guard arms beat drained 10/10 everywhere rolling
covers; P2 the first-window special case prevents any [0, 2.5] regression; P3 cost lands
≈ 1.9–2.0× audio vs 15/10's 1.5×.

## Caveats (same class as the sweep's shadows)

Offline shadow: no session refusal predicate, no deployed queueing; results rank
geometries, they do not certify deployment. The G4 eviction bug applies to ANY deployed
geometry until fixed.
