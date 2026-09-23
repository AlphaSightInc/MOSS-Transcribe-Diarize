# H2-B un-park and B2 retention

Structural question: can the quarantined Account DB supply the H1 settled speaker intervals, and can the quality producer retain those intervals for the next run without retaining content?

Minimum primitives: read-only DB transcript rows, frozen host reference JSONL, production `calculate_diarization`, the existing quality capture and projection seams.

Invariants: frozen six cases/two passes; unchanged scorer, macro, validator, bounds, and reference bytes; no words, text, audio, secrets, or real decoder requests in outputs.

Assumptions/unknowns: DB stores one latest terminal document per meeting; creation order plus durations bind the 24 quality meetings. Pre-Stop settled snapshots may have been overwritten. Host export may omit WAV bytes required for reference-speech DER.

Falsifier: a DB final replay that cannot reproduce the retained final DER and segment counts invalidates session binding; a retention field that changes macro or contains content invalidates B2.

Tools: read-only SQLite and SHA-256 establish source custody and binding; production scorers establish numeric attribution; focused RED/GREEN and full backend/bundle test product seam and regression risk.
