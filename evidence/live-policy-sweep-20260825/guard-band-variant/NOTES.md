# Guard-band 15/7.5 variant (owner-proposed) — measured 2026-08-25 ~17:10 EDT

Owner's idea: never publish text within 2.5 s of a decoded clip's edge; decode 15 s on a
7.5 s stride, own only the middle 10 s (W0 special-cased: owns [0,10] of [0,12.5] — the
meeting start has no leading cut-off). Consecutive owned regions overlap 2.5 s, reconciled
by exact-word anchor inside that edge-safe zone (fallback: zone midpoint).
Preregistration: `prototypes/streaming-diarization/live-policy-sweep-20260825/PREREGISTRATION-guard-band.md`;
harness: `guard_band_variant.py` (reuses the sweep's decoder/stitch/score stack verbatim).
Offline shadow, quiet GPU, one warm-up, one decoder session, fresh cache (checked in).

**Control:** `15_10_lexical_fresh` restitched from this session's own decodes reproduces
the sweep's recorded macro WER **exactly** (.1084025 vs .1084) — decoder warm-stable, so
arm differences below are geometry/policy, not decode flips.

## Macro (6 clips, same scorer as the sweep)

| arm | WER | TBSA | DER | matched-word spk | v2 recall | decode cost |
|---|---:|---:|---:|---:|---:|---:|
| 15/10 lexical (fresh) | **.1084** | .8885 | .1535 | **.9296** | **.9483** | 1.35× audio |
| guard_anchor (owner variant) | .1139 | **.8932** | **.1484** | .9212 | .9435 | 1.84× audio |
| guard_mid (ablation: no anchor) | .1230 | .8907 | .1472 | .9155 | .9367 | same decodes |

Per-case WER (guard_anchor vs 15/10 lex): mono .0973 = .0973; bill .1932 vs **.1705**;
keyu .1079 vs **.0863**; adam **.1337** vs .1375; jamie .0784 vs **.0714**;
rtfl **.0728** vs .0874.

## Preregistered decision

**FAILS both clauses**: macro WER higher (.1139 > .1084) AND two cases worse by > .02
(bill +.0227, keyu +.0216). The variant is not the better choice on the fixed rule.

## What the measurement teaches

1. **The edge-cut concern is real — and already solved more cheaply.** guard_anchor beats
   guard_mid everywhere (anchoring did 69/71 joins; hard midpoint cuts words), proving seam
   placement matters. But 15/10-lexical's `trim_prefix_by_text` already lands each seam
   where the two decodes' texts agree inside a 5 s overlap — cut words don't align, so
   edge-damaged text loses automatically. Hard guards then discard good context instead of
   letting alignment adjudicate it, and the 7.5 s stride adds ~33% more joins (83 vs 62),
   each a new seam risk with only a 2.5 s agreement zone.
2. **Where guards win is dense multi-speaker audio**: rtfl (4-speaker) .0728 vs .0874 and
   adam. Same pattern as the sweep's stable-anchor (rtfl .0728 identical) — on dense audio
   the decoder's edges are least reliable and conservatism pays. On clean interviews the
   guards throw away accuracy (bill/keyu −.022).
3. **The DER/TBSA win is extent, not attribution**: matched-word speaker accuracy (the
   campaign's honest speaker-text metric, plan §3.4) is LOWER for the variant (.9212 vs
   .9296) while DER is better — the guard geometry shifts segment extents, not who-said-what
   correctness.
4. Cost: 1.84× decoded audio vs 1.35× measured for 15/10 — the variant is more expensive
   and worse on the primary metric.

## Standing verdict (unchanged from the G4 addendum)

Keep production 10/10; fix the rolling normalization + refusal-stall first
(`../G4-root-cause/NOTES.md`); then the deployed-arm comparison. If a 15 s family arm is
promoted later, **15/10 lexical remains the candidate**; a guard/anchor hybrid is worth
revisiting only if multi-speaker corpora dominate the product's audio mix.
