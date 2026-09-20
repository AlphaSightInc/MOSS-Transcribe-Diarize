# R4-4 Jamie aggregation prototype

Run from the repository root:

```sh
PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/jamie/run.py
```

The command starts a fresh production WeSpeaker CPU ONNX session, embeds every control,
prints full policy state, and writes `evidence/round4/jamie/results.json`. It makes zero
decoder requests. `snippets.json` is an attended-adjudication packet, not frozen truth.
