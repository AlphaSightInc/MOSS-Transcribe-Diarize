# Human-audit attestation — Q2: 5m-acquired-coca-cola (2026-08-04)

Auditor: operator (direct listening). Original reference SHA-256 `41146f40c372…` (untouched).
New version: `reference-v2-human-20260804.jsonl`, SHA-256
`d2b92f1aff1df0a15b183205cc04246bc09097270a3445b3203d96d9fbb738fa`.
Cross-check instrument: blind fresh ASR at deployed `9089b332`.

## Operator findings → dispositions

Confirmed golden (no edit): "going to", "one", "now illegal", "product the real thing is",
"about the" — machine variants ("Jason"-style renderings: "1", "now-illegal", "product, the
thing, is") are the same single occurrences, not duplicates.

Machine hallucinations (not spoken; no action): "four-hour", "gonna" (actually Ben laughing),
"And about.", "fraction of the time. So onto".

Confirmed spoken but absent from golden (sparse coverage, documented only — most in unscored
gaps; brief interjections at window edges are sub-floor backchannels): "Ooh" (Ben), "Okay."
×2, "so" ×2, "Yes" (Ben), "Ooh" (David), David's "Always" before Ben's, "and I mean" before
"happiness", the ~116–162 s product-design passage (operator dictated fuller wording than the
machine caught, incl. "optimize it to maximize the rewards of ingesting it…"; preserved here
as spoken-content record), and "with just a few of your own production facilities" inside the
~217–238 s passage.

**Reference text edits (v2):**
1. Line 38: "the 1970s" → "the 70s"; "the 1980s" → "the 80s" (operator heard "70s"/"80s").
2. Line 40: trailing "of the world." deleted — audio clip ends right after "rest";
   text proven absent is deleted, never retimed (protocol).

Timing: all 19 timing-only flagged lines confirmed correct text, timestamps in-range;
high-word-rate flags adjudicated as genuine fast speech + coarse granularity.

**Case status: HUMAN-AUDITED — promotable** with v2 as the case reference at the next
corpus-manifest revision (vectors/caches derived from the reference will be rebuilt; m4mbp
master-corpus sync of v2 is a listed residual).
