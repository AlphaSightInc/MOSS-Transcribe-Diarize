from __future__ import annotations

import asyncio
import builtins
import hashlib
import importlib.metadata
import json
import socket
import struct
import wave
from dataclasses import replace
from types import SimpleNamespace

import packaging
import pytest

from moss_transcribe_diarize.app import live_provider_bundle
from moss_transcribe_diarize.app.live_identity_album import FingerprintAlbum
from moss_transcribe_diarize.app.live_provider_bundle import (
    BUNDLE_SCHEMA_VERSION,
    LiveProviderBundleAdmissionError,
    LiveProviderBundleConfig,
    LiveProviderBundleRuntime,
    SileroOnnxSpeechProvider,
    WebRtcSpeechProvider,
    WeSpeakerLiveEvidenceProvider,
    build_live_runtime_factory,
    compute_live_provider_bundle_hashes,
)
from moss_transcribe_diarize.app.live_service_runtime import hash_config
from moss_transcribe_diarize.app.live_session import AudioFrame, FrozenSpan, LiveIdentitySnapshot
from moss_transcribe_diarize.app.speaker_identity import TierBPreflight


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _tone(samples: int) -> bytes:
    import math

    return b"".join(
        struct.pack("<h", int(20000 * math.sin(2 * math.pi * 440 * index / 16000)))
        for index in range(samples)
    )


def _write_wav(path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)


class _FakeVad:
    def __init__(self, mode: int):
        self.mode = mode

    def is_speech(self, pcm: bytes, sample_rate: int) -> bool:
        assert self.mode == 1
        assert sample_rate == 16000
        return any(pcm)


class _FakeSilero:
    def speech_score(self, pcm: bytes, sample_rate: int) -> float:
        assert sample_rate == 16000
        return 0.9 if any(pcm) else 0.1


def _load_fake_silero(**kwargs):
    assert kwargs["backend"] == "onnxruntime-cpu"
    assert kwargs["device"] == "cpu"
    assert kwargs["intra_op_threads"] == 1
    assert kwargs["inter_op_threads"] == 1
    assert kwargs["model_path"].endswith("speech-provider.asset")
    return _FakeSilero()


class _FakeWeSpeakerAdapter:
    actual_dimension = 2

    def __init__(self, state_path, *, spec, device):
        self.state_path = state_path
        self.spec = spec
        self.device = device
        self.descriptor = {
            "provider": spec.provider,
            "revision": spec.revision,
            "state_sha256": spec.state_sha256,
            "embedding_dimension": spec.embedding_dimension,
            "frontend_version": spec.frontend_version,
            "device": device,
        }

    def preflight(self, *, fixture_path=None):
        assert fixture_path is not None
        if self.spec.embedding_dimension != self.actual_dimension:
            return TierBPreflight(False, "dimension_mismatch", self.descriptor)
        return TierBPreflight(True, None, self.descriptor)

    def embed(self, wav_path, intervals):
        assert intervals
        with wave.open(str(wav_path), "rb") as wav:
            assert wav.getframerate() == 16000
        return [0.6, 0.8]


@pytest.fixture(autouse=True)
def _provider_runtime_fakes(monkeypatch):
    monkeypatch.setattr(packaging, "Vad", _FakeVad, raising=False)
    monkeypatch.setattr(packaging, "load_fake_silero", _load_fake_silero, raising=False)
    monkeypatch.setattr(live_provider_bundle, "WeSpeakerResNet152LmAdapter", _FakeWeSpeakerAdapter)


def _golden_output_sha(kind: str) -> str:
    provider_reason = "webrtc_observation" if kind == "webrtc" else "silero_onnx_observation"
    return hash_config(
        {
            "schema_version": 1,
            "output_identity": f"{kind}+wespeaker_resnet152_lm:golden-v1",
            "speech_observations": [
                {
                    "start_sample": 0,
                    "end_sample": 160,
                    "speech_present": False,
                    "confidence": 0.0 if kind == "webrtc" else 0.1,
                    "provider_endpoint_sample": None,
                    "provider_reason": provider_reason,
                }
            ],
            "identity_embedding": [0.6, 0.8],
        }
    )


def _manifest(
    tmp_path,
    *,
    speech_kind: str = "webrtc",
    runtime_device: str = "cpu",
    runtime_backend: str | None = None,
    embedding_dimension: int = 2,
    state_sha: str | None = None,
) -> dict:
    state = tmp_path / "identity-provider.asset"
    golden = tmp_path / "golden.wav"
    state.write_bytes(b"offline identity provider state")
    _write_wav(golden, b"\0\0" * 160)
    state_sha = state_sha or _sha256_bytes(state.read_bytes())
    assets = [
        {
            "name": "identity-state",
            "path": state.name,
            "byte_size": state.stat().st_size,
            "sha256": state_sha,
            "identity": "synthetic-identity-state",
        }
    ]
    if speech_kind == "silero_onnx":
        speech_asset = tmp_path / "speech-provider.asset"
        speech_asset.write_bytes(b"offline speech provider state")
        assets.append(
            {
                "name": "speech-state",
                "path": speech_asset.name,
                "byte_size": speech_asset.stat().st_size,
                "sha256": _sha256_bytes(speech_asset.read_bytes()),
                "identity": "synthetic-speech-state",
            }
        )
        speech_provider = {
            "kind": "silero_onnx",
            "package_import": "packaging",
            "factory": "load_fake_silero",
            "asset_name": "speech-state",
            "threshold": 0.5,
        }
        backend = "onnxruntime-cpu"
    else:
        speech_provider = {
            "kind": speech_kind,
            "package_import": "packaging",
            "factory": "Vad",
            "mode": 1,
            "frame_samples": 160,
        }
        backend = "webrtc-cpu"
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
        "assets": assets,
        "runtime": {
            "backend": runtime_backend or backend,
            "device": runtime_device,
            "intra_op_threads": 1,
            "inter_op_threads": 1,
            "embedding_dimension": embedding_dimension,
        },
        "golden": {
            "input": {
                "name": "golden-input",
                "path": golden.name,
                "byte_size": golden.stat().st_size,
                "sha256": _sha256_bytes(golden.read_bytes()),
                "identity": "synthetic-golden-input",
            },
            "expected_output_identity": f"{speech_kind}+wespeaker_resnet152_lm:golden-v1",
            "expected_output_sha256": _golden_output_sha(speech_kind),
        },
        "endpoint_config": {
            "min_speech_samples": 1,
            "min_silence_samples": 1,
            "hard_cap_samples": 160,
        },
        "identity_config": {
            "max_speakers": 2,
            "min_match_score": 0.5,
            "min_match_margin": 0.1,
        },
        "decoder_config": {"max_samples": 160},
        "bounds_config": {
            "max_frame_samples": 160,
            "max_queue_depth": 2,
            "max_retained_samples": 320,
            "max_identity_speakers": 2,
            "max_events": 32,
            "frame_samples": 160,
            # Must equal endpoint_config.hard_cap_samples: the finalizer requires it when it
            # writes a manifest and the runtime refuses a session when it does not hold.
            "hard_cap_samples": 160,
            "stop_drain_deadline_seconds": 1.0,
        },
        "speech_provider": speech_provider,
        "identity_provider": {
            "kind": "wespeaker_resnet152_lm",
            "package_import": "packaging",
            "state_asset_name": "identity-state",
            "revision": "test-revision",
            "frontend_version": "synthetic-test",
            "min_segment_samples": 1,
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
        return SimpleNamespace(text="[0][S01]ok[0.01]", prompt_len=0, generated_tokens=1, elapsed_sec=0.01)


def _observations(provider, pcm: bytes):
    return provider.observe(
        frame=AudioFrame(sequence=0, pcm=pcm, sample_count=len(pcm) // 2, sample_rate=16000),
        start_sample=0,
        end_sample=len(pcm) // 2,
    )


def test_bundle_preflight_verifies_complete_offline_manifest_and_real_golden(tmp_path):
    config = LiveProviderBundleConfig.from_manifest(_write_manifest(tmp_path, _manifest(tmp_path)))
    preflight = config.preflight()

    assert preflight.available is True
    assert preflight.descriptor["provider_name"] == "deterministic-bundle"
    assert preflight.descriptor["speech_provider_kind"] == "webrtc"
    assert preflight.descriptor["identity_provider_kind"] == "wespeaker_resnet152_lm"
    assert preflight.config_hashes == config.declared_config_hashes
    assert len(preflight.manifest_hash) == 64


def test_bundle_runtime_factory_builds_audio_dependent_vad_and_live_identity_evidence(tmp_path):
    config = LiveProviderBundleConfig.from_manifest(_write_manifest(tmp_path, _manifest(tmp_path)))
    runtime = build_live_runtime_factory(config, FakeRunner())()
    speech = runtime._speech_provider_factory()
    preparer = runtime._identity_preparer_factory()

    assert isinstance(speech, WebRtcSpeechProvider)
    assert isinstance(preparer.evidence_provider, WeSpeakerLiveEvidenceProvider)
    assert _observations(speech, _tone(160)) != _observations(speech, b"\0\0" * 160)

    first_span = FrozenSpan(id=0, epoch=0, start_sample=0, end_sample=1600, reason="end_silence")
    second_span = FrozenSpan(id=1, epoch=0, start_sample=1600, end_sample=3200, reason="end_silence")
    first = preparer.prepare(
        span=first_span,
        pcm=_tone(1600),
        transcript="[0][S01]one[0.1]",
        base_snapshot=LiveIdentitySnapshot(),
    )
    second = preparer.prepare(
        span=second_span,
        pcm=_tone(1600),
        transcript="[0][S01]two[0.1]",
        base_snapshot=first.proposed_snapshot,
    )

    assert first.status == second.status == "prepared"
    assert first.proposed_snapshot.canonical_speakers == ("speaker-0001",)
    assert second.proposed_snapshot.canonical_speakers == ("speaker-0001",)
    assert ("assignments", "S01->speaker-0001") in second.proposed_snapshot.diagnostics


def test_bundle_factory_constructs_silero_from_declared_import_and_asset(tmp_path):
    config = LiveProviderBundleConfig.from_manifest(
        _write_manifest(tmp_path, _manifest(tmp_path, speech_kind="silero_onnx"))
    )
    runtime = build_live_runtime_factory(config, FakeRunner())()
    speech = runtime._speech_provider_factory()

    assert config.preflight().available is True
    assert isinstance(speech, SileroOnnxSpeechProvider)
    assert _observations(speech, _tone(160))[0].speech_present is True
    assert _observations(speech, b"\0\0" * 160)[0].speech_present is False


def test_bundle_runtime_factory_uses_existing_live_runtime_seams(tmp_path):
    config = LiveProviderBundleConfig.from_manifest(_write_manifest(tmp_path, _manifest(tmp_path)))
    runner = FakeRunner()
    runtime = build_live_runtime_factory(config, runner)()
    created = runtime.create()

    runtime.accept_frame(
        created.session_id,
        AudioFrame(sequence=0, pcm=_tone(160), sample_count=160, sample_rate=16000),
    )
    stopped = asyncio.run(runtime.stop(created.session_id, deadline=1.0))

    assert runtime.descriptor.provider_name == "deterministic-bundle"
    assert stopped.session.accepted_samples == stopped.session.accounted_samples == 160
    assert [commit.transcript for commit in stopped.session.committed] == ["[0][S01]ok[0.01]"]
    assert runner.calls == 1


def test_bundle_preflight_fails_closed_on_mismatched_fact(tmp_path):
    config = LiveProviderBundleConfig.from_manifest(
        _write_manifest(tmp_path, _manifest(tmp_path, runtime_device="cuda"))
    )
    preflight = config.preflight()

    assert preflight.available is False
    assert "runtime.device must be cpu" in preflight.failures
    with pytest.raises(LiveProviderBundleAdmissionError, match="preflight failed"):
        build_live_runtime_factory(config, FakeRunner())


def test_bundle_preflight_rejects_asset_hash_and_size_drift(tmp_path):
    payload = _manifest(tmp_path, state_sha="0" * 64)
    payload["assets"][0]["byte_size"] += 1
    config = LiveProviderBundleConfig.from_manifest(_write_manifest(tmp_path, payload))

    preflight = config.preflight()

    assert preflight.available is False
    assert "asset byte_size mismatch: identity-state" in preflight.failures
    assert "asset sha256 mismatch: identity-state" in preflight.failures


def test_bundle_preflight_rejects_package_version_and_import_drift(tmp_path):
    payload = _manifest(tmp_path)
    payload["packages"][0]["version"] = "0.0.invalid"
    missing_import = "packaging.definitely_missing_live_provider"
    payload["packages"][0]["import_name"] = missing_import
    payload["speech_provider"]["package_import"] = missing_import
    payload["identity_provider"]["package_import"] = missing_import
    config = LiveProviderBundleConfig.from_manifest(_write_manifest(tmp_path, payload))

    preflight = config.preflight()

    assert preflight.available is False
    assert "package version mismatch: packaging" in preflight.failures
    assert f"package import is not available: {missing_import}" in preflight.failures


def test_bundle_preflight_rejects_empty_or_decorative_provider_facts(tmp_path):
    payload = _manifest(tmp_path)
    payload["packages"] = []
    payload["assets"] = []
    config = LiveProviderBundleConfig.from_manifest(_write_manifest(tmp_path, payload))

    preflight = config.preflight()

    assert preflight.available is False
    assert "packages must declare every provider import" in preflight.failures
    assert "assets must declare every provider asset" in preflight.failures


def test_bundle_preflight_rejects_wrong_backend_dimension_and_golden_output(tmp_path):
    config = LiveProviderBundleConfig.from_manifest(
        _write_manifest(
            tmp_path,
            _manifest(
                tmp_path,
                runtime_backend="tensorrt-cuda-fp16",
                embedding_dimension=1,
            ),
        )
    )
    preflight = config.preflight()
    assert preflight.available is False
    assert "runtime.backend must be webrtc-cpu for webrtc." in preflight.failures

    payload = _manifest(tmp_path)
    payload["golden"]["expected_output_sha256"] = "0" * 64
    config = LiveProviderBundleConfig.from_manifest(_write_manifest(tmp_path, payload))
    preflight = config.preflight()
    assert preflight.available is False
    assert "golden expected_output_sha256 mismatch" in preflight.failures

    config = LiveProviderBundleConfig.from_manifest(
        _write_manifest(tmp_path, _manifest(tmp_path, embedding_dimension=1))
    )
    preflight = config.preflight()
    assert preflight.available is False
    assert "identity provider golden preflight failed: dimension_mismatch" in preflight.failures


def test_bundle_preflight_rejects_arbitrary_golden_identity_and_unsupported_kind(tmp_path):
    payload = _manifest(tmp_path)
    payload["golden"]["expected_output_identity"] = "never-computed-output"
    config = LiveProviderBundleConfig.from_manifest(_write_manifest(tmp_path, payload))
    assert "golden expected_output_identity mismatch" in config.preflight().failures

    payload = _manifest(tmp_path)
    payload["speech_provider"]["kind"] = "static_observation"
    config = LiveProviderBundleConfig.from_manifest(_write_manifest(tmp_path, payload))
    assert any("unwired stub" in failure for failure in config.preflight().failures)

    payload = _manifest(tmp_path)
    payload["speech_provider"]["kind"] = "totally_unknown"
    config = LiveProviderBundleConfig.from_manifest(_write_manifest(tmp_path, payload))
    assert any("unsupported speech provider kind: totally_unknown" in failure for failure in config.preflight().failures)


def test_bundle_manifest_rejects_non_positive_provider_thread_counts(tmp_path):
    payload = _manifest(tmp_path)
    payload["runtime"]["intra_op_threads"] = 0

    with pytest.raises(LiveProviderBundleAdmissionError, match="positive integer"):
        LiveProviderBundleConfig.from_mapping(payload, base_dir=tmp_path)

    config = LiveProviderBundleConfig.from_manifest(_write_manifest(tmp_path, _manifest(tmp_path)))
    config = replace(
        config,
        runtime=LiveProviderBundleRuntime(
            backend="webrtc-cpu",
            device="cpu",
            intra_op_threads=0,
            inter_op_threads=1,
            embedding_dimension=2,
        ),
    )
    assert "runtime.intra_op_threads must be positive" in config.preflight().failures


def test_bundle_runtime_factory_fails_before_route_construction(tmp_path):
    config = LiveProviderBundleConfig.from_manifest(_write_manifest(tmp_path, _manifest(tmp_path)))

    with pytest.raises(LiveProviderBundleAdmissionError, match="runner has no transcribe"):
        build_live_runtime_factory(config, object())


def test_bundle_preflight_is_offline_when_network_is_denied(tmp_path, monkeypatch):
    def deny_network(*args, **kwargs):
        del args, kwargs
        raise AssertionError("live provider preflight attempted network access")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(socket, "socket", deny_network)

    preflight = LiveProviderBundleConfig.from_manifest(
        _write_manifest(tmp_path, _manifest(tmp_path))
    ).preflight()

    assert preflight.available is True
    assert preflight.failures == ()


def test_web_cli_disabled_live_does_not_import_provider_bundle_or_optional_providers(monkeypatch):
    from moss_transcribe_diarize.app.web_cli import _live_runtime_factory

    real_import = builtins.__import__
    forbidden_roots = {"onnxruntime", "webrtcvad", "silero", "pyannote"}
    forbidden_modules = {"moss_transcribe_diarize.app.live_provider_bundle"}

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in forbidden_modules or name.split(".", 1)[0] in forbidden_roots:
            raise AssertionError(f"disabled live mode imported optional provider surface: {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    assert _live_runtime_factory(SimpleNamespace(live=False, live_provider_manifest=None)) is None


def test_web_cli_enabled_live_rejects_bad_manifest_before_app_construction(tmp_path):
    from moss_transcribe_diarize.app.web_cli import _live_runtime_factory

    manifest_path = _write_manifest(tmp_path, _manifest(tmp_path, runtime_device="cuda"))
    args = SimpleNamespace(
        live=True,
        live_provider_manifest=str(manifest_path),
        backend="hf",
        model="fake-model",
        vllm_model=None,
        vllm_base_url=None,
        vllm_api_key="EMPTY",
        vllm_timeout=600.0,
        device="cpu",
        dtype="float32",
    )

    with pytest.raises(LiveProviderBundleAdmissionError) as exc:
        _live_runtime_factory(args)

    assert exc.value.failure.code == "bundle_preflight_failed"
    assert "runtime.device must be cpu" in exc.value.failure.detail["failures"]


def test_silero_onnx_adapter_emits_observations_only_from_injected_inference():
    calls = []

    def infer(pcm, sample_rate):
        calls.append((pcm, sample_rate))
        return {"speech_score": 0.81}

    provider = SileroOnnxSpeechProvider(infer=infer, threshold=0.80)
    observations = _observations(provider, b"\0\0" * 320)

    assert calls == [(b"\0\0" * 320, 16000)]
    assert observations[0].speech_present is True
    assert observations[0].confidence == pytest.approx(0.81)
    assert observations[0].provider_endpoint_sample is None


def test_webrtc_adapter_normalizes_binary_frames_without_endpoint_authority():
    seen = []

    def vad(pcm, sample_rate):
        seen.append((len(pcm), sample_rate))
        return len(seen) == 2

    provider = WebRtcSpeechProvider(vad=vad, frame_samples=160)
    observations = _observations(provider, b"\0\0" * 320)

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


def _prepared_snapshot(*, span_id, assignments, canonical_speakers, version):
    return LiveIdentitySnapshot(
        version=version,
        canonical_speakers=canonical_speakers,
        diagnostics=(
            ("status", "prepared"),
            ("reason", "ok"),
            ("span_id", str(span_id)),
            ("assignments", assignments),
            ("canonical_speakers", ",".join(canonical_speakers)),
        ),
    )


class _ScriptedEncoder:
    """Returns one vector per `embed` call, so each span's voiceprint is chosen by the test."""

    def __init__(self, vectors):
        self.vectors = list(vectors)
        self.calls = []

    def embed(self, wav_path, intervals):
        self.calls.append(intervals)
        return self.vectors[len(self.calls) - 1]


def _score_span(provider, *, span_id, seconds, base_snapshot):
    samples = int(seconds * 16000)
    return provider.score(
        span=FrozenSpan(id=span_id, epoch=0, start_sample=0, end_sample=samples, reason="end_silence"),
        pcm=b"\0\0" * samples,
        segments=(SimpleNamespace(start=0.0, end=seconds, speaker="S01", text="words"),),
        base_snapshot=base_snapshot,
    )


def test_a_short_span_labels_against_the_album_but_never_overwrites_it():
    """ADR-0002 step 1, at the seam the overwrite policy lived on.

    Under latest-span replacement the 0.5 s fragment in the middle becomes `speaker-0001`'s
    reference and the third span -- the same voice as the first -- scores 0.0 against it.
    """

    encoder = _ScriptedEncoder([[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]])
    provider = WeSpeakerLiveEvidenceProvider(encoder=encoder, album=FingerprintAlbum())

    # Span 1: 2.0 s of a voice, before any canonical speaker exists.
    assert _score_span(
        provider,
        span_id=1,
        seconds=2.0,
        base_snapshot=LiveIdentitySnapshot(version=0, canonical_speakers=()),
    ) == ()

    # Span 2: 0.5 s of something else, admitted as a *label* for the same canonical speaker.
    after_first = _prepared_snapshot(
        span_id=1,
        assignments="S01->speaker-0001",
        canonical_speakers=("speaker-0001",),
        version=1,
    )
    short_evidence = _score_span(provider, span_id=2, seconds=0.5, base_snapshot=after_first)
    assert [round(item.score, 6) for item in short_evidence] == [0.0]

    # Span 3: the original voice again. The album still holds it.
    after_second = _prepared_snapshot(
        span_id=2,
        assignments="S01->speaker-0001",
        canonical_speakers=("speaker-0001",),
        version=2,
    )
    recovered = _score_span(provider, span_id=3, seconds=2.0, base_snapshot=after_second)

    assert [round(item.score, 6) for item in recovered] == [1.0]


def test_the_album_accumulates_rather_than_replacing_across_spans():
    encoder = _ScriptedEncoder([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    album = FingerprintAlbum()
    provider = WeSpeakerLiveEvidenceProvider(encoder=encoder, album=album)

    _score_span(provider, span_id=1, seconds=2.0, base_snapshot=LiveIdentitySnapshot(version=0, canonical_speakers=()))
    _score_span(
        provider,
        span_id=2,
        seconds=2.0,
        base_snapshot=_prepared_snapshot(
            span_id=1,
            assignments="S01->speaker-0001",
            canonical_speakers=("speaker-0001",),
            version=1,
        ),
    )
    _score_span(
        provider,
        span_id=3,
        seconds=2.0,
        base_snapshot=_prepared_snapshot(
            span_id=2,
            assignments="S01->speaker-0001",
            canonical_speakers=("speaker-0001",),
            version=2,
        ),
    )

    assert album.exemplar_count("speaker-0001") == 2
    assert album.reference("speaker-0001") == pytest.approx((0.5**0.5, 0.5**0.5))


def test_unreconciled_spans_do_not_grow_the_pending_map_for_the_length_of_a_meeting():
    """An abstain never reconciles, and an abstain is a designed outcome, not an anomaly."""

    encoder = _ScriptedEncoder([[1.0, 0.0]] * 40)
    provider = WeSpeakerLiveEvidenceProvider(encoder=encoder, album=FingerprintAlbum())
    empty = LiveIdentitySnapshot(version=0, canonical_speakers=())

    for span_id in range(1, 41):
        _score_span(provider, span_id=span_id, seconds=1.0, base_snapshot=empty)

    assert len(provider._pending_vectors) == live_provider_bundle._PENDING_SPAN_LIMIT
    assert max(provider._pending_vectors) == 40


def test_the_album_takes_adr_0002_defaults_and_lets_the_manifest_override_them():
    default = live_provider_bundle._fingerprint_album({})
    assert (default.admission_seconds, default.exemplars_per_speaker) == (1.0, 10)

    tuned = live_provider_bundle._fingerprint_album(
        {"album_admission_seconds": 1.5, "album_exemplars_per_speaker": 4}
    )
    assert (tuned.admission_seconds, tuned.exemplars_per_speaker) == (1.5, 4)


@pytest.mark.parametrize(
    "payload",
    [
        {"album_admission_seconds": 0},
        {"album_admission_seconds": -1.0},
        {"album_admission_seconds": "2"},
        {"album_admission_seconds": True},
        {"album_exemplars_per_speaker": 0},
        {"album_exemplars_per_speaker": 2.5},
    ],
)
def test_the_album_refuses_a_manifest_that_names_a_nonsensical_parameter(payload):
    with pytest.raises(LiveProviderBundleAdmissionError):
        live_provider_bundle._fingerprint_album(payload)
