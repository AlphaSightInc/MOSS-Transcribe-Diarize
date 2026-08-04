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
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python prototypes/streaming-diarization/l2-stage0/validate_inputs.py --case-scope non-holdout --json-output prototypes/streaming-diarization/l2-stage0/evidence/a12-renewed-a1-validation-final.json
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

The initial A2 attempt remains a superseded `BLOCKED` result. A1.2 then version-rebuilt
all 16 non-holdout derived caches through production `EndpointPolicy` and
`WeSpeakerResNet152LmAdapter`; all caches matched their own replan. Holdout caches remain
untouched and are pinned for rebuild inside the single A5 opening.

Campaign A reached A5/A6 and ended `BLOCKED`. The candidate was frozen before the
single recorded holdout opening and was not tuned or rerun afterward. The sealed A6
verdict remains terminal; `L2_STAGE0_VERDICT_ADDENDUM.md` records the independent
review's later finding that truth-partitioned runtime units make the candidate gains
upper bounds rather than blind feasibility measurements. Campaign B is not authorized.
