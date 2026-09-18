# WP16 prototype verdict

Question: do real file/URL meetings reach truthful saved results and failures at scale?
Initial contract falsified: 10 s of exact PCM zeros completed with 32 invented words,
no notice (silence.wav.json). Export agreement alone does not establish accuracy.

Correction question: can the existing exact-zero PCM predicate distinguish that input
from any signal at the File dispatch boundary, leaving the shared decoder unchanged?
Five real WAV probes passed: all-zero true; speech, one-bit quiet signal, last-sample
signal, 30-minute speech false. See silence-prototype.jsonl. This supports an ingestion
fix using the existing predicate, not a new threshold or decoder/window policy.
Primitives: nonempty normalized PCM, exact-zero fact, dispatch decision, saved outcome.
Invariant: any nonzero PCM reaches unchanged decode; empty/damaged media still fails.
Falsifier: one-bit signal suppressed, zero-byte input accepted as speechless, or a
nonempty zero mix invokes the runner. Regression tests must exercise those boundaries.

The real-browser runner replaces the skill's interactive TUI because the brief explicitly
requires browser/persistence evidence. Scratch databases, media and profiles remain under
.wp16runtime. Final measurements and failed attempts are recorded in the evidence NOTES.

Capacity correction prototype: a real 177,185,845,248-byte sparse File spent >60 s
preparing its multipart submission without a browser response. The server's header-only
control returned 507 with zero body bytes and zero meetings. A browser File.size -> tiny
metadata GET against the existing admission policy returned 507 in 1.76 ms; 64,078 bytes
were accepted in 3.58 ms. Verdict supports metadata preflight. No new ceiling, reservation,
threshold or lifecycle decision. The authoritative multipart admission remains mandatory;
a positive preflight cannot promise future disk capacity. Falsifier: body sent after
refusal, meeting created during preflight, or actual admission bypassed after success.
