#!/usr/bin/env python3
"""Validate and print the frozen CPU/HF-local concurrency measurement contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


PATH = Path(__file__).with_name("cpu_hf_local_preregistration.json")


def main() -> None:
    raw = PATH.read_bytes()
    state = json.loads(raw)

    assert state["schema"] == "moss-live-concurrency-preregistration.v2"
    assert state["profile"] == "cpu-hf-local-deployed-geometry"
    assert state["ticket"] == 3
    assert state["run_started"] is False

    scope = state["scope"]
    assert scope["latency_label"] == "CPU HF local decode, not the deployed GPU bound"
    assert "deployed GPU p95 transcript lag" in scope["does_not_establish"]
    assert "deployed GPU memory or utilisation" in scope["does_not_establish"]

    path = state["production_path"]
    assert path["ingress_cadence_seconds"] == 0.5
    assert path["stub_results_qualify"] is False
    assert path["remote_service_mutation_allowed"] is False
    assert path["additional_uvicorn_workers_allowed"] is False
    assert path["frame_geometry"]["hardcoded_values_allowed"] is False

    matrix = state["matrix"]
    assert matrix["screening_session_counts"] == [2, 4]
    assert matrix["chosen_bound_soak_seconds"] >= 600
    assert matrix["overload_session_count"] >= 2
    assert matrix["observer_reconnects_per_session"] >= 1

    gates = state["gates"]
    assert gates["latency"]["maximum_per_session_p95_transcript_lag_seconds"] > 0
    assert gates["latency"]["quantile_method"] == "linear Type-7"
    assert gates["memory"]["maximum_process_tree_rss_increase_bytes_over_warm_idle"] > 0
    assert gates["memory"]["maximum_oom_or_accelerator_error_count"] == 0
    assert gates["memory"]["gpu_metrics_required"] is False
    assert gates["fairness"]["maximum_dispatch_count_skew_for_continuously_ready_sessions"] == 1
    assert gates["backpressure"]["lane"] == "v2"
    assert gates["backpressure"]["minimum_session_local_429_cases"] >= 1
    assert len(gates["backpressure"]["required_behavior"]) == 3

    assert state["selection_rule"]["candidate_set"] == [2, 4]
    assert state["selection_rule"]["gate_changes_after_first_measurement_allowed"] is False
    assert len(state["evidence_requirements"]["raw_arrays"]) == 5

    print(json.dumps(state, indent=2, sort_keys=True))
    print(f"sha256={hashlib.sha256(raw).hexdigest()}")
    print("PASS: CPU/HF-local concurrency gates and measurement contract are frozen before measurement")


if __name__ == "__main__":
    main()
