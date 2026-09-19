# Local-label purity prototype

Status: **IN PROGRESS — no production change authorized by this note.**

## Contract

- Structural question: when a decoder-local speaker label contains more than one
  source-verified person, can the interval vectors already computed before averaging
  distinguish the people without damaging clean labels?
- Minimum primitives: retained local decoder interval, its production WeSpeaker vector,
  decoder-local label, final fingerprint-album reference, and independent source turn.
  These respectively carry time, acoustics, the decoder hypothesis, durable identity,
  and adjudication.
- Invariants: words and times never change; no source label enters the candidate;
  unknown is not correct; matching score/margin remain `0.35`/`0.10`; clean assigned
  people must not regress.
- Assumptions/unknowns: the retained WP28 WAV spans correspond to the retained long-WAV
  source; MP3 local spans were not retained, so MP3 causality is unknown; coarse source
  turns include boundary uncertainty; simultaneous omitted speech cannot be recovered by
  identity.
- Falsifier: interval vectors do not separate the mixed local label at the production
  matcher, or reassignment confuses/abstains clean-label controls.
- Tool decision: reuse the production ONNX embedder, retained local spans, retained audio,
  current album implementation, and independent source turns. No decoder/GPU call is
  needed. The prototype exposes vectors the production embedder already computes before
  its mean; it does not embed an interval twice.

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python \
  prototypes/streaming-diarization/local-label-purity/probe.py
```

The command prints and writes `results.json`. It retains scores/counts, not audio,
transcript text, or raw vectors.
