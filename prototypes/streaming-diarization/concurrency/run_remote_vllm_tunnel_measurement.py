#!/usr/bin/env python3
"""Run the frozen W2 matrix through local live routes and the read-only vLLM tunnel.

This is deliberately a measurement harness, not product code.  It owns exactly one
loopback route process, finalizes a manifest only inside its evidence directory, and
uses the production ``VllmRunner`` through that process.  The remote endpoint is read
only: this runner probes it and sends inference requests, but never starts, stops, or
reconfigures anything there.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any

from run_cpu_hf_local_measurement import (  # Reuse the established live-route bench.
    DEFAULT_DEPLOYED_DESCRIPTOR_URL,
    FINALIZER_PATH,
    FIXTURE_PATH,
    ROOT,
    SERVER_PATH,
    Measurement,
    MeasurementError,
    SessionRun,
    _atomic_json,
    _descriptor_fields,
    _process_tree_rss_bytes,
    _read_json,
    _request_json,
    _sha256,
    _wav_clip,
)


CONTRACT_PATH = Path(__file__).with_name("remote_vllm_tunnel_preregistration.json")


def _canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _endpoint_urls(base_url: str) -> tuple[str, str, str]:
    """Return sanitized base, health, and models URLs without accepting credentials."""
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise MeasurementError("vLLM base URL must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise MeasurementError("vLLM base URL must not embed credentials")
    if parsed.query or parsed.fragment:
        raise MeasurementError("vLLM base URL must not contain a query or fragment")
    path = parsed.path.rstrip("/")
    if not path:
        raise MeasurementError("vLLM base URL must include its API path, such as /v1")
    origin = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    safe_base = f"{origin}{path}"
    return safe_base, f"{origin}/health", f"{safe_base}/models"


def _probe_remote_endpoint(
    *,
    base_url: str,
    selected_model: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Fail closed on endpoint health, catalog shape, or selected-model identity."""
    safe_base, health_url, models_url = _endpoint_urls(base_url)
    health = _request_json(health_url, timeout_seconds=timeout_seconds)
    if health["status"] != 200:
        raise MeasurementError(f"remote vLLM health probe returned HTTP {health['status']}")
    models = _request_json(models_url, timeout_seconds=timeout_seconds)
    body = models["json"]
    if models["status"] != 200 or not isinstance(body, dict):
        raise MeasurementError(f"remote vLLM models probe returned HTTP {models['status']}")
    catalog = body.get("data")
    if not isinstance(catalog, list):
        raise MeasurementError("remote vLLM /models response has no data list")
    model_ids = sorted(
        item["id"] for item in catalog if isinstance(item, dict) and isinstance(item.get("id"), str)
    )
    if selected_model not in model_ids:
        raise MeasurementError("configured vLLM model is absent from /models")
    return {
        "base_url": safe_base,
        "health_url": health_url,
        "health_status": health["status"],
        "models_url": models_url,
        "models_status": models["status"],
        "selected_model": selected_model,
        "model_ids": model_ids,
        "models_canonical_json_sha256": _canonical_json_sha256(body),
    }


class _RemoteHeartbeat:
    """Keep helper presence independent of a slow remote transcription request."""

    def __init__(self, runner: "RemoteVllmMeasurement", session: SessionRun):
        self._runner = runner
        self._session = session
        self._interval_seconds = runner.args.live_helper_lease_seconds / 4.0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._sequence = 0
        self.error: str | None = None
        self._thread = threading.Thread(
            target=self._run,
            name=f"w2-remote-vllm-heartbeat-{session.session_id[:8]}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval_seconds + 5.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                sequence = self._sequence
                self._sequence += 1
            payload = {
                "schema": "moss-live-helper-health.v1",
                "instance_id": f"w2-remote-vllm-{self._session.session_id}",
                "sequence": sequence,
                "sent_monotonic_ns": time.monotonic_ns(),
                "helper_version": "w2-remote-vllm-matrix-v1",
                "state": "capturing",
                "lanes": {
                    lane: {
                        "state": "capturing",
                        "device_epoch": 1,
                        "dropped_frames": 0,
                        "discontinuities": 0,
                        "failure_code": None,
                    }
                    for lane in ("microphone", "system")
                },
            }
            try:
                response = _request_json(
                    f"{self._runner.base_url}/api/live/sessions/"
                    f"{urllib.parse.quote(self._session.session_id)}/heartbeat",
                    method="POST",
                    payload=payload,
                    bearer=self._session.capture_bearer,
                    timeout_seconds=self._interval_seconds,
                )
                self._session.heartbeats.append(
                    {"sequence": sequence, "status": response["status"], "wall_ns": time.time_ns()}
                )
                if response["status"] != 200:
                    self.error = f"heartbeat returned HTTP {response['status']}"
                    return
            except MeasurementError as error:
                self.error = str(error)
                return
            self._stop.wait(self._interval_seconds)


class RemoteVllmMeasurement(Measurement):
    """CPU bench mechanics with remote-vLLM identity and heartbeat controls."""

    def __init__(self, args: argparse.Namespace, contract: dict[str, Any], fixture: dict[str, Any]):
        super().__init__(args, contract, fixture)
        self.head_revision: str | None = None
        self.run_manifest = self.output / "live-provider-manifest.json"
        self.endpoint_probes: dict[str, dict[str, Any]] = {}
        self.endpoint_probe_errors: dict[str, str] = {}
        self._heartbeats: dict[str, _RemoteHeartbeat] = {}
        self._heartbeat_outcomes: dict[str, dict[str, Any]] = {}
        self._verdict: dict[str, Any] | None = None

    def state(self, *, terminal: str | None = None, error: str | None = None) -> dict[str, Any]:
        value = super().state(terminal=terminal, error=error)
        value.update(
            {
                "schema": "moss-remote-vllm-tunnel-concurrency-measurement.v1",
                "contract_sha256": _sha256(CONTRACT_PATH),
                "fixture_manifest_sha256": _sha256(self.args.fixture),
                "fixture_sha256": _sha256(ROOT / self.fixture["audio"]["path"]),
                "captured_head_revision": self.head_revision,
                "run_owned_manifest": str(self.run_manifest),
                "run_owned_manifest_sha256": _sha256(self.run_manifest)
                if self.run_manifest.is_file()
                else None,
                "endpoint_probes": self.endpoint_probes,
                "endpoint_probe_errors": self.endpoint_probe_errors,
                "heartbeat_outcomes": self._heartbeat_outcomes,
            }
        )
        return value

    def endpoint_probe(self, label: str) -> dict[str, Any]:
        try:
            value = _probe_remote_endpoint(
                base_url=self.args.vllm_base_url,
                selected_model=self.args.vllm_model,
                timeout_seconds=self.args.endpoint_timeout_seconds,
            )
        except MeasurementError as error:
            self.endpoint_probe_errors[label] = str(error)
            raise
        self.endpoint_probes[label] = value
        return value

    def preflight(self) -> dict[str, Any]:
        if self.contract.get("profile") != "remote-vllm-tunnel-local-live-routes":
            raise MeasurementError("remote-vLLM runner requires its frozen remote-vLLM contract")
        if self.contract.get("run_started") is not False:
            raise MeasurementError("contract says a measurement already started; refuse to overwrite it")
        if self.contract["production_path"].get("stub_results_qualify") is not False:
            raise MeasurementError("contract must reject stub results")
        if self.contract["run_owned_manifest"].get("shared_manifest_overwrite_allowed") is not False:
            raise MeasurementError("contract must forbid writing the shared manifest")
        if not self.args.provisional_manifest.is_file():
            raise MeasurementError(f"provisional manifest is absent: {self.args.provisional_manifest}")
        provisional = _read_json(self.args.provisional_manifest)
        if not isinstance(provisional.get("identity_config"), dict) or not isinstance(
            provisional.get("identity_provider"), dict
        ):
            raise MeasurementError("provisional manifest lacks calibrated identity configuration")
        fixture_audio = ROOT / self.fixture["audio"]["path"]
        _wav_clip(self.fixture, self.fixture["clips"][0])
        _wav_clip(self.fixture, self.fixture["clips"][1])
        self.head_revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        remote = self.endpoint_probe("before")
        response = _request_json(
            self.args.deployed_descriptor_url,
            insecure_tls=self.args.deployed_descriptor_url.startswith("https://"),
            timeout_seconds=self.args.endpoint_timeout_seconds,
        )
        if response["status"] != 200 or not isinstance(response["json"], dict):
            raise MeasurementError("read-only deployed descriptor did not return HTTP 200 JSON")
        descriptor = response["json"].get("descriptor")
        if not isinstance(descriptor, dict):
            raise MeasurementError("deployed descriptor response has no descriptor object")
        self.deployed_descriptor = descriptor
        result = {
            "preflight": "PASS",
            "contract_sha256": _sha256(CONTRACT_PATH),
            "fixture_manifest_path": str(self.args.fixture.relative_to(ROOT)),
            "fixture_manifest_sha256": _sha256(self.args.fixture),
            "fixture_path": str(fixture_audio.relative_to(ROOT)),
            "fixture_sha256": _sha256(fixture_audio),
            "fixture_clip_ids": [clip["id"] for clip in self.fixture["clips"]],
            "captured_head_revision": self.head_revision,
            "run_owned_manifest_path": str(self.run_manifest),
            "deployed_bound_fields": _descriptor_fields(descriptor),
            "endpoint_before": remote,
            "gpu_claims_permitted": False,
        }
        self.persist(terminal="preflight", error=None)
        _atomic_json(self.output / "preflight.json", result)
        return result

    def finalize_manifest(self) -> None:
        if self.deployed_descriptor is None or self.head_revision is None:
            raise MeasurementError("preflight must capture descriptor and HEAD before finalizing")
        current_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if current_head != self.head_revision:
            raise MeasurementError("checkout HEAD changed after preflight; start a new run directory")
        deployed = _descriptor_fields(self.deployed_descriptor)
        provisional = _read_json(self.args.provisional_manifest)
        identity = provisional["identity_config"]
        provider = provisional["identity_provider"]
        command = [
            str(FINALIZER_PATH),
            "--input",
            str(self.args.provisional_manifest),
            "--output",
            str(self.run_manifest),
            "--source-revision",
            self.head_revision,
            "--hard-cap-samples",
            str(deployed["hard_cap_samples"]),
            "--max-retained-samples",
            str(deployed["max_retained_samples"]),
            "--frame-samples",
            str(deployed["frame_samples"]),
            "--min-match-score",
            str(identity["min_match_score"]),
            "--min-match-margin",
            str(identity["min_match_margin"]),
            "--album-admission-seconds",
            str(provider["album_admission_seconds"]),
            "--birth-min-seconds",
            str(provider["birth_min_seconds"]),
        ]
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / "manifest-finalization.txt").write_text(
            "$ " + " ".join(command) + "\n" + completed.stdout + completed.stderr,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise MeasurementError("run-owned manifest finalization failed")
        finalized = _read_json(self.run_manifest)
        if finalized.get("source_revision") != self.head_revision:
            raise MeasurementError("finalizer did not bind the run-owned manifest to captured HEAD")
        from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig

        try:
            LiveProviderBundleConfig.from_manifest(self.run_manifest)
        except Exception as error:  # The production reader is the contract here.
            raise MeasurementError("production provider reader rejected the run-owned manifest") from error

    def start_service(self) -> str:
        if self.deployed_descriptor is None or self.head_revision is None:
            raise MeasurementError("preflight must complete before service startup")
        self.event_log.write_text("", encoding="utf-8")
        log_handle = self.service_log.open("wb")
        command = [
            sys.executable,
            str(SERVER_PATH),
            "--live-provider-manifest",
            str(self.run_manifest),
            "--vllm-base-url",
            self.endpoint_probes["before"]["base_url"],
            "--vllm-model",
            self.args.vllm_model,
            "--vllm-timeout-seconds",
            str(self.args.vllm_timeout_seconds),
            "--live-helper-lease-seconds",
            str(self.args.live_helper_lease_seconds),
            "--canonical-event-log",
            str(self.event_log),
            "--port",
            str(self.args.port),
        ]
        self.service = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + self.args.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self.service.poll() is not None:
                raise MeasurementError("local service exited during startup; see service.log")
            try:
                response = _request_json(f"{self.base_url}/api/live/descriptor", timeout_seconds=2.0)
            except MeasurementError:
                time.sleep(0.2)
                continue
            if response["status"] == 200 and isinstance(response["json"], dict):
                descriptor = response["json"].get("descriptor")
                if isinstance(descriptor, dict):
                    self.local_descriptor = descriptor
                    break
            time.sleep(0.2)
        if self.local_descriptor is None:
            raise MeasurementError("local service did not expose its descriptor before startup deadline")
        if _descriptor_fields(self.local_descriptor) != _descriptor_fields(self.deployed_descriptor):
            raise MeasurementError("local and deployed descriptor bounds differ; refuse capture")
        if self.local_descriptor.get("source_revision") != self.head_revision:
            raise MeasurementError("local descriptor source revision does not match captured HEAD")
        bootstrap = _request_json(f"{self.base_url}/prototype/bootstrap")
        if bootstrap["status"] != 200 or not isinstance(bootstrap["json"], dict):
            raise MeasurementError("local measurement bootstrap did not provide capture authority")
        bearer = bootstrap["json"].get("capture_bearer")
        if not isinstance(bearer, str) or not bearer:
            raise MeasurementError("local measurement capture authority is absent")
        self.rss_warm_idle = _process_tree_rss_bytes(self.service.pid)
        self.persist()
        return bearer

    def create_session(self, *, bearer: str, clip: dict[str, Any]) -> SessionRun:
        session = super().create_session(bearer=bearer, clip=clip)
        heartbeat = _RemoteHeartbeat(self, session)
        self._heartbeats[session.session_id] = heartbeat
        heartbeat.start()
        return session

    def heartbeat(self, session: SessionRun) -> None:
        """Background heartbeat cadence is lease/4, even while a frame request blocks."""

    def stop(self, session: SessionRun) -> dict[str, Any]:
        try:
            return super().stop(session)
        finally:
            heartbeat = self._heartbeats.pop(session.session_id, None)
            if heartbeat is not None:
                heartbeat.close()
                self._heartbeat_outcomes[session.session_id] = {
                    "interval_seconds": self.args.live_helper_lease_seconds / 4.0,
                    "statuses": [record["status"] for record in session.heartbeats],
                    "error": heartbeat.error,
                }

    def evaluate_normal_phase(self, phase: dict[str, Any], sessions: list[SessionRun]) -> dict[str, Any]:
        memory = self.contract["gates"]["memory"]
        # The CPU bench uses the old spelling; keep its tested evaluation mechanics without
        # mutating or serializing a different remote contract.
        memory["maximum_process_tree_rss_increase_bytes_over_warm_idle"] = memory[
            "maximum_local_process_tree_rss_increase_bytes_over_warm_idle"
        ]
        try:
            evaluation = super().evaluate_normal_phase(phase, sessions)
        finally:
            del memory["maximum_process_tree_rss_increase_bytes_over_warm_idle"]
        helpers = {session.session_id: self._heartbeat_outcomes.get(session.session_id, {}) for session in sessions}
        helper_passes = all(
            bool(outcome.get("statuses"))
            and all(status == 200 for status in outcome["statuses"])
            and outcome.get("error") is None
            for outcome in helpers.values()
        )
        evaluation["remote_vllm_tunnel_decode_real_time_factor"] = evaluation.pop(
            "local_cpu_hf_decode_real_time_factor"
        )
        evaluation["helper_presence"] = helpers
        evaluation["helper_presence_passes"] = helper_passes
        evaluation["passes"] = evaluation["passes"] and helper_passes
        return evaluation

    def run_overload_phase(self) -> dict[str, Any]:
        phase = super().run_overload_phase()
        helpers = {session_id: self._heartbeat_outcomes.get(session_id, {}) for session_id in phase["sessions"]}
        helper_passes = all(
            bool(outcome.get("statuses"))
            and all(status == 200 for status in outcome["statuses"])
            and outcome.get("error") is None
            for outcome in helpers.values()
        )
        phase["evaluation"]["helper_presence"] = helpers
        phase["evaluation"]["helper_presence_passes"] = helper_passes
        phase["evaluation"]["passes"] = phase["evaluation"]["passes"] and helper_passes
        self.persist()
        return phase

    def run(self) -> dict[str, Any]:
        body_error: BaseException | None = None
        try:
            self.preflight()
            self.finalize_manifest()
            self._capture_bearer = self.start_service()
            matrix = self.contract["matrix"]
            screens = [
                self.run_normal_phase(
                    name=f"screen-{count}",
                    session_count=count,
                    duration_seconds=matrix["screening_measurement_seconds"],
                )
                for count in matrix["screening_session_counts"]
            ]
            passing = [phase for phase in screens if phase["evaluation"]["passes"]]
            soak = None
            if passing:
                chosen = max(phase["session_count"] for phase in passing)
                soak = self.run_normal_phase(
                    name="chosen-bound-soak",
                    session_count=chosen,
                    duration_seconds=matrix["chosen_bound_soak_seconds"],
                )
            overload = self.run_overload_phase()
            self._verdict = {
                "chosen_normal_session_bound": None
                if not passing
                else max(phase["session_count"] for phase in passing),
                "screening_passes": [phase["session_count"] for phase in passing],
                "soak_passes": soak is not None and soak["evaluation"]["passes"],
                "overload_passes": overload["evaluation"]["passes"],
                "closing_endpoint_probe_passes": None,
                "qualifies_local_g4_g5_portions": False,
                "does_not_establish": self.contract["scope"]["does_not_establish"],
                "fixture_limit_statement": self.contract["evidence_requirements"][
                    "fixture_limit_statement"
                ],
            }
        except BaseException as error:
            body_error = error
            raise
        finally:
            try:
                self.endpoint_probe("after")
            except MeasurementError:
                pass
            if self._verdict is not None:
                closing_passes = "after" in self.endpoint_probes
                self._verdict["closing_endpoint_probe_passes"] = closing_passes
                self._verdict["qualifies_local_g4_g5_portions"] = bool(
                    self._verdict["screening_passes"]
                    and self._verdict["soak_passes"]
                    and self._verdict["overload_passes"]
                    and closing_passes
                )
                self.phases.append({"name": "verdict", "kind": "verdict", "value": self._verdict})
                self.persist(terminal="completed")
                _atomic_json(self.output / "verdict.json", self._verdict)
            elif body_error is not None:
                self.persist(terminal="blocked-or-failed", error=str(body_error))
        if self._verdict is None:
            raise MeasurementError("measurement did not produce a verdict")
        return self._verdict

    def cleanup(self) -> None:
        for heartbeat in list(self._heartbeats.values()):
            heartbeat.close()
        self._heartbeats.clear()
        super().cleanup()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provisional-manifest", type=Path, required=True)
    parser.add_argument("--vllm-base-url", required=True)
    parser.add_argument("--vllm-model", required=True)
    parser.add_argument("--live-helper-lease-seconds", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH)
    parser.add_argument("--deployed-descriptor-url", default=DEFAULT_DEPLOYED_DESCRIPTOR_URL)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--endpoint-timeout-seconds", type=float, default=15.0)
    parser.add_argument("--startup-timeout-seconds", type=float, default=90.0)
    parser.add_argument("--vllm-timeout-seconds", type=float, default=600.0)
    parser.add_argument("--stop-deadline-seconds", type=float, default=90.0)
    parser.add_argument("--overload-retry-timeout-seconds", type=float, default=90.0)
    parser.add_argument("--preflight", action="store_true", help="probe immutable inputs without starting routes")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.live_helper_lease_seconds <= 0:
        raise SystemExit("--live-helper-lease-seconds must be positive")
    if args.endpoint_timeout_seconds <= 0:
        raise SystemExit("--endpoint-timeout-seconds must be positive")
    contract = _read_json(CONTRACT_PATH)
    fixture = _read_json(args.fixture)
    measurement = RemoteVllmMeasurement(args, contract, fixture)
    try:
        if args.preflight:
            print(json.dumps(measurement.preflight(), indent=2, sort_keys=True))
            return
        print(json.dumps(measurement.run(), indent=2, sort_keys=True))
    except MeasurementError as error:
        measurement.persist(terminal="blocked-or-failed", error=str(error))
        raise SystemExit(f"MEASUREMENT REFUSED: {error}") from error
    finally:
        measurement.cleanup()


if __name__ == "__main__":
    main()
