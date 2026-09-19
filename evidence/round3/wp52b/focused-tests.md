# WP52b focused tests

- Command: `python -m pytest -q -p no:cacheprovider tests/test_inference_scheduler.py`
- Result: **8 passed in 0.03 s**.
- Stability: repeated five times; **40/40 passed**, each run 0.03 s.
- Healthy control: File executed between earlier and later terminal windows;
  existing Live priority and cancelled-owner controls remained green.
- Violating control: scheduler-above-window-loop receipt reported File only
  after all terminal work and was detected as a whole-batch hold.
