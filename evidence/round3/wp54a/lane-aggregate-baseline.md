# WP54a two-lane aggregate violating control

- State: after per-finalizer clocks, before the authorized `live_lane_decode.py` follow-up.
- Command: `python -m pytest -q -p no:cacheprovider tests/test_live_lane_decode.py::test_terminal_lane_stage_clocks_aggregate_all_reached_lanes tests/phase2/test_draft_lane.py`
- Result: **FAIL as required** for the new control; `1 failed, 15 passed`.
- Failure: aggregate total `0.0007374590 s` did not partition the aggregate stages (`0.0008014170 s`) because preparation/total came from one template lane while decode covered both.
