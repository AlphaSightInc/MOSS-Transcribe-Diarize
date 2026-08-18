"""Small fail-closed checks for the remote-vLLM W2 matrix runner."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONCURRENCY = ROOT / "prototypes/streaming-diarization/concurrency"
RUNNER_PATH = CONCURRENCY / "run_remote_vllm_tunnel_measurement.py"


def _load_runner():
    sys.path.insert(0, str(CONCURRENCY))
    spec = importlib.util.spec_from_file_location("remote_vllm_tunnel_runner_test", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_endpoint_probe_requires_health_and_the_selected_model(monkeypatch):
    runner = _load_runner()
    requests: list[str] = []

    def fake_request(url, **_kwargs):
        requests.append(url)
        if url.endswith("/health"):
            return {"status": 200, "json": {"status": "ok"}, "body": "{}"}
        return {
            "status": 200,
            "json": {"data": [{"id": "other"}, {"id": "moss-model"}]},
            "body": "{}",
        }

    monkeypatch.setattr(runner, "_request_json", fake_request)
    result = runner._probe_remote_endpoint(
        base_url="http://127.0.0.1:18000/v1",
        selected_model="moss-model",
        timeout_seconds=3,
    )

    assert requests == ["http://127.0.0.1:18000/health", "http://127.0.0.1:18000/v1/models"]
    assert result["model_ids"] == ["moss-model", "other"]
    assert len(result["models_canonical_json_sha256"]) == 64


def test_endpoint_probe_refuses_embedded_credentials_and_missing_model(monkeypatch):
    runner = _load_runner()
    with pytest.raises(runner.MeasurementError, match="must not embed credentials"):
        runner._endpoint_urls("http://token@127.0.0.1:18000/v1")

    monkeypatch.setattr(
        runner,
        "_request_json",
        lambda _url, **_kwargs: {"status": 200, "json": {"data": [{"id": "other"}]}, "body": "{}"},
    )
    with pytest.raises(runner.MeasurementError, match="absent from /models"):
        runner._probe_remote_endpoint(
            base_url="http://127.0.0.1:18000/v1",
            selected_model="moss-model",
            timeout_seconds=3,
        )


def test_preflight_accepts_a_relative_evidence_output_path(monkeypatch, tmp_path):
    runner = _load_runner()
    output = Path("evidence/phase1/w2-local-concurrency/relative-output-test")
    args = SimpleNamespace(
        output=output,
        fixture=runner.FIXTURE_PATH,
        provisional_manifest=tmp_path / "provisional.json",
        vllm_base_url="http://127.0.0.1:18000/v1",
        vllm_model="moss-model",
        endpoint_timeout_seconds=3,
        deployed_descriptor_url="https://descriptor.invalid/api/live/descriptor",
        port=18999,
    )
    args.provisional_manifest.write_text(
        '{"identity_config": {}, "identity_provider": {}}', encoding="utf-8"
    )
    contract = {
        "profile": "remote-vllm-tunnel-local-live-routes",
        "run_started": False,
        "production_path": {"stub_results_qualify": False},
        "run_owned_manifest": {"shared_manifest_overwrite_allowed": False},
    }
    fixture = runner._read_json(runner.FIXTURE_PATH)
    measurement = runner.RemoteVllmMeasurement(args, contract, fixture)
    monkeypatch.setattr(measurement, "persist", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "_atomic_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        runner,
        "_probe_remote_endpoint",
        lambda **_kwargs: {"base_url": "http://127.0.0.1:18000/v1", "model_ids": ["moss-model"]},
    )
    monkeypatch.setattr(
        runner,
        "_request_json",
        lambda *_args, **_kwargs: {
            "status": 200,
            "json": {"descriptor": {"sample_rate": 16000, "frame_samples": 8000, "bounds": {
                "hard_cap_samples": 40000, "max_events": 1000, "max_frame_samples": 16000,
                "max_identity_speakers": 16, "max_queue_depth": 16, "max_retained_samples": 960000,
                "stop_drain_deadline_seconds": 5.0}}},
            "body": "{}",
        },
    )

    result = measurement.preflight()

    assert result["run_owned_manifest_path"] == str(output / "live-provider-manifest.json")
