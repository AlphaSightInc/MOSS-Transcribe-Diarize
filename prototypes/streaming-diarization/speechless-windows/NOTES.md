# Empty terminal windows

Question: distinguish a legitimate empty response to speechless PCM from a failed decode of speech.
Primitives: exact window PCM, empty decoder outcome, VAD voiced sample fraction, window diagnostics. PCM determines speech independently of decoder output; the result records the classification independently of identity/stitching.
Invariants: only genuinely empty output is eligible; any detected speech at/above threshold remains failure; VAD unavailable/unreadable PCM fails closed; successful text, identity policy, QUALITY_BOUNDS, and 150/120 geometry unchanged.
Assumptions/unknowns: VAD is a detector, not ground truth; quiet/distant speech can be missed. Use existing WebRTC dependency, least-aggressive mode 0, 20ms frames, threshold strictly below 0.0001 (0.01%). At 150s a single voiced full frame exceeds this threshold. No new dependency or operator policy knob.
Falsifier: silence fails classification, or real/brief speech embedded in silence is classified speechless. Tool: PCM probe measures this cheaply before any production edit; real decoder calls cannot establish whether audio was speechless independently of that decoder.

Run from repo root:
`.venv/bin/python prototypes/streaming-diarization/speechless-windows/measure.py --speech /path/to/mono_javier_intro_50s/audio.wav`

Measured before implementation: see results.json (actual human Javier introduction corpus). 150s silence and partial-frame silence classify speechless; human speech, human speech plus long silence, and one second of human audio surrounded by silence remain speech-present. ~10ms VAD overhead per 150s window on this Mac. Initial fixture-only probe also passed, but that fixture's human provenance is unverified; it is not the basis of the human-speech claim.

Tail handling: zero-pad only the final incomplete 20ms frame for the VAD call; count only actual input samples in numerator and denominator. New detector per window avoids carrying speech hangover from another window. Inspect only empty responses; do not skip decoding ahead of time. Absorb the same primitive into WindowedRunner and retain this opt-in measurement bench.

Post-implementation: production-results.json records agreement between the independent PCM probe and the actual WindowedRunner classifier on all five cases. Integration regressions additionally run the real window extractor, checkpoint store, terminal finalizer, and session publication; only decoder answers are controlled. See docs/audits/speechless-terminal-windows-20260911.md.
