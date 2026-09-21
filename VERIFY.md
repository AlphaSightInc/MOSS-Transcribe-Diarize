# R4-10 pre-terminal harness verification

Run from this clone with the prescribed interpreter:

```sh
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
$PY -m pytest -q -p no:cacheprovider tests/test_preterm_rerun_harness.py
$PY prototypes/preterm-rerun/run.py --plan-only --out evidence/round4/preterm/plan.json
```

Expected: 2 tests pass; plan records 15/13 alternation and 15/13 overlap requests, 56 total, and `corrected_reference.status=MISSING` on this pre-D27-fixture base. That `MISSING` status is correct: `--run` must refuse before creating the stack or dispatching a decoder request. Once the frozen candidate has the D27 fixture, the same command must instead report `READY`; a full run must retain all five named layers and every edit must classify a/b/c/d. Any absent layer, unclassified edit, missing fixture bypass, or request with a budget below 56 falsifies the harness.
