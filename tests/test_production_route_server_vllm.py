"""Regression coverage for the W2 route-probe remote-vLLM seam."""

from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "prototypes/browser-capture-feasibility/production_route_server.py"


def _load_server_module():
    spec = importlib.util.spec_from_file_location("production_route_server_vllm_test", SERVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_route_probe_constructs_remote_runner_without_a_local_model(monkeypatch, tmp_path):
    server = _load_server_module()
    captured: dict[str, object] = {}

    class FakeRunner:
        def __init__(self, *, base_url, model, timeout):
            captured["runner"] = {
                "base_url": base_url,
                "model": model,
                "timeout": timeout,
            }

        def transcribe(self, *_args, **_kwargs):
            raise AssertionError("the wiring test must not make an inference request")

    class FakeConfig:
        pass

    def fake_from_manifest(path):
        captured["manifest"] = path
        return FakeConfig()

    def fake_runtime_factory(config, runner):
        captured["factory"] = {"config_type": type(config), "runner_type": type(runner)}
        return lambda: object()

    class FakeApp:
        def __init__(self):
            self.state = SimpleNamespace()

        def middleware(self, *_args, **_kwargs):
            return lambda function: function

        def get(self, *_args, **_kwargs):
            return lambda function: function

        def post(self, *_args, **_kwargs):
            return lambda function: function

    def fake_create_app(**kwargs):
        captured["create_app"] = kwargs
        return FakeApp()

    from moss_transcribe_diarize.app import live_provider_bundle, vllm_runner

    monkeypatch.setattr(
        live_provider_bundle.LiveProviderBundleConfig,
        "from_manifest",
        staticmethod(fake_from_manifest),
    )
    monkeypatch.setattr(live_provider_bundle, "build_live_runtime_factory", fake_runtime_factory)
    monkeypatch.setattr(vllm_runner, "VllmRunner", FakeRunner)
    monkeypatch.setattr(server, "create_app", fake_create_app)

    manifest = tmp_path / "manifest.json"
    app = server.build_app(
        live_provider_manifest=manifest,
        vllm_base_url="http://127.0.0.1:18000/v1",
        vllm_model="remote-moss",
        vllm_timeout_seconds=123.0,
        live_helper_lease_seconds=47.0,
    )
    try:
        assert captured["manifest"] == manifest
        assert captured["runner"] == {
            "base_url": "http://127.0.0.1:18000/v1",
            "model": "remote-moss",
            "timeout": 123.0,
        }
        assert captured["factory"] == {"config_type": FakeConfig, "runner_type": FakeRunner}
        assert captured["create_app"]["live_enabled"] is True
        assert captured["create_app"]["live_runtime_factory"]
        assert captured["create_app"]["live_helper_lease_seconds"] == 47.0
        assert app.state.prototype_capture_bearer
        assert app.state.prototype_provider_scope.startswith("real production routes")
        assert "remote production VllmRunner" in app.state.prototype_provider_scope
    finally:
        app.state.prototype_scratch.cleanup()


def test_route_probe_refuses_remote_vllm_without_a_manifest_or_model():
    server = _load_server_module()

    with pytest.raises(ValueError, match="requires --live-provider-manifest"):
        server.build_app(vllm_base_url="http://127.0.0.1:18000/v1", vllm_model="remote-moss")

    with pytest.raises(ValueError, match="requires --vllm-model or --model"):
        server.build_app(
            live_provider_manifest=Path("manifest.json"),
            vllm_base_url="http://127.0.0.1:18000/v1",
        )

    with pytest.raises(ValueError, match="live-helper-lease-seconds must be positive"):
        server.build_app(live_helper_lease_seconds=0)


def test_canonical_measurement_log_captures_queue_start_and_publication_lifecycle():
    server = _load_server_module()
    records: list[dict] = []

    class EventLog:
        def append(self, record):
            records.append(record)

    class Runtime:
        def _record_event(self, *_args):
            return None

    runtime = Runtime()
    committed = SimpleNamespace(
        span_id=3,
        transcript="[0][S01]marker text[0.5]",
        revised_transcript=None,
    )
    state = SimpleNamespace(
        session_id="session-a",
        session=SimpleNamespace(snapshot=lambda: SimpleNamespace(committed=(committed,))),
    )
    server._instrument_commit_times(runtime, {}, threading.Lock(), event_log=EventLog())

    runtime._record_event(state, "canonical_queued", {"item_id": 7})
    runtime._record_event(state, "canonical_started", {"item_id": 7})
    runtime._record_event(
        state,
        "canonical_processed",
        {"item_id": 7, "span_id": 3, "submitted": True},
    )

    assert [record["kind"] for record in records] == [
        "canonical_queued",
        "canonical_started",
        "canonical_processed",
    ]
    assert {record["schema"] for record in records} == {
        "moss-live-canonical-dispatch-observation.v2"
    }
    assert records[-1]["payload"]["rendered_transcript"] == "[0][S01]marker text[0.5]"
