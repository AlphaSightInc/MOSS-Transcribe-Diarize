# FIX-3.1 pre-fix controls

Base: `738cdfdde092b8ba9341179fb1d33e1c34cbd24c`

Command:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$PY" -m pytest -q -p no:cacheprovider \
  tests/test_visible_word_instrument.py::test_headed_reference_reader_preserves_intervals_for_word_expansion \
  tests/test_inference_scheduler.py::test_stage_clock_summary_reports_per_owner_wait_service_and_terminal_contention \
  tests/phase2/test_operator_status.py::test_operator_status_carries_stage_clocks_after_background_dispatch
```

Verdict: expected FAIL, `3 failed, 1 warning in 2.91s`, exit 1.

- Headed producer control: `ValueError: each source interval requires numeric start and end`.
- Scheduler projection control: `AttributeError` because `stage_clock_summary` is absent.
- Operator projection control: `KeyError: dispatch_stage_clocks`.

These failures prove both defects are present on the unpatched integration base.
