# FIX-3.1 focused tests

Command:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$PY" -m pytest -q -p no:cacheprovider \
  tests/test_visible_word_instrument.py \
  tests/test_inference_scheduler.py \
  tests/phase2/test_operator_status.py
```

- Initial implementation: `34 passed, 1 warning in 2.88s`.
- Review found completed File owners would be relabeled after leaving the active population.
- First dispatch-time classification patch misplaced its validation in `run_live`: `3 failed, 31 passed`; no production run or GPU use occurred.
- Corrected classification/validation: `34 passed, 1 warning in 3.05s`; `git diff --check` clean.

Final verdict: PASS.
