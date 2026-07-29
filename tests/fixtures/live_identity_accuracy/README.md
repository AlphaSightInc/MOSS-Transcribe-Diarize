# Labelled multi-speaker meetings for the live identity accuracy harness

ADR-0002 accepts the fingerprint album on a measured number. This directory is the only
labelled multi-speaker material in the repository, and `tests/live_identity_accuracy.py`
is what turns it into that number against the production live identity path.

## What each file holds

One `.npz` per meeting, `meet_k<K>_s<seed>.npz`, with four arrays:

| array | shape | meaning |
| --- | --- | --- |
| `truth` | `(utterances, 3)` | `(start_sec, end_sec, true_speaker_index)` for the whole meeting |
| `rows` | `(units, 6)` | one **evidence unit** -- one speaker's speech inside one span -- as `(span, true_speaker, start_sec, end_sec, eligible_duration_sec, eligible)` |
| `vecs` | `(eligible_units, 256)` | the 256-d embedding the **real** encoder produced for each eligible unit, unit-norm `float32`, in `rows` order |
| `k` | scalar | the number of true speakers in the cast |

`rows` is derivable from `truth` by replanning, and the harness does exactly that: it
replans and refuses the fixture unless the result matches `rows` unit for unit. `rows` is
therefore not a convenience -- it is the assertion that the ported span planner still agrees
with the plan the vectors were embedded under.

## Provenance

Synthesised from **LibriSpeech `dev-clean`** (CC BY 4.0) by the operator's
`prototypes/streaming-diarization/proto_ab_identity.py`, whose verdicts became
`docs/adr/0002-two-tier-diarization-fingerprint-album.md`. The prototype tree is excluded
from git (`.git/info/exclude`) because it also carries the corpus tarball and the ONNX
asset; this directory is the reviewed, tracked extract of its cache.

* **Cast** — `K ∈ {2, 3, 4, 6}` speakers × 2 seeds, 600 s per meeting, 30 % short
  backchannel turns and fast turn-taking so multi-speaker spans and sub-second evidence both
  occur. Those short turns are the condition the album exists to survive.
* **Encoder** — the production class `_OnnxWeSpeakerEmbedder` via
  `WeSpeakerResNet152LmAdapter`, loaded from this repository, with the pinned
  `voxceleb_resnet152_LM.onnx` (sha verified against `spec.state_sha256`). The vectors are
  the real encoder's; the harness substitutes only the forward pass, so the test suite needs
  no GPU-class asset.
* **Eligibility** — each interval is filtered individually at the deployed evidence floor
  `identity_provider.min_segment_samples` 8000 (0.5 s), matching
  `live_provider_bundle._speaker_intervals_by_label`. A unit with no surviving interval is
  `eligible = 0` and carries no vector.

Source cache sha256 (first 16), from `prototypes/streaming-diarization/data/cache_<name>.npz`:

| file | K | utterances | units | embedded | source cache sha256 |
| --- | --- | --- | --- | --- | --- |
| `meet_k2_s0.npz` | 2 | 201 | 279 | 252 | `314c956c39e1188e…` |
| `meet_k2_s1.npz` | 2 | 191 | 273 | 246 | `286729075b0a921b…` |
| `meet_k3_s0.npz` | 3 | 196 | 275 | 250 | `d6dcb580c1143fe1…` |
| `meet_k3_s1.npz` | 3 | 187 | 278 | 241 | `9fb6343cd5554163…` |
| `meet_k4_s0.npz` | 4 | 197 | 273 | 244 | `fb99b37e1c3a3433…` |
| `meet_k4_s1.npz` | 4 | 190 | 273 | 246 | `f9a7abacf963f5d1…` |
| `meet_k6_s0.npz` | 6 | 187 | 275 | 245 | `d4f9fef071501e97…` |
| `meet_k6_s1.npz` | 6 | 189 | 268 | 246 | `0e47d0eaf65e8b2d…` |

## Limits, carried from ADR-0002 §7

Read speech: no overlapped speech, no noise, no reverb, and in-span local diarization is
assumed correct. These meetings bound the identity layer in isolation. A real conversational
recording is still required before production sign-off, and MOSS's own measured hardware
limit -- a built-in laptop microphone cannot hear a second voice across a room -- means the
loop's live certification runs cannot substitute for one.
