# WP52a unpatched violating control

- Base: `a7a738cf9f9ff246f64c52c112e0bf597ba58241`
- Command: `python -m pytest -q -p no:cacheprovider tests/test_live_service_runtime.py::test_active_live_session_count_never_projects_full_snapshots`
- Result: **FAIL as required**; `1 failed in 0.87s`.
- Failure: `active_live_session_count()` invoked patched-to-raise `runtime._snapshot()`.
- Verdict: the control detects the pre-fix transcript/service projection dependency.
