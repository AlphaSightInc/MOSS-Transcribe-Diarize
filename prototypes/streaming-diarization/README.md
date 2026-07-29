# Streaming-diarization measurement bench

Standing prototype harness for identity/diarization design questions
(design doc `docs/design-streaming-diarization.md`, ADR-0002). Verdicts to date:
`NOTES.md`. Code is committed; models/corpora/venv are local-only (`.gitignore`).

## Setup

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python torch torchaudio onnxruntime soundfile numpy scipy
# production-pinned WeSpeaker ONNX (sha must equal spec.state_sha256)
curl -fsSL -o data/voxceleb_resnet152_LM.onnx \
  'https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet152-LM/resolve/4adba1525a6c9d5fff74b6df43a6ec97a86c4112/voxceleb_resnet152_LM.onnx'
shasum -a 256 data/voxceleb_resnet152_LM.onnx  # 5b734353b4b410e222bbd124dd095537642237ad895727d18a3b9fee330262a8
# synthetic-meeting source (real human read speech)
curl -fsSL 'https://www.openslr.org/resources/12/dev-clean.tar.gz' | tar xz -C data/
# real golden interview corpora (1-min benchmark + 3-min calibration)
mkdir -p data/real && scp -r \
  'ga0@m4mbp:/Users/ga0/Desktop/AI_Projects/LiveTranscribe/data/benchmark_diarization_1min' \
  'ga0@m4mbp:/Users/ga0/Desktop/AI_Projects/LiveTranscribe/data/calibration_diarization_3min' \
  data/real/
```

## Runs

- `python3 proto_c_assembly.py` — gate C: frame assembly / gap manifest / resume (stdlib only)
- `.venv/bin/python proto_ab_identity.py all` — gates A+B: album vs overwrite, convergence,
  threshold grid, on synthetic meetings via the PRODUCTION embedder code path
- `.venv/bin/python proto_real_replay.py` — same policies on the real golden corpora

The harness imports `moss_transcribe_diarize/app/speaker_identity.py` directly
(`load_production_embedder`) so measurements run the exact production frontend and
ONNX session settings. Live-path semantics mirrored: 2.5 s span cap, 0.6 s silence
split, 0.5 s per-interval evidence floor, one-to-one score/margin matching, abstain,
birth, 16-speaker cap.
