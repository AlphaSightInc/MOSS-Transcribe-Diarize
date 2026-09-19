# WP54a unpatched violating control

- Base: `a7a738cf9f9ff246f64c52c112e0bf597ba58241` plus committed WP52a (disjoint files).
- Command: `python -m pytest -q -p no:cacheprovider tests/test_live_transcript_convergence.py::test_terminal_stage_clocks_leave_unreached_stages_null`
- Result: **FAIL as required**; `1 failed in 0.33s`.
- Failure: `TerminalFinalizationAccounting` lacked `preparation_elapsed_sec` (and therefore could not distinguish reached from unreached preparation).
