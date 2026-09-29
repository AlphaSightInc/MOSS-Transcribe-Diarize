# Shared WeSpeaker encoder concurrency falsifier — 2026-09-29

**Structural question.** Could WP4's tentative embedding thread corrupt vectors used by the canonical registry because both call the same pinned `_OnnxWeSpeakerEmbedder` instance?

**Minimum primitives.** One warmed production encoder with live `interval_workers=3` and pinned ONNX; fixed public long60 speech from all five reference speakers; 1.0 s tentative-like and 2.5 s registry-like PCM16 clips; serial repeats; synchronized two-thread calls on the *same* instance. These isolate shared encoder concurrency while holding audio, model and frontend fixed.

**Invariant and unknown.** No Gemini call or live server. The clips, intervals and session settings do not change across arms. The probe tests warmed two-thread overlap; it cannot prove every runtime timing, cold initialization, or the content of fresh Gemini responses.

**Falsifier and tool.** Any concurrent vector differing beyond serial repeatability, or a concurrent exception, supports the shared-instance corruption hypothesis and would warrant a separate encoder or serialization. One command runs the production fbank/ONNX path and prints per-case serial and concurrent max component delta/min cosine plus observed overlap count:

```sh
PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/streaming-diarization/shared-encoder-concurrency/probe.py
```

**Measured verdict.** Five public speakers × two clip lengths = ten fixed cases. Two serial repeats per case, four concurrent repeats per case on two synchronized callers; the encoder used the live `interval_workers=3` setting; 20 overlapping call pairs observed. Serial max absolute component delta **0.0**, concurrent max delta **0.0**, minimum cosine **1.0**, no exception. The tested shared-instance path is deterministic and does not explain the paced long60 identity collapse. Fresh Gemini output drift and untested runtime timing remain open. Content-free result: `evidence/P66/wp4/shared-encoder-concurrency/result.json`. No production fix or paid send was made.
