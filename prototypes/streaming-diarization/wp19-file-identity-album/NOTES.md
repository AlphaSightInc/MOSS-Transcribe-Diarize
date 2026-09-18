# WP19 prototype — PASS, proceed to implementation

Question: can existing canonical album/matcher/sweep replace occurrence-to-occurrence
file matching without changing policy? Primitives: local utterances, sampled vectors,
canonical reference album, retained evidence ledger, speaker-only rewrite.
Invariants: same text/time/decode; unchanged live policy, live path, and saved schema.
Unknown: real attribution, long-file cost, saved-file enrollment integration.
Falsifier: perfect repeated voices split, or real six-minute file misses three voices.
Tools: WP18 fake cases isolate assignment arithmetic; pinned ONNX + retained WP18
real decoder outputs isolate identity from decoder nondeterminism.

Measured: perfect 1 voice x 3 windows -> 1; 2 x 3 -> 2. Six-minute real decode:
7 legacy identities -> 3 album identities, 0 unattributed; 62.863999 seconds including
all embeddings. Same-voice final-window scores .960366-.999999; policy unchanged.
State after every window is retained in evidence/mvpfix/wp19/prototype-*.json.
No truth-attribution claim yet; acceptance must score each segment against references.

One command: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <venv-python>
prototypes/streaming-diarization/wp19-file-identity-album/probe.py
The unattended JSON state driver substitutes for an interactive TUI, as in WP18.
After implementation the probe becomes a bench driver over the product resolver.

Enrollment extension prototype: reconstruct evidence from retained 48 kbps MP3 and
existing addressed speaker intervals, then apply the existing enrollment gate.
No new stored fields or policy. Falsifier: MP3 voice agreement lost or short evidence
admitted. Pinned encoder cosine PCM versus MP3 = .969589; 5 s eligible, .6 s refused.
The product uses the existing album admission and `_eligible_evidence` checks.

Prototype absorbed: probe.py now calls the product resolver and prints state.
Enrollment prototype removed after its result was recorded.
