# Speaker reference v2 forced alignment

Blindly force-align the immutable v1 transcript text to the corpus waveform. The aligner never
reads live-run output. V1 timestamps only split independent alignment windows at gaps of at least
10 seconds; no v1 timestamp is copied into v2.

```bash
PYTHON=.venv/bin/python bash prototypes/speaker-reference-v2/run.sh \
  --audio prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/audio.wav \
  --v1 prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/reference.jsonl \
  --output tests/fixtures/live_identity_real_corpus/speaker-reference-v2.jsonl \
  --provenance tests/fixtures/live_identity_real_corpus/speaker-reference-v2.provenance.json \
  --suspects /tmp/speaker-reference-v2-suspects.json
```

The first run downloads torchaudio's MMS forced-alignment checkpoint. Output is deterministic
for fixed model, audio, transcript, and PyTorch runtime.

Padding-gaming check (expected verdict `FAIL`, rc 3):

```bash
.venv/bin/python prototypes/speaker-reference-v2/proto_padding_gaming.py \
  --evidence-dir /tmp/moss-final-3e0edc1-evidence/real-run1-3e0edc1 \
  --reference-v2 tests/fixtures/live_identity_real_corpus/speaker-reference-v2.jsonl
```

Historical side-by-side rescore:

```bash
.venv/bin/python prototypes/speaker-reference-v2/rescore_evidence.py \
  --reference-v2 tests/fixtures/live_identity_real_corpus/speaker-reference-v2-post-audit.jsonl \
  --evidence /tmp/moss-final-3e0edc1-evidence/real-run1-3e0edc1 \
  --evidence /tmp/moss-final-3e0edc1-evidence/real-run2-3e0edc1
```

Freeze the accepted post-audit reference without overwriting the rejected candidate:

```bash
.venv/bin/python prototypes/speaker-reference-v2/finalize_post_audit.py \
  --v1 prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/reference.jsonl \
  --candidate tests/fixtures/live_identity_real_corpus/speaker-reference-v2.jsonl \
  --candidate-provenance tests/fixtures/live_identity_real_corpus/speaker-reference-v2.provenance.json \
  --audit tests/fixtures/live_identity_real_corpus/speaker-reference-v2-human-audit-20260803.json \
  --acoustic-evidence tests/fixtures/live_identity_real_corpus/speaker-reference-v2-candidate.acoustic-evidence.json \
  --output tests/fixtures/live_identity_real_corpus/speaker-reference-v2-post-audit.jsonl \
  --provenance tests/fixtures/live_identity_real_corpus/speaker-reference-v2-post-audit.provenance.json
```

Transcript-independent acoustic evidence, after five blind 60-second ASR responses have been
saved as `/tmp/moss-c2-acquired-asr-chunks/audio-00.json` through `audio-04.json`:

```bash
.venv/bin/python prototypes/speaker-reference-v2/build_acoustic_evidence.py \
  --audio prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/audio.wav \
  --response 0:/tmp/moss-c2-acquired-asr-chunks/audio-00.json \
  --response 60:/tmp/moss-c2-acquired-asr-chunks/audio-01.json \
  --response 120:/tmp/moss-c2-acquired-asr-chunks/audio-02.json \
  --response 180:/tmp/moss-c2-acquired-asr-chunks/audio-03.json \
  --response 240:/tmp/moss-c2-acquired-asr-chunks/audio-04.json \
  --source-revision 32323755f59374ff38c9c9126b274882d81029a9 \
  --output tests/fixtures/live_identity_real_corpus/speaker-reference-v2-candidate.acoustic-evidence.json
```

The operator audit packet and one-command listen snippets are in
`human-audit-acquired-alphabet-20260803.md`.
