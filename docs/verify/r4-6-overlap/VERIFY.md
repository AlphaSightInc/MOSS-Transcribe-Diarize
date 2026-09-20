# Fresh-context verification: R4-6 overlap diagnosis

Run from this clone. Do not change product code or evidence. Write `VERIFY-RESULT.md` with pass/fail, exact counts, and any falsifier hit.

1. Confirm source custody:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -c 'import moss_transcribe_diarize as m; print(m.__file__)'
```

Expected: path is inside `/private/tmp/moss-round4-20260920/overlap`.

2. Rebuild attribution from retained evidence:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/overlap/build_attribution.py
```

Expected: 83 rows; demo system classes `a=3,d=10`; each ladder system row `a=2,d=33`; raw words 105. Any raw/demo publication inequality or ladder-prefix inequality is a falsifier.

3. Run the diagnosis controls and production scorer controls:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_round4_overlap_diagnosis.py tests/phase2/test_lane_word_oracle.py
```

Expected: 10 passed, 2 xfailed. An unexpected pass of either strict expected failure falsifies the base-defect claim; another failure falsifies the reproduction.

4. Inspect `evidence/round4/overlap/attribution.json`, `attribution.md`, `decoder-requests.jsonl`, and `reference-correction-proposal.json`. Confirm requests `1/40`, peak in flight `1`, retries `0`; proposal status `proposal_only_never_applied`; classes (b) and (c) both zero; no product file is modified. Any contrary value is a failure.
