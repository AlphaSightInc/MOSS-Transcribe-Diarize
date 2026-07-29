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
from moss_transcribe_diarize.app.live_identity import BoundedCausalIdentityPreparer, LiveIdentityConfig
from moss_transcribe_diarize.app.live_identity_album import (
    ALBUM_MIN_MATCH_MARGIN,
    ALBUM_MIN_MATCH_SCORE,
    FingerprintAlbum,
)
from moss_transcribe_diarize.app.live_identity_sweep import LABELLED, LiveIdentitySweeper
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
            # Candidate 55's birth floor is the album's admission gate, so a manifest whose
            # spans are shorter than `album_admission_seconds` can never birth a speaker.
            # This bundle's `hard_cap_samples` is 160 -- 0.01 s -- so it has to state an
            # admission its own spans can clear, or every node below would be asserting that
            # identity is disabled rather than that the seams are wired.
            "album_admission_seconds": 0.005,
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


def test_the_birth_floor_is_the_albums_own_admission_gate_and_not_a_second_constant():
    """Candidate 55's floor, read from the album rather than restated beside it.

    The rule is *a birth must be enrollable*: evidence too short to become a reference is too
    short to create the speaker that would hold one. Reading `admission_seconds` off the album
    is what makes the two one number -- a manifest that states `album_admission_seconds` moves
    both, and there is no second value that can agree today and drift later.
    """

    strict = WeSpeakerLiveEvidenceProvider(encoder=_ScriptedEncoder([[1.0, 0.0]]), album=FingerprintAlbum(admission_seconds=1.5))
    lenient = WeSpeakerLiveEvidenceProvider(encoder=_ScriptedEncoder([[1.0, 0.0]]), album=FingerprintAlbum(admission_seconds=0.5))
    empty = LiveIdentitySnapshot(version=0, canonical_speakers=())

    _score_span(strict, span_id=1, seconds=1.0, base_snapshot=empty)
    _score_span(lenient, span_id=1, seconds=1.0, base_snapshot=empty)

    assert strict.birth_deferrals(span_id=1, candidates=("S01",)) == (("S01", 1.0),)
    assert lenient.birth_deferrals(span_id=1, candidates=("S01",)) == ()


def test_a_speaker_the_evidence_floor_skipped_reports_no_embedded_speech_at_all():
    """The fragment case, which is where 14 of one run's 16 canonical speakers came from.

    At the deployed `min_segment_samples` 8000 a 0.5 s turn produces no interval, so the
    encoder is never called and the album is never offered anything. Reporting **0.0 s**
    rather than "unknown" is the point: the preparer must be able to tell a voice the system
    refused to embed from one it embedded and found short.
    """

    encoder = _ScriptedEncoder([[1.0, 0.0]])
    provider = WeSpeakerLiveEvidenceProvider(encoder=encoder, min_segment_samples=8000, album=FingerprintAlbum())

    assert _score_span(
        provider,
        span_id=1,
        seconds=0.4,
        base_snapshot=LiveIdentitySnapshot(version=0, canonical_speakers=()),
    ) == ()

    assert encoder.calls == []
    assert provider.birth_deferrals(span_id=1, candidates=("S01",)) == (("S01", 0.0),)


def test_a_stack_with_no_album_has_no_admission_gate_and_defers_no_birth():
    """The pre-ADR-0002 overwrite policy is a measurement baseline, not a deployment.

    `tests/live_identity_accuracy.py` reaches it with `album=None` to price what the album
    replaced. A floor applied there would move that baseline, so the comparison would stop
    measuring the album and start measuring the floor.
    """

    provider = WeSpeakerLiveEvidenceProvider(encoder=_ScriptedEncoder([[1.0, 0.0]]), album=None)
    _score_span(provider, span_id=1, seconds=0.1, base_snapshot=LiveIdentitySnapshot(version=0, canonical_speakers=()))

    assert provider.birth_deferrals(span_id=1, candidates=("S01",)) == ()


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


# --------------------------------------------------------------------------------------
# ADR-0002 step 3 on the live seam: what the sweeper retains, and when it re-matches it
# --------------------------------------------------------------------------------------


def _voice(angle_degrees: float) -> list[float]:
    """A voiceprint on the unit circle, so every cosine in these nodes is readable by eye."""

    import math

    radians = math.radians(angle_degrees)
    return [math.cos(radians), math.sin(radians)]


def _sweep_seam(*, interval_seconds: float = 1.0):
    """The real preparer over the real provider, with the real album and the real sweeper.

    Nothing here is a stand-in except the encoder's forward pass, exactly as the accuracy
    harness substitutes it: the matcher, the admission rule, the reconcile seam and the
    cadence are all production code.
    """

    encoder = _ScriptedEncoder(
        [
            _voice(0),  # span 1, S01 -- the first voice, born as speaker-0001
            _voice(90),  # span 1, S02 -- the second voice, born as speaker-0002
            _voice(45),  # span 2 -- exactly between them, so the live path must abstain
            _voice(30),  # span 3 -- the first voice again, and 4 s of it
            _voice(30),  # span 4 -- whatever; this span exists to reconcile span 3
        ]
    )
    album = FingerprintAlbum()
    config = LiveIdentityConfig(
        max_speakers=16,
        min_match_score=ALBUM_MIN_MATCH_SCORE,
        min_match_margin=ALBUM_MIN_MATCH_MARGIN,
    )
    sweeper = LiveIdentitySweeper(album=album, config=config, interval_seconds=interval_seconds)
    provider = WeSpeakerLiveEvidenceProvider(encoder=encoder, album=album, sweeper=sweeper)
    return BoundedCausalIdentityPreparer(config=config, evidence_provider=provider), sweeper


def _prepare(preparer, *, span_id, start_sec, segments, snapshot):
    end_sec = max(end for _, end, _ in segments)
    start_sample = int(start_sec * 16000)
    sample_count = int(end_sec * 16000)
    return preparer.prepare(
        span=FrozenSpan(
            id=span_id,
            epoch=0,
            start_sample=start_sample,
            end_sample=start_sample + sample_count,
            reason="end_silence",
        ),
        pcm=b"\0\0" * sample_count,
        transcript="".join(f"[{start:g}][{label}]w[{end:g}]" for start, end, label in segments),
        base_snapshot=snapshot,
    )


def _drive_sweep_seam(preparer):
    """Four spans of a meeting the live path cannot label correctly on its own."""

    return _drive_sweep_seam_to_snapshot(preparer)[0]


def _drive_sweep_seam_to_snapshot(preparer):
    """The same meeting, plus the identity state a session would be holding at its end."""

    snapshot = LiveIdentitySnapshot(version=0, canonical_speakers=())
    statuses = []
    for span_id, start_sec, segments in (
        (1, 0.0, [(0.0, 1.0, "S01"), (1.0, 2.0, "S02")]),
        (2, 2.0, [(0.0, 2.0, "S01")]),
        (3, 4.0, [(0.0, 4.0, "S01")]),
        (4, 8.0, [(0.0, 2.0, "S01")]),
    ):
        preparation = _prepare(
            preparer,
            span_id=span_id,
            start_sec=start_sec,
            segments=segments,
            snapshot=snapshot,
        )
        statuses.append(preparation.status)
        if preparation.status == "prepared":
            snapshot = preparation.proposed_snapshot
    return statuses, snapshot


def test_the_live_path_retains_the_evidence_a_sweep_rescues_an_abstained_span_with():
    """ADR-0002 step 3, end to end on the seam the live path actually runs.

    Span 2 sits exactly between the two voices born in span 1, so the matcher abstains -- the
    designed outcome (J2), and the reason a reader sees that span unattributed. Span 3 then
    gives `speaker-0001` four more seconds of speech, the album's centroid moves, and the
    sweep at span 4 re-matches span 2's *retained* vector and labels it. None of that is
    possible unless the unlabelled unit was retained when it was embedded, which is the
    decision this wiring took.
    """

    preparer, sweeper = _sweep_seam()

    statuses = _drive_sweep_seam(preparer)

    assert statuses == ["prepared", "abstain", "prepared", "prepared"]
    assert [
        (item.span_id, item.local_speaker, item.previous_speaker, item.canonical_speaker, item.reason)
        for item in sweeper.latest_revision.corrections
    ] == [(2, "S01", None, "speaker-0001", LABELLED)]
    assert sweeper.corrections == 1


def test_the_cadence_never_sees_the_span_being_prepared():
    """A sweep that could label the span in flight would correct a transcript nobody has read.

    Span 4's own evidence is retained *after* its cadence sweep runs, so the revision that
    rescues span 2 says nothing about span 4 -- whose label the live path is in the middle of
    deciding. The ledger holds it; the revision does not touch it.
    """

    preparer, sweeper = _sweep_seam()

    _drive_sweep_seam(preparer)

    assert sweeper.ledger.canonical_speaker(4, "S01") is None
    assert [item.span_id for item in sweeper.latest_revision.corrections] == [2]
    assert sweeper.sweeps == 3


def test_a_reconciled_assignment_reaches_the_ledger_as_well_as_the_album():
    """The album hears assignments; the ledger hears every embedded unit, labelled or not.

    Both are fed from the one place that holds a vector and an assignment together, so a unit
    the album admitted and a unit the ledger retained can never disagree about who spoke. The
    cadence is switched off for the length of this meeting on purpose: a sweep also writes
    labels into the ledger, so with one running this node would pass whether or not the
    reconcile seam fed it at all.
    """

    preparer, sweeper = _sweep_seam(interval_seconds=3600.0)

    _drive_sweep_seam(preparer)

    assert sweeper.sweeps == 0

    assert sweeper.ledger.canonical_speaker(1, "S01") == "speaker-0001"
    assert sweeper.ledger.canonical_speaker(1, "S02") == "speaker-0002"
    assert sweeper.ledger.canonical_speaker(3, "S01") == "speaker-0001"
    assert sweeper.ledger.unit_count == 5
    assert sweeper.ledger.refused_units == 0
    assert album_speakers(sweeper.album) == ["speaker-0001", "speaker-0002"]


def album_speakers(album):
    return sorted(album.speakers())


def test_an_abstained_span_is_the_one_unit_the_album_never_hears():
    """An abstention publishes words with no speaker, so there is no assignment to enrol -- and
    that is exactly the span whose vector a later sweep has the most to say about."""

    preparer, sweeper = _sweep_seam()

    _drive_sweep_seam(preparer)

    assert sweeper.album.exemplar_count("speaker-0001") == 2
    assert sweeper.album.exemplar_count("speaker-0002") == 1
    assert sweeper.ledger.span_count == 4


def test_a_cadence_that_has_not_come_round_leaves_the_meeting_untouched():
    preparer, sweeper = _sweep_seam(interval_seconds=3600.0)

    statuses = _drive_sweep_seam(preparer)

    assert statuses == ["prepared", "abstain", "prepared", "prepared"]
    assert (sweeper.sweeps, sweeper.corrections) == (0, 0)
    assert sweeper.latest_revision is None
    assert sweeper.ledger.unit_count == 5


def test_the_bundle_builds_one_album_and_one_sweeper_that_share_the_matcher_calibration(tmp_path):
    """ADR-0002 calls the album shipped without the sweep a terminal-state failure, so the
    factory that can produce one must produce the other, against the same album and the same
    calibration. A sweeper holding its own `LiveIdentityConfig` would be candidate 63 again:
    labels measured at one pair of thresholds and revised at another.
    """

    config = LiveProviderBundleConfig.from_manifest(_write_manifest(tmp_path, _manifest(tmp_path)))

    preparer = build_live_runtime_factory(config, FakeRunner())()._identity_preparer_factory()

    provider = preparer.evidence_provider
    assert isinstance(provider, WeSpeakerLiveEvidenceProvider)
    assert provider._sweeper is not None
    assert provider._sweeper.album is provider._album
    assert provider._sweeper.config is preparer.config
    assert provider._sweeper.interval_seconds == live_provider_bundle_sweep_interval()


def live_provider_bundle_sweep_interval() -> float:
    from moss_transcribe_diarize.app.live_identity_sweep import SWEEP_INTERVAL_SECONDS

    return SWEEP_INTERVAL_SECONDS


def test_the_session_end_finalize_labels_the_last_spans_evidence_before_it_sweeps():
    """ADR-0002's final sweep, and the order inside it, on the seam the live path runs.

    The cadence is off for the whole of this meeting, so this is the *only* sweep it gets --
    which is the ordinary case for any meeting shorter than one interval, and the tail of
    every meeting longer than one. Span 4's evidence is retained unlabelled while the meeting
    runs, because a span is labelled when the *following* preparation reconciles it and
    nothing follows the last one; the finalize settles that first and only then re-matches,
    so the sweep sees a ledger that agrees with the transcript rather than proposing a
    correction for a span the live path had already labelled.
    """

    preparer, sweeper = _sweep_seam(interval_seconds=3600.0)

    statuses, final_snapshot = _drive_sweep_seam_to_snapshot(preparer)

    assert statuses == ["prepared", "abstain", "prepared", "prepared"]
    assert sweeper.sweeps == 0
    assert sweeper.ledger.canonical_speaker(4, "S01") is None

    preparer.finalize_identity(base_snapshot=final_snapshot)

    assert sweeper.ledger.canonical_speaker(4, "S01") == "speaker-0001"
    assert sweeper.sweeps == 1
    # The abstained span is rescued, and the last span -- now settled -- is left alone.
    assert [
        (item.span_id, item.local_speaker, item.canonical_speaker, item.reason)
        for item in sweeper.latest_revision.corrections
    ] == [(2, "S01", "speaker-0001", LABELLED)]


def test_a_provider_that_cannot_sweep_still_settles_its_last_span():
    """The reconcile is not the sweep's errand; it is how the meeting's evidence ends up true.

    A stack with no sweeper has nothing to re-match, but the album it does have must still
    hear the last span's assignment -- and the pre-ADR-0002 stack, which keeps its reference
    vectors itself, must still record it. Neither has anything to say at session end, and
    saying nothing must not mean raising.
    """

    encoder = _ScriptedEncoder([_voice(0), _voice(0)])
    config = LiveIdentityConfig(
        max_speakers=16,
        min_match_score=ALBUM_MIN_MATCH_SCORE,
        min_match_margin=ALBUM_MIN_MATCH_MARGIN,
    )
    album = FingerprintAlbum()
    provider = WeSpeakerLiveEvidenceProvider(encoder=encoder, album=album)
    preparer = BoundedCausalIdentityPreparer(config=config, evidence_provider=provider)

    first = _prepare(
        preparer,
        span_id=1,
        start_sec=0.0,
        segments=[(0.0, 2.0, "S01")],
        snapshot=LiveIdentitySnapshot(version=0, canonical_speakers=()),
    )
    assert first.status == "prepared"
    assert album.exemplar_count("speaker-0001") == 0

    preparer.finalize_identity(base_snapshot=first.proposed_snapshot)

    assert album.exemplar_count("speaker-0001") == 1
    assert provider.take_identity_revision() is None
