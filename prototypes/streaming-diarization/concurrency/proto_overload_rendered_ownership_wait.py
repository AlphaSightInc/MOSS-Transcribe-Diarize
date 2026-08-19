#!/usr/bin/env python3
"""Measure whether overload observers need a bounded rendered-ownership wait.

This bench-only probe keeps the production remote-vLLM/live-route overload path,
but replaces its repeated reconnect reads with ordinary polling until every
observer has rendered its own distinct marker.  It then performs exactly one
reconnect per observer.  A timeout remains a failure: the probe does not change
the frozen W2 gate or its timeout policy.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from run_cpu_hf_local_measurement import (
    DEFAULT_DEPLOYED_DESCRIPTOR_URL,
    FIXTURE_PATH,
    _atomic_json,
    _read_json,
    _sha256,
)
from run_remote_vllm_tunnel_measurement import (
    CONTRACT_PATH,
    RemoteVllmMeasurement,
)


class RenderedOwnershipWaitProbe(RemoteVllmMeasurement):
    """Turn repeated overload reconnect reads into pre-reconnect ordinary polls."""

    def __init__(self, args: argparse.Namespace, contract: dict[str, Any], fixture: dict[str, Any]):
        super().__init__(args, contract, fixture)
        self._ownership_wait_started_monotonic_ns: int | None = None
        self._ownership_observed_monotonic_ns: int | None = None
        self._marker_first_seen_monotonic_ns: dict[str, int] = {}
        self._reconnect_triggered = False

    def _observe_rendered_ownership(self) -> bool:
        now = time.monotonic_ns()
        sessions = list(self.active.values())
        for active in sessions:
            rendered = "\n".join(active.observer["text"].values()).casefold()
            if active.expected_marker.casefold() in rendered:
                self._marker_first_seen_monotonic_ns.setdefault(active.session_id, now)
        complete = bool(sessions) and len(self._marker_first_seen_monotonic_ns) == len(sessions)
        if complete and self._ownership_observed_monotonic_ns is None:
            self._ownership_observed_monotonic_ns = now
        return complete

    def reconnect_observer(self, session):  # type: ignore[no-untyped-def]
        """Poll before reconnect; parent overload code retains its bounded timeout loop."""
        if self._ownership_wait_started_monotonic_ns is None:
            self._ownership_wait_started_monotonic_ns = time.monotonic_ns()
        if self._reconnect_triggered:
            return
        self.poll(session, observation="pre-reconnect-rendered-ownership")
        if not self._observe_rendered_ownership():
            return
        self._reconnect_triggered = True
        for active in self.active.values():
            super().reconnect_observer(active)

    def rendered_ownership_result(self, phase: dict[str, Any]) -> dict[str, Any]:
        sessions = list(self.active.values())
        wait_started = self._ownership_wait_started_monotonic_ns
        first_seen_seconds = {
            session.session_id: None
            if wait_started is None or session.session_id not in self._marker_first_seen_monotonic_ns
            else (self._marker_first_seen_monotonic_ns[session.session_id] - wait_started) / 1_000_000_000
            for session in sessions
        }
        reconnect_counts = {session.session_id: len(session.reconnects) for session in sessions}
        observed_before_reconnect = (
            self._ownership_observed_monotonic_ns is not None and self._reconnect_triggered
        )
        return {
            "timeout_seconds": self.args.overload_retry_timeout_seconds,
            "wait_started_monotonic_ns": wait_started,
            "ownership_observed_monotonic_ns": self._ownership_observed_monotonic_ns,
            "ownership_wait_seconds": None
            if wait_started is None or self._ownership_observed_monotonic_ns is None
            else (self._ownership_observed_monotonic_ns - wait_started) / 1_000_000_000,
            "marker_first_seen_after_wait_seconds": first_seen_seconds,
            "reconnect_counts": reconnect_counts,
            "rendered_ownership_observed_before_reconnect": observed_before_reconnect,
            "exactly_one_reconnect_per_session": bool(reconnect_counts)
            and all(count == 1 for count in reconnect_counts.values()),
            "parent_overload_rendered_marker_predicate": phase["evaluation"][
                "rendered_markers_observed_before_reconnect"
            ],
            "parent_overload_integrity_passes": phase["evaluation"]["integrity_passes"],
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provisional-manifest", type=Path, required=True)
    parser.add_argument("--vllm-base-url", required=True)
    parser.add_argument("--vllm-model", required=True)
    parser.add_argument("--live-helper-lease-seconds", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH)
    parser.add_argument(
        "--rendered-ownership-timeout-seconds",
        type=float,
        default=120.0,
        help="exploratory bounded wait; timeout remains a fail-closed probe result",
    )
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--deployed-descriptor-url", default=DEFAULT_DEPLOYED_DESCRIPTOR_URL)
    parser.add_argument("--endpoint-timeout-seconds", type=float, default=15.0)
    parser.add_argument("--startup-timeout-seconds", type=float, default=90.0)
    parser.add_argument("--vllm-timeout-seconds", type=float, default=600.0)
    parser.add_argument("--stop-deadline-seconds", type=float, default=90.0)
    args = parser.parse_args()
    for name in (
        "live_helper_lease_seconds",
        "rendered_ownership_timeout_seconds",
        "endpoint_timeout_seconds",
        "startup_timeout_seconds",
        "vllm_timeout_seconds",
        "stop_deadline_seconds",
    ):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    args.overload_retry_timeout_seconds = args.rendered_ownership_timeout_seconds
    return args


def main() -> int:
    args = parse_args()
    contract = _read_json(CONTRACT_PATH)
    fixture = _read_json(args.fixture)
    measurement = RenderedOwnershipWaitProbe(args, contract, fixture)
    result: dict[str, Any] | None = None
    error: str | None = None
    try:
        preflight = measurement.preflight()
        measurement.finalize_manifest()
        measurement._capture_bearer = measurement.start_service()
        phase = measurement.run_overload_phase()
        endpoint_after = measurement.endpoint_probe("after")
        ownership = measurement.rendered_ownership_result(phase)
        passes = bool(
            ownership["rendered_ownership_observed_before_reconnect"]
            and ownership["exactly_one_reconnect_per_session"]
            and ownership["parent_overload_rendered_marker_predicate"]
            and ownership["parent_overload_integrity_passes"]
        )
        result = {
            "schema": "moss-overload-rendered-ownership-wait-prototype.v1",
            "question": (
                "Under the production remote-vLLM overload path, does a bounded ordinary-poll wait "
                "observe each session's rendered own marker before exactly one reconnect per observer?"
            ),
            "production_code_path": {
                "route": "production_route_server.py via RemoteVllmMeasurement.start_service",
                "decoder": "production VllmRunner through the supplied read-only tunnel",
                "overload": "Measurement.run_overload_phase",
                "observation_change": (
                    "ordinary poll until all rendered own markers are visible, then one reconnect per "
                    "observer; timeout remains fail-closed"
                ),
            },
            "inputs": {
                "contract_sha256": _sha256(CONTRACT_PATH),
                "fixture_manifest_sha256": _sha256(args.fixture),
                "rendered_ownership_timeout_seconds": args.rendered_ownership_timeout_seconds,
                "endpoint_before": preflight["endpoint_before"],
                "endpoint_after": endpoint_after,
            },
            "overload_evaluation": phase["evaluation"],
            "rendered_ownership": ownership,
            "verdict": {
                "passes": passes,
                "required_next_step": (
                    "Move the measured poll-before-single-reconnect sequence into the frozen runner and "
                    "rerun the full matrix; retain the bounded timeout as a failure."
                    if passes
                    else "Retain the current fail-closed overload result; investigate rendered publication before changing the runner."
                ),
                "does_not_establish": [
                    "G4",
                    "G5",
                    "a new concurrency bound",
                    "GPU memory, utilisation, OOM, or vLLM queue telemetry",
                ],
            },
        }
        _atomic_json(args.output / "overload-rendered-ownership-wait.json", result)
        measurement.persist(terminal="completed")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if passes else 1
    except Exception as caught:  # Keep the probe's captured preflight/service state as evidence.
        error = str(caught)
        raise
    finally:
        if result is None:
            measurement.persist(terminal="blocked-or-failed", error=error)
        measurement.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
