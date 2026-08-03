# L2 Stage 0 — A1 frozen inputs

Prototype-only corpus and model boundary for retained-tape identity refinement.
Local audio, vectors, and model files remain under the bench's ignored `data/` tree;
their paths and hashes are frozen in `corpus-manifest.json` and
`model-manifest.json`.

Setup (copies data read-only from the existing bench, adopts only accepted alphabet
v2, rebuilds its vectors, writes manifests, and updates the launcher pin):

```bash
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/setup_inputs.py --source-bench /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/prototypes/streaming-diarization --json-output prototypes/streaming-diarization/l2-stage0/evidence/a1-setup.json
```

Run:

```bash
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/validate_inputs.py --json-output prototypes/streaming-diarization/l2-stage0/evidence/a1-validation.json
```

Accepted set: 2 development, 4 validation, 3 blind holdout. Ten other cases are
explicitly exploratory. The only accepted case at least four minutes long is
`5m-acquired-alphabet`, bound to the accepted post-audit reference and its blind
acoustic evidence. No other reference was edited.

`candidate-config.json` contains only holdout hash plus candidate freeze state—no
holdout path, cases, results, reference, or golden data. Until A5 freezes the
candidate family and spec hash, `holdout_gate.py` refuses before reading the sealed
manifest.

A2 production L1 control (six development/validation cases; holdout refused):

```bash
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/run_l1_control.py --evidence-dir prototypes/streaming-diarization/l2-stage0/evidence/a2-l1-runs --json-output prototypes/streaming-diarization/l2-stage0/evidence/a2-l1-summary.json --transcript-output prototypes/streaming-diarization/l2-stage0/evidence/a2-l1-transcript.txt
```

Current A2 verdict is `BLOCKED`: the first gated case replans to 26 production
evidence units while its frozen cache contains 29. No alternate configuration or
holdout case ran.
