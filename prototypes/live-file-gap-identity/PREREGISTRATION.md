# PREREGISTRATION — live-vs-file gap, identity component (H4)

Written **before** any lever was run. Baseline numbers below come from Phase-1 diagnosis of the
frozen baseline `remeasure-20260824T160130`; lever numbers are what this prototype produces.

## Question

The live arm assigns speaker identity per ~2.5 s frozen span via a causal fingerprint album
(WeSpeaker, `S00` = abstention). Live trio-mean speaker_accuracy is **.8236** vs file **.8979**
(DER .1764 vs .1021). Speaker confusion is the secondary component of the gap.

**Can an identity-only lever, applied offline to cached/recomputed embeddings with no model
decodes, close a material part of that gap?** Two levers:

* **C1 — merged-evidence assignment.** Assign identity once per *endpoint-merged window*
  (consecutive published segments joined across span seams while the inter-segment gap stays
  below a threshold, accumulating evidence up to a window cap) instead of once per 2.5 s span.
  Prediction: sub-floor fragments that are today unembeddable inherit a confident neighbour's
  identity, so `S00` seconds fall.
* **C2 — sweep activation.** The minimal change that lets the existing retrospective sweep fire
  on today's evidence. Three sub-levers, measured separately:
  * C2a scheduling — `SWEEP_INTERVAL_SECONDS` 60 → 20 (cadence sweeps during the meeting).
  * C2b margin — sweep-only `min_match_margin` 0.10 → 0.05.
  * C2c ledger floor — record sub-floor fragments in the sweep ledger (embed below
    `min_segment_samples`) so the sweep can address the units it is blind to today.

## Preregistered gates (from the task brief)

* **G1** — live speaker_accuracy ≥ **.89** trio mean (closes ≥ half of .8236 → .8979), with
  **zero regression on any case**.
* **G2** — `S00` seconds reduced ≥ **50 %**, with **no new confusion**.

## Preregistered ceiling — G1 is unreachable by construction

Measured in Phase 1, before any lever: relabelling **every** live hypothesis segment to its
overlap-optimal reference speaker (a perfect identity oracle, extents untouched) gives trio-mean
speaker_accuracy **.8498**, DER **.1502**. Relabelling only the `S00` segments gives **.8437**.

The residual .8498 → .8979 is **not** identity: it is `missed_speaker_seconds` (live 26.30 s vs
file 16.23 s across the trio), which no relabelling can move. **G1 (.89) therefore cannot be met
by any identity lever, correct or oracular.** This is recorded here so the gates are not
retro-fitted after the fact.

Consequently the prototype is judged against:

* **G1′ (reachable-headroom form of G1)** — fraction of the identity-reachable headroom
  (.8236 → .8498, i.e. **+.0262**) that the lever captures, with zero per-case regression.
  A lever is *interesting* at ≥ 50 % (≥ +.0131, trio mean ≥ .8367).
* **G2** — unchanged: `S00` seconds −50 % with no new confusion.

`G1` itself is reported as **FAIL — unreachable**, with the ceiling as the evidence.

## Metric-validity caveat (adopted from the timing/H5 analysis, and independently confirmed here)

The corpus references are coarse, gapless turn intervals on **integer-second** boundaries, so
duration-overlap metrics partly measure emitted *extent* rather than label *correctness*.
Word-level check of the two live segments whose label disagrees with the reference
(`lex_bill_ackman` span 16 "That you're.", `lex_keyu_jin` span 14 "Authority.") shows both words
belong, **in the reference's own transcript text**, to the speaker the live arm named — the
reference turn boundary is 0.5–0.6 s late/early. True live misassignment in the trio is
therefore **0.00 s**.

All numbers this prototype reports are **label-driven**: every lever changes labels only, never
segment start/end times, so no gain reported here is extent-driven. `miss` and `false_alarm` are
invariant under every lever and are not claimed.

## Falsifiable predictions

1. C1 reduces `S00` seconds by ≥ 50 % (8 of 11 `S00` segments are sub-floor fragments with a
   confident neighbour within 0.35 s).
2. C2a produces **zero** additional corrections (the album grows monotonically; the terminal
   sweep already sees the final album — scheduling is not the blocker).
3. C2b produces exactly **one** correction on the trio (`lex_bill_ackman` span 13,
   scores .424/.379, margin .045 < .10), worth ~2.3 s of correctly-relabelled speech.
4. No lever reaches G1; the best lever lands between .8236 and .8498.

## Run

```bash
.venv/bin/python prototypes/live-file-gap-identity/proto_identity_levers.py
```
