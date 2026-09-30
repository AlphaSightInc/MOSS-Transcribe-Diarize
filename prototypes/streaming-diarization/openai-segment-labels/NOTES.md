# OpenAI-compatible labels through the production identity paths (WP-F, 2026-09-29)

**Question.** A non-diarizing OpenAI-compatible model returns segments without speakers. Under J1 each
segment gets its own provisional label and local WeSpeaker linking must join voices. Does the production
composition (live: `ContinuityRegistry` + `WeSpeakerWindowEmbeddings`, 90 s context / 15 s refresh;
File: `GeminiFileRunner` → `FinalWordPolicy`) recover speakers? Does a short-segment rule help? Does
placing timeless text on voiced frames (vs uniform time) matter for the production word gate?

**Falsifiers.** Per-segment File output with K_out ≈ K and accuracy ≈ oracle (no fragmentation);
attach-short improving accuracy on both paths; uniform placement surviving the gate as well as voiced.

**Command.** `<venv python> proto_segment_labels.py` (File) and `… --live` (live), production pinned
ONNX, 10 golden clips (6 × 60 s, 3 × 180 s, rtfl 90 s K=4). Provider stand-in: golden lines, lines
> 8 s split into ≈6 s pieces (whisper-like), tokens clipped at window edges. Everything after the
provider is production code, including `parse_transcription`.

**Metric.** Output-row time overlapping reference lines, one-to-one label↔speaker mapping; spurious and
speaker-less time count as error. `extra K` = output labels − true speakers. `tok` = output tokens /
reference tokens (duplication > 1, loss < 1).

| path | variant | acc mean (min) | extra K mean (max) | speaker-less mean (max) | tok range |
|---|---|---|---|---|---|
| live | oracle diarized labels | 1.000 (.998) | +0.0 (+0) | .000 (.002) | 1.000–1.032 |
| live | **per-segment (J1)** | .836 (.453) | +1.1 (+6) | .085 (.544) | 1.000–1.032 |
| live | attach short → neighbour | .846 (.448) | +1.1 (+6) | .000 | 1.000–1.032 |
| live | json text only | .682 (.380) | −1.5 (K_out = 1) | .000 | **.887–1.131** |
| file | oracle diarized labels | 1.000 (1.000) | +0.0 | — | gate kept 100% |
| file | **per-segment (J1)** | .867 (.568) | **+3.9 (+18)** | — | gate kept 100% |
| file | attach short → neighbour | .870 (.523) | +0.8 (+5) | — | gate kept 100% |
| file | json text only, voiced placement | .682 (.380) | K_out = 1 | — | gate kept 100% |
| file | json text only, uniform placement | .682 (.380) | K_out = 1 | — | gate kept ≥ 96.0% |

**VERDICT.**
1. **Per-segment labels work but fragment.** Live keeps near-true speaker counts (+1.1) because the
   registry leaves short labels speaker-less (8.5% of time, 54% on the 60 s Jamie clip) for later
   relabel / Stop fingerprinting, which this bench does not simulate. File has no orphan step, so every
   segment < 2 s (no voiceprint) and every same-voice pair below FinalWordPolicy's .65 stays its own
   speaker: rtfl 22 labels for 4 people, Jamie 60 s 9 for 3.
2. **Attach-short is rejected for the adapter.** Accuracy +0.3 (File) / +1.0 (live) points; it only
   trades spurious File speakers for misattributed ones (rtfl −4.5 points). A File orphan rule belongs in
   the File composition (the live Stop fingerprint absorption is the measured analogue) — unmeasured.
3. **json-only models are not diarization.** One label per request (K_out = 1) on both paths, and live
   refresh boundaries lose up to 11% or duplicate up to 13% of words (segment-timed variants ≤ 3.2%).
4. **Voiced placement stays.** Uniform placement lost up to 4.0% of words to the WebRTC gate in File;
   voiced lost none. Live boundary error is similar for both (json rows above).

**Unmeasured.** Real provider segmentation, speaker labels (gpt-4o-transcribe-diarize), word timing,
and cross-speaker segments; Stop relabel of speaker-less rows; references for acquired/rtfl clips are
sparse (design doc: not binding aggregates).
