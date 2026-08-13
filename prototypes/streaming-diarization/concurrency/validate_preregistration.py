#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
from pathlib import Path


PATH = Path(__file__).with_name("preregistration.json")


def main() -> None:
    raw = PATH.read_bytes()
    state = json.loads(raw)

    assert state["schema"] == "moss-live-concurrency-preregistration.v1"
    assert state["ticket"] == 3
    assert state["run_started"] is False
    assert state["production_path"]["ingress_cadence_seconds"] == 0.5
    assert state["production_path"]["stub_results_qualify"] is False
    assert state["production_path"]["additional_uvicorn_workers_allowed"] is False
    assert state["matrix"]["dispatcher_concurrency"] == [1, 2, 4]
    assert state["matrix"]["simultaneous_meetings"] == [1, 2, 4, 8]
    assert state["matrix"]["chosen_bound_soak_seconds"] >= 600

    gates = state["gates"]
    assert gates["latency"]["maximum_per_session_p95_transcript_lag_seconds"] > 0
    assert 0 < gates["memory"]["maximum_vllm_gpu_cache_usage_fraction"] < 1
    assert gates["memory"]["maximum_process_tree_rss_increase_bytes_over_warm_idle"] > 0
    assert gates["memory"]["maximum_oom_or_accelerator_error_count"] == 0
    assert gates["memory"]["missing_vllm_metrics_qualify"] is False
    assert gates["fairness"]["maximum_dispatch_count_skew_for_continuously_ready_sessions"] == 1
    assert state["selection_rule"]["gate_changes_after_first_measurement_allowed"] is False

    print(json.dumps(state, indent=2, sort_keys=True))
    print(f"sha256={hashlib.sha256(raw).hexdigest()}")
    print("PASS: concurrency gates and measurement contract are frozen before measurement")


if __name__ == "__main__":
    main()
