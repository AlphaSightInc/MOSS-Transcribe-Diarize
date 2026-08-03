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
# regression fixture (golden actively maintained on m4mbp — refetch before measuring)
scp -r 'ga0@m4mbp:/Users/ga0/Desktop/AI_Projects/LiveTranscribe/data/regression_fixtures/youtube_rtfl_first_90s' \
  data/real/regression_fixtures/
# 5m + 30m tiers from the full corpus (per-case windows/{5m,30m}/{audio.wav,reference.jsonl}
# under .../LiveTranscribe/data/benchmark_diarization/cases/ -> data/real/benchmark_5m/<case>/,
# data/real/benchmark_30m/<case>/ — see proto_corpus_5m30m.py header)
```

## Test-audio library (data/real/, m4mbp is source of truth)

| tier | clips | duration | speakers | runner |
|---|---|---|---|---|
| benchmark_1min | 6 | 60 s | K=2-3 | proto_real_replay.py |
| calibration_3min | 3 | ~180 s | K=2-3 | proto_real_replay.py |
| youtube_rtfl_first_90s | 1 | 90 s | K=4, decisecond golden | proto_fixture_90s.py |
| benchmark_5m | 8 | 300 s | K=2-3 | proto_corpus_5m30m.py |
| benchmark_30m | 2 | 1800 s | K=2-3 | proto_corpus_5m30m.py |
| synthetic LibriSpeech | 8 | 600 s | K=2-6 | proto_ab_identity.py |

The binding 9-clip aggregate (design doc §7, 95.2%) = benchmark_1min + calibration_3min
only; other tiers are reported standalone. Not yet fetched from m4mbp: 30m windows for
6 more cases, `dual_lane_diarization/` (two-lane scenario), `manual_labeling/` (All-In
clip, K≈4-5, labeling in progress), `benchmark_diarization_test{,2,3}`, and unlabeled
long-form WAVs (5/10/30 min, lex_fridman_karpathy_30m60m).

## Runs

- `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/validate_inputs.py --json-output prototypes/streaming-diarization/l2-stage0/evidence/a1-validation.json` — L2 Stage-0 A1 frozen corpus/model/runtime/holdout boundary
- `python3 proto_c_assembly.py` — gate C: frame assembly / gap manifest / resume (stdlib only)
- `.venv/bin/python proto_ab_identity.py all` — gates A+B: album vs overwrite, convergence,
  threshold grid, on synthetic meetings via the PRODUCTION embedder code path
- `.venv/bin/python proto_real_replay.py` — same policies on the real golden corpora
- `.venv/bin/python proto_tape_differential.py --tape-index /path/to/retained-session/index.json --source-wav data/real/benchmark_5m/acquired_alphabet/audio.wav --reference data/real/benchmark_5m/acquired_alphabet/reference.jsonl --identity-asset data/voxceleb_resnet152_LM.onnx --corpus-start-sample <accepted-sample-before-playback> --work-dir /path/to/retained-session/derived --json-output /path/to/retained-session/derived/tape-differential.json` — retained live tape vs clean corpus through the production identity path

The harness imports `moss_transcribe_diarize/app/speaker_identity.py` directly
(`load_production_embedder`) so measurements run the exact production frontend and
ONNX session settings. Live-path semantics mirrored: 2.5 s span cap, 0.6 s silence
split, 0.5 s per-interval evidence floor, one-to-one score/margin matching, abstain,
birth, 16-speaker cap.
