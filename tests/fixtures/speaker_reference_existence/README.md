# Acoustic-existence negative control

Authoritative corpus (kept unchanged on `ga0@m4mbp`):

`/Users/ga0/Desktop/AI_Projects/LiveTranscribe/data/regression_fixtures/youtube_rtfl_first_90s/`

- `audio.wav`: SHA256 `dd48a724629aa05846a7c266218ee161083c60933e3c6a313540442536c95cbe`
- `reference.jsonl`: SHA256 `03734014d811a67fee2c19d6ef465fb9e8e4fb66a0e4eda5cb66a043b1f3dde1`, 26 rows

The prior 28-row reference contained two text lines proven absent from the waveform: the boss line
at 14.599–18.891 and “what's up?” at 72.278–73.694. The authoritative reference removes them.

The tracked ASR response is a blind pass over the audio at deployed source revision `3232375`.
The permanent regression gives the absent boss line valid v2 alignment and claimed-existence
metadata, and even uses it as its own matching lineage. Validation still fails because existence is
recomputed from the audio-hash-bound independent ASR evidence. The separate present fixture proves
a genuinely audible line passes the same gate.
