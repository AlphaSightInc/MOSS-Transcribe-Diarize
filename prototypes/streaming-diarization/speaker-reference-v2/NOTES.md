# Verdict — 2026-08-03 corpus-truth correction

The first forced-aligned candidate v2 (`7c3020b8…`) is rejected as a certification reference.
Forced alignment assigns time to every supplied token and therefore cannot establish that a
transcript line exists in the waveform. A fabricated 46th line with valid alignment metadata
passed the old validator.

A transcript-independent ASR pass on the authoritative 90-second negative control measured:

- known-present opening line: score 1.000;
- absent boss line at 14.599–18.891: score 0.200;
- absent “what's up?” line: score 0.000.

The deletion-capable local token-F1 gate uses `>=0.65` with a +/-1.5-second acoustic window and may
omit up to four proposed reference tokens. The threshold is below the minimum Acquired Alphabet
candidate score (0.714) and above the negative-control maximum (0.200). It is recomputed from a
hash-bound independent-ASR evidence file; claimed per-row metadata cannot override it.

The one-off acoustic scorer was deleted after the verdict. Production
`acoustic_existence_evaluation` and its negative-control tests now own this rule; this packet is
retained under the standing streaming-diarization bench only for audit and reproduction.

All 45 Acquired candidate rows passed the acoustic gate. The operator audit disposition is frozen:
R1/R2/R3/R5/R6 are present; R4 removes the unproven lexical prefix and keeps David activity from
161.8–163.411, with 161.8–162.4 recorded as uncertain nonlexical vocalization. The candidate,
superseded C3/C4 evidence, v1, and authoritative 90-second golden remain preserved.
