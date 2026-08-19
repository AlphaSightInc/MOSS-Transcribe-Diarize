"""Small fail-closed checks for the remote-vLLM W2 matrix runner."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig


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


def test_lifecycle_fairness_excludes_an_idle_peer_but_rejects_ready_peer_starvation():
    runner = _load_runner()

    def event(session_id, kind, item_id):
        return {"session_id": session_id, "kind": kind, "payload": {"item_id": item_id}}

    fair_with_extra_peer_work = [
        event("a", "canonical_queued", 0),
        event("a", "canonical_queued", 1),
        event("a", "canonical_queued", 2),
        event("b", "canonical_queued", 0),
        event("b", "canonical_queued", 1),
        event("b", "canonical_queued", 2),
        event("a", "canonical_started", 0),
        event("a", "canonical_processed", 0),
        event("b", "canonical_started", 0),
        event("b", "canonical_processed", 0),
        event("a", "canonical_started", 1),
        event("a", "canonical_processed", 1),
        event("b", "canonical_started", 1),
        event("b", "canonical_processed", 1),
        event("a", "canonical_started", 2),
        event("a", "canonical_processed", 2),
        event("b", "canonical_started", 2),
        event("b", "canonical_processed", 2),
        event("b", "canonical_queued", 3),
        event("b", "canonical_started", 3),
        event("b", "canonical_processed", 3),
    ]
    fair = runner._canonical_lifecycle_fairness(
        fair_with_extra_peer_work, {"a", "b"}, maximum_skew=1
    )

    assert fair["passes"]
    assert fair["maximum_contended_pair_dispatch_skew"] == 1
    assert fair["contended_pair_dispatch_observations"] == 5

    starving_ready_peer = [
        event("a", "canonical_queued", 0),
        event("a", "canonical_queued", 1),
        event("b", "canonical_queued", 0),
        event("a", "canonical_started", 0),
        event("a", "canonical_processed", 0),
        event("a", "canonical_started", 1),
        event("a", "canonical_processed", 1),
        event("b", "canonical_started", 0),
        event("b", "canonical_processed", 0),
    ]
    unfair = runner._canonical_lifecycle_fairness(
        starving_ready_peer, {"a", "b"}, maximum_skew=1
    )

    assert not unfair["passes"]
    assert unfair["maximum_contended_pair_dispatch_skew"] == 2


def test_lifecycle_fairness_does_not_conflate_stop_residue_with_scheduler_fairness():
    runner = _load_runner()

    def event(session_id, kind, item_id):
        return {"session_id": session_id, "kind": kind, "payload": {"item_id": item_id}}

    lifecycle_with_post_stop_residue = [
        event("a", "canonical_queued", 0),
        event("b", "canonical_queued", 0),
        event("a", "canonical_started", 0),
        event("a", "canonical_processed", 0),
        event("b", "canonical_started", 0),
        event("b", "canonical_processed", 0),
        event("a", "canonical_queued", 1),
    ]

    fairness = runner._canonical_lifecycle_fairness(
        lifecycle_with_post_stop_residue, {"a", "b"}, maximum_skew=1
    )
    stop_drain = runner._canonical_lifecycle_stop_drain(
        lifecycle_with_post_stop_residue, {"a", "b"}
    )

    assert fairness["applicability"] == "measured"
    assert fairness["passes"] is True
    assert stop_drain["passes"] is False
    assert stop_drain["queued_item_count"] == 1


def test_single_session_normal_phase_accepts_not_applicable_fairness(tmp_path):
    runner = _load_runner()
    args = SimpleNamespace(output=tmp_path, port=18999)
    contract = {
        "scope": {"latency_label": "test latency"},
        "gates": {
            "latency": {"maximum_per_session_p95_transcript_lag_seconds": 10.0},
            "memory": {"maximum_process_tree_rss_increase_bytes_over_warm_idle": 1024},
            "fairness": {"maximum_dispatch_count_skew_for_continuously_ready_sessions": 1},
        },
    }
    measurement = runner.Measurement(args, contract, {})
    measurement.rss_warm_idle = 100
    session = runner.SessionRun(
        session_id="only-session",
        capture_bearer="capture",
        view_bearer="view",
        expected_marker="owned marker",
    )
    session.observer["latency_seconds"] = [0.5]
    session.observer["text"] = {"0": "owned marker"}
    session.rss_samples = [{"bytes": 100}]
    session.reconnects = [{"prior_event_cursor": 0, "prior_snapshot_version": 0}]
    measurement.event_log.write_text(
        "\n".join(
            json.dumps(
                {"session_id": "only-session", "kind": kind, "payload": payload}
            )
            for kind, payload in (
                ("canonical_queued", {"item_id": 0}),
                ("canonical_started", {"item_id": 0}),
                (
                    "canonical_processed",
                    {
                        "item_id": 0,
                        "submitted": True,
                        "rendered_transcript": "owned marker",
                    },
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    phase = {
        "stops": [{"status": 200}],
        "unexpected_frame_results": {"total_count": 0},
    }

    evaluation = measurement.evaluate_normal_phase(phase, [session])

    assert evaluation["canonical_lifecycle_fairness"]["applicability"] == "not_applicable"
    assert evaluation["stop_drain_complete"]["passes"] is True
    assert evaluation["passes"] is True


def test_unique_phase_clips_and_overload_integrity_oracle_fail_closed(tmp_path):
    runner = _load_runner()
    args = SimpleNamespace(output=tmp_path, port=18999)
    fixture = runner._read_json(runner.FIXTURE_PATH)
    measurement = runner.Measurement(args, {}, fixture)

    clips = measurement.phase_clips(8)
    assert len({clip["expected_marker"].casefold() for clip in clips}) == 8

    too_short = {**fixture, "clips": fixture["clips"][:7]}
    with pytest.raises(runner.MeasurementError, match="fewer clips"):
        runner.Measurement(args, {}, too_short).phase_clips(8)

    duplicate = {**fixture, "clips": [dict(clip) for clip in fixture["clips"]]}
    duplicate["clips"][1]["expected_marker"] = duplicate["clips"][0]["expected_marker"]
    with pytest.raises(runner.MeasurementError, match="lacks distinct clips and markers"):
        runner.Measurement(args, {}, duplicate).phase_clips(2)

    def session(session_id, marker):
        value = runner.SessionRun(
            session_id=session_id,
            capture_bearer="capture",
            view_bearer="view",
            expected_marker=marker,
        )
        value.observer["text"] = {"0": marker}
        value.reconnects = [{"prior_event_cursor": 1, "prior_snapshot_version": 1}]
        value.observer["snapshots"] = [
            {"observation": "reconnect", "status": 200, "rendered_transcript": marker}
        ]
        value.observer["events"] = [
            {
                "observation": "reconnect",
                "status": 200,
                "events": [
                    {
                        "kind": "canonical_processed",
                        "payload": {"span_id": 0, "submitted": True},
                    }
                ],
            }
        ]
        return value

    sessions = [session("a", "alpha marker"), session("b", "beta marker")]
    lifecycle = [
        {
            "session_id": item.session_id,
            "kind": "canonical_processed",
            "payload": {"span_id": 0, "submitted": True, "rendered_transcript": item.expected_marker},
        }
        for item in sessions
    ]
    checks = measurement.overload_integrity_checks(sessions, lifecycle)
    assert all(all(check.values()) for check in checks.values())

    lifecycle[0]["payload"]["rendered_transcript"] = "beta marker"
    falsified = measurement.overload_integrity_checks(sessions, lifecycle)
    assert not falsified["a"]["canonical_foreign_markers_absent"]
    assert not falsified["a"]["reconnect_replayed_canonical_foreign_markers_absent"]


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

    assert result["evidence_manifest_path"] == str(output / "live-provider-manifest.json")


def test_ephemeral_execution_manifest_materializes_relative_assets_before_production_preflight(tmp_path):
    runner = _load_runner()
    provisioned = tmp_path / "provisioned"
    run_directory = tmp_path / "evidence-run"
    identity = provisioned / "assets" / "identity.onnx"
    golden = provisioned / "golden" / "input.wav"
    identity.parent.mkdir(parents=True)
    golden.parent.mkdir(parents=True)
    identity.write_bytes(b"identity-state")
    golden.write_bytes(b"golden-input")
    run_directory.mkdir()

    manifest = run_directory / "live-provider-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_revision": "0" * 40,
                "provider_name": "test-provider",
                "provider_revision": "test-revision",
                "provider_license": "test-license",
                "provider_provenance": "test provenance",
                "packages": [],
                "assets": [
                    {
                        "name": "identity-state",
                        "path": "assets/identity.onnx",
                        "byte_size": identity.stat().st_size,
                        "sha256": hashlib.sha256(identity.read_bytes()).hexdigest(),
                        "identity": "test-identity",
                    }
                ],
                "runtime": {
                    "backend": "webrtc-cpu",
                    "device": "cpu",
                    "intra_op_threads": 1,
                    "inter_op_threads": 1,
                },
                "golden": {
                    "input": {
                        "name": "golden-input",
                        "path": "golden/input.wav",
                        "byte_size": golden.stat().st_size,
                        "sha256": hashlib.sha256(golden.read_bytes()).hexdigest(),
                        "identity": "test-golden",
                    },
                    "expected_output_identity": "test",
                    "expected_output_sha256": "0" * 64,
                },
                "endpoint_config": {},
                "identity_config": {},
                "decoder_config": {},
                "bounds_config": {},
                "config_hashes": {},
                "speech_provider": {},
                "identity_provider": {},
            }
        ),
        encoding="utf-8",
    )

    red = LiveProviderBundleConfig.from_manifest(manifest).preflight()
    assert "asset is not preinstalled: identity-state" in red.failures
    assert "asset is not preinstalled: golden-input" in red.failures

    materialized = runner._materialize_ephemeral_execution_assets(
        manifest_path=manifest,
        source_base_dir=provisioned,
    )

    green = LiveProviderBundleConfig.from_manifest(manifest).preflight()
    assert {record["name"] for record in materialized} == {"identity-state", "golden-input"}
    assert not any("asset is not preinstalled" in failure for failure in green.failures)
    assert (run_directory / "assets" / "identity.onnx").read_bytes() == identity.read_bytes()
    assert (run_directory / "golden" / "input.wav").read_bytes() == golden.read_bytes()


def test_finalize_keeps_execution_assets_out_of_evidence(monkeypatch, tmp_path):
    runner = _load_runner()
    provisioned = tmp_path / "provisioned"
    provisioned.mkdir()
    identity = provisioned / "identity.onnx"
    golden = provisioned / "golden.wav"
    identity.write_bytes(b"identity-state")
    golden.write_bytes(b"golden-input")
    provisional = provisioned / "provisional.json"
    provisional.write_text(
        json.dumps(
            {
                "identity_config": {"min_match_score": 0.35, "min_match_margin": 0.1},
                "identity_provider": {"album_admission_seconds": 2.0, "birth_min_seconds": 1.0},
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "evidence"
    execution_directory = tmp_path / "ephemeral-execution"
    execution_directory.mkdir()
    args = SimpleNamespace(output=output, provisional_manifest=provisional, port=18999)
    measurement = runner.RemoteVllmMeasurement(args, {}, {})
    measurement.head_revision = "0" * 40
    measurement.deployed_descriptor = {
        "sample_rate": 16000,
        "frame_samples": 8000,
        "bounds": {
            "hard_cap_samples": 40000,
            "max_events": 1000,
            "max_frame_samples": 16000,
            "max_identity_speakers": 16,
            "max_queue_depth": 16,
            "max_retained_samples": 960000,
            "stop_drain_deadline_seconds": 5.0,
        },
    }

    def fake_finalize(command, **_kwargs):
        execution_manifest = Path(command[command.index("--output") + 1])
        execution_manifest.write_text(
            json.dumps(
                {
                    "source_revision": "0" * 40,
                    "assets": [{"name": "identity-state", "path": "identity.onnx"}],
                    "golden": {"input": {"name": "golden-input", "path": "golden.wav"}},
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    class AvailablePreflight:
        available = True

        @staticmethod
        def to_dict():
            return {"available": True, "failures": []}

    class AvailableBundleConfig:
        @staticmethod
        def from_manifest(_path):
            return SimpleNamespace(preflight=AvailablePreflight)

    import moss_transcribe_diarize.app.live_provider_bundle as live_provider_bundle

    monkeypatch.setattr(runner.tempfile, "mkdtemp", lambda **_kwargs: str(execution_directory))
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *_args, **_kwargs: "0" * 40)
    monkeypatch.setattr(runner.subprocess, "run", fake_finalize)
    monkeypatch.setattr(live_provider_bundle, "LiveProviderBundleConfig", AvailableBundleConfig)

    measurement.finalize_manifest()

    assert measurement.execution_manifest is not None
    assert measurement.execution_manifest.parent == execution_directory
    assert measurement.evidence_manifest.is_file()
    assert not list(output.rglob("*.onnx"))
    assert not list(output.rglob("*.wav"))
    assert (execution_directory / "identity.onnx").is_file()
    assert (execution_directory / "golden.wav").is_file()

    measurement.cleanup()
    assert not execution_directory.exists()
