from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
from types import SimpleNamespace

import pytest

from moss_transcribe_diarize.app.live_provider_bundle import (
    BUNDLE_SCHEMA_VERSION,
    LiveProviderBundleAdmissionError,
    LiveProviderBundleConfig,
    SileroOnnxSpeechProvider,
    WebRtcSpeechProvider,
    WeSpeakerLiveEvidenceProvider,
    build_live_runtime_factory,
    compute_live_provider_bundle_hashes,
)
from moss_transcribe_diarize.app.live_session import AudioFrame, FrozenSpan, LiveIdentitySnapshot


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _golden_output_sha(input_sha: str, identity: str = "synthetic-static-speech") -> str:
    return hashlib.sha256(f"{input_sha}:{identity}".encode("utf-8")).hexdigest()


def _manifest(tmp_path, *, runtime_device: str = "cpu", asset_sha: str | None = None) -> dict:
    asset = tmp_path / "provider.asset"
    golden = tmp_path / "golden.pcm"
    asset.write_bytes(b"offline provider asset")
    golden.write_bytes(b"\0\0\0\0")
    asset_sha = asset_sha or _sha256_bytes(asset.read_bytes())
    golden_sha = _sha256_bytes(golden.read_bytes())
    payload = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "source_revision": "eda5e69faf0e0251383029295f7e8875a2a1a4f6",
        "provider_name": "deterministic-bundle",
        "provider_revision": "test-revision",
        "provider_license": "test-fixture",
        "provider_provenance": "synthetic local unit test",
        "packages": [
            {
                "distribution": "packaging",
                "version": importlib.metadata.version("packaging"),
                "import_name": "packaging",
            }
        ],
        "assets": [
            {
                "name": "provider-asset",
                "path": "provider.asset",
                "byte_size": asset.stat().st_size,
                "sha256": asset_sha,
                "identity": "synthetic-provider-asset",
            }
        ],
        "runtime": {
            "backend": "deterministic-fake",
            "device": runtime_device,
            "intra_op_threads": 1,
            "inter_op_threads": 1,
            "embedding_dimension": 256,
        },
        "golden": {
            "input": {
                "name": "golden-input",
                "path": "golden.pcm",
                "byte_size": golden.stat().st_size,
                "sha256": golden_sha,
                "identity": "synthetic-golden-input",
            },
            "expected_output_identity": "synthetic-static-speech",
            "expected_output_sha256": _golden_output_sha(golden_sha),
        },
        "endpoint_config": {
            "min_speech_samples": 1,
            "min_silence_samples": 1,
            "hard_cap_samples": 4000,
        },
        "identity_config": {
            "max_speakers": 2,
            "min_match_score": 0.0,
            "min_match_margin": 0.0,
        },
        "decoder_config": {"max_samples": 4000},
        "bounds_config": {
            "max_frame_samples": 4000,
            "max_queue_depth": 2,
            "max_retained_samples": 8000,
            "max_identity_speakers": 2,
            "max_events": 32,
            "frame_samples": 4000,
            "stop_drain_deadline_seconds": 1.0,
        },
        "speech_provider": {
            "kind": "static_observation",
            "speech_present": False,
            "confidence": 0.0,
            "provider_reason": "synthetic_non_speech",
        },
        "config_hashes": {},
    }
    config = LiveProviderBundleConfig.from_mapping(payload, base_dir=tmp_path)
    payload["config_hashes"] = compute_live_provider_bundle_hashes(config)
    return payload


def _write_manifest(tmp_path, payload: dict):
    path = tmp_path / "live-provider-manifest.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


class FakeRunner:
    def __init__(self):
        self.calls = 0

    def transcribe(self, wav_path, **kwargs):
        del wav_path, kwargs
        self.calls += 1
        return SimpleNamespace(text="[0][S01]ok[0.000125]", prompt_len=0, generated_tokens=1)


def test_bundle_preflight_verifies_complete_offline_manifest(tmp_path):
    manifest_path = _write_manifest(tmp_path, _manifest(tmp_path))

    config = LiveProviderBundleConfig.from_manifest(manifest_path)
    preflight = config.preflight()

    assert preflight.available is True
    assert preflight.descriptor["provider_name"] == "deterministic-bundle"
    assert preflight.config_hashes == config.declared_config_hashes
    assert len(preflight.manifest_hash) == 64


def test_bundle_preflight_fails_closed_on_mismatched_fact(tmp_path):
    payload = _manifest(tmp_path, runtime_device="cuda")
    manifest_path = _write_manifest(tmp_path, payload)

    preflight = LiveProviderBundleConfig.from_manifest(manifest_path).preflight()

    assert preflight.available is False
    assert "runtime.device must be cpu" in preflight.failures
    with pytest.raises(LiveProviderBundleAdmissionError, match="preflight failed"):
        build_live_runtime_factory(LiveProviderBundleConfig.from_manifest(manifest_path), FakeRunner())


def test_bundle_preflight_rejects_asset_hash_drift(tmp_path):
    manifest_path = _write_manifest(tmp_path, _manifest(tmp_path, asset_sha="0" * 64))

    preflight = LiveProviderBundleConfig.from_manifest(manifest_path).preflight()

    assert preflight.available is False
    assert "asset sha256 mismatch: provider-asset" in preflight.failures


def test_bundle_runtime_factory_uses_existing_live_runtime_seams(tmp_path):
    config = LiveProviderBundleConfig.from_manifest(_write_manifest(tmp_path, _manifest(tmp_path)))
    runner = FakeRunner()
    runtime = build_live_runtime_factory(config, runner)()
    created = runtime.create()

    runtime.accept_frame(
        created.session_id,
        AudioFrame(sequence=0, pcm=b"\0\0\0\0", sample_count=2, sample_rate=16000),
    )
    stopped = asyncio.run(runtime.stop(created.session_id, deadline=1.0))

    assert runtime.descriptor.provider_name == "deterministic-bundle"
    assert stopped.session.accepted_samples == stopped.session.accounted_samples == 2
    assert [commit.transcript for commit in stopped.session.committed] == ["[0][S01]ok[0.000125]"]
    assert runner.calls == 1


def test_bundle_runtime_factory_fails_before_route_construction(tmp_path):
    config = LiveProviderBundleConfig.from_manifest(_write_manifest(tmp_path, _manifest(tmp_path)))

    with pytest.raises(LiveProviderBundleAdmissionError, match="runner has no transcribe"):
        build_live_runtime_factory(config, object())


def test_silero_onnx_adapter_emits_observations_only_from_injected_inference():
    calls = []

    def infer(pcm, sample_rate):
        calls.append((pcm, sample_rate))
        return {"speech_score": 0.81}

    provider = SileroOnnxSpeechProvider(infer=infer, threshold=0.80)

    observations = provider.observe(
        frame=AudioFrame(sequence=7, pcm=b"\0\0" * 320, sample_count=320, sample_rate=16000),
        start_sample=100,
        end_sample=420,
    )

    assert calls == [(b"\0\0" * 320, 16000)]
    assert observations[0].start_sample == 100
    assert observations[0].end_sample == 420
    assert observations[0].speech_present is True
    assert observations[0].confidence == pytest.approx(0.81)
    assert observations[0].provider_endpoint_sample is None


def test_webrtc_adapter_normalizes_binary_frames_without_endpoint_authority():
    seen = []

    def vad(pcm, sample_rate):
        seen.append((len(pcm), sample_rate))
        return len(seen) == 2

    provider = WebRtcSpeechProvider(vad=vad, frame_samples=160)

    observations = provider.observe(
        frame=AudioFrame(sequence=1, pcm=b"\0\0" * 320, sample_count=320, sample_rate=16000),
        start_sample=0,
        end_sample=320,
    )

    assert seen == [(320, 16000), (320, 16000)]
    assert [(item.start_sample, item.end_sample, item.speech_present) for item in observations] == [
        (0, 160, False),
        (160, 320, True),
    ]
    assert all(item.provider_endpoint_sample is None for item in observations)


def test_wespeaker_live_adapter_scores_evidence_without_mutating_identity_snapshot():
    class FakeEncoder:
        def __init__(self):
            self.calls = []

        def embed(self, wav_path, intervals):
            self.calls.append((wav_path, intervals))
            return [1.0, 0.0]

    encoder = FakeEncoder()
    base = LiveIdentitySnapshot(version=4, canonical_speakers=("speaker-0001", "speaker-0002"))
    provider = WeSpeakerLiveEvidenceProvider(
        encoder=encoder,
        canonical_embedding=lambda snapshot, speaker: {
            "speaker-0001": [1.0, 0.0],
            "speaker-0002": [0.0, 1.0],
        }[speaker],
    )

    evidence = provider.score(
        span=FrozenSpan(id=3, epoch=0, start_sample=0, end_sample=3200, reason="end_silence"),
        pcm=b"\0\0" * 3200,
        segments=tuple(
            [
                SimpleNamespace(start=0.0, end=0.1, speaker="S01", text="one"),
                SimpleNamespace(start=0.1, end=0.2, speaker="S02", text="two"),
            ]
        ),
        base_snapshot=base,
    )

    assert base.canonical_speakers == ("speaker-0001", "speaker-0002")
    assert len(encoder.calls) == 2
    assert [item.local_speaker for item in evidence] == ["S01", "S01", "S02", "S02"]
    assert [item.score for item in evidence] == [1.0, 0.0, 1.0, 0.0]
