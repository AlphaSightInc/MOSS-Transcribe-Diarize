# WP52b unpatched instrumentation control

- Base scheduler: `a7a738cf9f9ff246f64c52c112e0bf597ba58241`; prior WP commits are disjoint.
- Command: `python -m pytest -q -p no:cacheprovider tests/test_inference_scheduler.py::test_scheduler_retains_content_free_dispatch_stage_clocks`
- Result: **FAIL as required**; `1 failed in 0.03s`.
- Failure: `InferenceDispatchScheduler` had no monotonic clock/instrument and retained no accepted/wait/start/end receipt.
