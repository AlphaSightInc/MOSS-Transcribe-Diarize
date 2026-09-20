# WP56a unpatched violating control

- Base contract: `a7a738cf9f9ff246f64c52c112e0bf597ba58241`; prior WP commits are disjoint.
- Command: `python -m pytest -q -p no:cacheprovider tests/test_qualification_verdict.py::test_two_meeting_capacity_is_the_supported_population`
- Result: **FAIL as required**; `1 failed in 0.91s`.
- Failure: the production validator rejected an otherwise healthy two-meeting receipt solely because it required four sessions.

After the population change, the healthy control and all eight violating controls pass as tests:
missing peer, wrong owner, missing owner probe, sample-accounting loss, lag violation,
false fairness, false real-time factor, and missing event time.
