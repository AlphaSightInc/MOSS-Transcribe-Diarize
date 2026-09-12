# Account path versus legacy mono — measurement recipe

Question: same source audio, decoder and identity manifest; does v2/account change
the input, causal span boundaries, or speaker result? Falsifier: equal inputs and
outcomes reject an account-specific explanation. Report: ../../../docs/audits/account-path-der-differential-20260911.md.

These scripts reuse the production runtime/mixer, account replay adapter and
standing three-surface scorer. They do not change policy, thresholds, publication
order or the 30-second settle timeout. Raw captures stay outside the repository.
The only server patch is the existing local-stack SQLite-version accommodation.

Prerequisites: existing local decoder tunnel on 18000, installed live identity
manifest and model assets, trusted local TLS cert/key. This is a new instance on
17862, not the operator's 17861 stack. Use an empty scratch directory; retain it.

```sh
export MOSS_DIFFERENTIAL_REPO="$PWD"
export MOSS_DIFFERENTIAL_SCRATCH=/tmp/moss-der-differential-new
mkdir -p "$MOSS_DIFFERENTIAL_SCRATCH"
cp prototypes/streaming-diarization/account-path-differential/*.py "$MOSS_DIFFERENTIAL_SCRATCH/"
# Place existing local cert.pem/key.pem here with their original permissions.
# Terminal 1:
.venv/bin/python "$MOSS_DIFFERENTIAL_SCRATCH/run_stack.py"
# Terminal 2, with the same environment:
.venv/bin/python "$MOSS_DIFFERENTIAL_SCRATCH/measure.py"
.venv/bin/python "$MOSS_DIFFERENTIAL_SCRATCH/endpoints.py"
.venv/bin/python "$MOSS_DIFFERENTIAL_SCRATCH/controls.py"
.venv/bin/python "$MOSS_DIFFERENTIAL_SCRATCH/repeat.py"
```

`measure.py` saves each completed case immediately and records failed attempts.
It skips cases already recorded in results.json, including failures. A performance
RTF failure is retained separately only when all three valid captures exist; it is
never converted to a qualification pass. Settle/final-state failures are unscored.
The original terminal/abort handling remains in run_service_replay.

`endpoints.py` runs the real speech detector and endpoint policy on original and
production-mixed PCM without a decoder. `controls.py` makes one explicit Javier
account retry, then separates Ackman's gain-only and one-frame-hold-only effects and tests Adam's gain-only input.
The final repeat checks Javier twice in the same fresh workspace, without enrollment.
Hold-only retains original bytes and releases the last frame on Stop, preserving
the complete final audio. These are diagnostic controls, not product changes.

`instrument.py` records provider intervals and match scores after the existing
score call. It neither reconciles nor embeds additional evidence. Do not publish
the raw scratch directory; only selected counts, scores and timing are retained
in this bench's results.

Stop only this scratch server after measurement; do not reset either database.
