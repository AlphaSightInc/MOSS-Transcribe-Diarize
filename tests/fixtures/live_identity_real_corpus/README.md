# Acquired Alphabet five-minute identity fixture

`acquired_alphabet_5m.npz` caches the production WeSpeaker ResNet152-LM vectors produced
by `scripts/ralph-afk/live-identity-real-corpus.py` for the exact clause-11 corpus. The test
harness replans the reference and refuses the fixture if production would select different
evidence intervals.

- audio: `prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/audio.wav`
- audio SHA-256: `333b1e50b05d5dc888a6bdb4dc82f1c429e0e9c5a0b1df0cf115c2215eb394fb`
- reference: `prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/reference.jsonl`
- reference SHA-256: `27c9b96e86cce3be86a3ce06dd64c1710e2c94e72a01c30339e953db94b8ebbe`
- identity asset SHA-256: `5b734353b4b410e222bbd124dd095537642237ad895727d18a3b9fee330262a8`
- fixture SHA-256: `b7bdd7d10623a31f04be35b5ac044c7d88f40cd78ec60d2825de3a20bd17d9e3`
- truth speaker order: David, Ben
- rows/vectors: 55/47

The fixture is an identity-layer test, not a replacement for the live clause-11 capture.
