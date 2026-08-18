#!/usr/bin/env python3
"""Validate and print the frozen remote-vLLM tunnel measurement contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


PATH = Path(__file__).with_name("remote_vllm_tunnel_preregistration.json")


def main() -> None:
    raw = PATH.read_bytes()
    state = json.loads(raw)

    assert state["schema"] == "moss-live-concurrency-preregistration.v3"
    assert state["profile"] == "remote-vllm-tunnel-local-live-routes"
    assert state["ticket"] == 3
    assert state["run_started"] is False

    scope = state["scope"]
    assert "SSH tunnel and tailnet" in scope["latency_label"]
    assert "an isolated-GPU transcript-lag bound" in scope["does_not_establish"]
    assert "GPU memory or utilisation" in scope["does_not_establish"]
    assert "GPU OOM or accelerator errors" in scope["does_not_establish"]
    assert "vLLM active or queued request counts" in scope["does_not_establish"]

    path = state["production_path"]
    assert path["ingress_cadence_seconds"] == 0.5
    assert path["stub_results_qualify"] is False
    assert path["remote_service_mutation_allowed"] is False
    assert path["remote_host_read_only"] is True
    assert path["additional_uvicorn_workers_allowed"] is False
    assert path["frame_geometry"]["hardcoded_values_allowed"] is False

    manifest = state["run_owned_manifest"]
    assert manifest["shared_manifest_overwrite_allowed"] is False
    assert "git HEAD" in manifest["source_revision"]
    assert len(manifest["required_checks"]) == 4

    endpoint = state["endpoint_preflight"]
    assert endpoint["before_and_after_run"] is True
    assert "HTTP 200" in endpoint["health"]
    assert "HTTP 200" in endpoint["models"]
    assert len(endpoint["required_checks"]) == 5

    matrix = state["matrix"]
    assert matrix["screening_session_counts"] == [1, 2, 4, 8]
    assert matrix["chosen_bound_soak_seconds"] >= 600
    assert matrix["overload_session_count"] >= 2
    assert matrix["observer_reconnects_per_session"] >= 1

    gates = state["gates"]
    assert gates["latency"]["maximum_per_session_p95_transcript_lag_seconds"] > 0
    assert gates["latency"]["quantile_method"] == "linear Type-7"
    assert "tailnet transit" in gates["latency"]["basis"]
    assert gates["memory"]["maximum_local_process_tree_rss_increase_bytes_over_warm_idle"] > 0
    assert gates["memory"]["maximum_local_oom_or_accelerator_error_count"] == 0
    assert gates["memory"]["gpu_metrics_required"] is False
    assert gates["fairness"]["maximum_dispatch_count_skew_for_continuously_ready_sessions"] == 1
    assert gates["backpressure"]["lane"] == "v2"
    assert gates["backpressure"]["minimum_session_local_429_cases"] >= 1
    assert len(gates["backpressure"]["required_behavior"]) == 3

    assert state["selection_rule"]["candidate_set"] == [1, 2, 4, 8]
    assert state["selection_rule"]["gate_changes_after_first_measurement_allowed"] is False

    evidence = state["evidence_requirements"]
    assert len(evidence["raw_arrays"]) == 5
    assert len(evidence["identity_records"]) == 4
    assert len(evidence["required_recorded_metrics"]) == 3
    assert "does not measure isolated-GPU latency" in evidence["required_negative_statement"]
    assert "repeats" in evidence["fixture_limit_statement"]

    print(json.dumps(state, indent=2, sort_keys=True))
    print(f"sha256={hashlib.sha256(raw).hexdigest()}")
    print("PASS: remote-vLLM tunnel concurrency gates and measurement contract are frozen before measurement")


if __name__ == "__main__":
    main()
