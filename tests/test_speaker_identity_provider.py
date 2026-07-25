from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from moss_transcribe_diarize.app import speaker_identity as identity_module
from moss_transcribe_diarize.app.speaker_identity import (
    PINNED_TIER_B_ASSET_SPEC,
    TierBAssetSpec,
    WeSpeakerResNet152LmAdapter,
    tier_b_provider_manifest,
)


FIXTURE = Path(__file__).parent / "fixtures" / "idea_020_provider_smoke.wav"


def test_preflight_cli_help_does_not_require_optional_provider_packages():
    completed = subprocess.run(
        [sys.executable, "-m", "moss_transcribe_diarize.speaker_identity_preflight", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "--state-path" in completed.stdout
    assert "--fixture" in completed.stdout
    assert "--json" in completed.stdout


def test_pinned_manifest_is_the_default_descriptor():
    assert tier_b_provider_manifest() == {
        "provider": "wespeaker_resnet152_lm",
        "revision": "4adba1525a6c9d5fff74b6df43a6ec97a86c4112",
        "state_sha256": "5b734353b4b410e222bbd124dd095537642237ad895727d18a3b9fee330262a8",
        "embedding_dimension": 256,
        "frontend_version": "wespeaker-onnx-fbank-v1",
        "device": "cpu",
    }


def test_static_preflight_failures_do_not_load_provider(tmp_path):
    calls = 0

    def loader():
        nonlocal calls
        calls += 1
        return GoodEmbedder()

    missing = WeSpeakerResNet152LmAdapter(tmp_path / "missing.pt", loader=loader).preflight()
    assert missing.available is False
    assert missing.reason == "asset_missing"
    assert calls == 0

    state = tmp_path / "state.pt"
    state.write_bytes(b"wrong-state")
    mismatch = WeSpeakerResNet152LmAdapter(state, loader=loader).preflight()
    assert mismatch.available is False
    assert mismatch.reason == "asset_hash_mismatch"
    assert calls == 0

    device = WeSpeakerResNet152LmAdapter(state, loader=loader, device="cuda").preflight()
    assert device.available is False
    assert device.reason == "device_not_cpu"
    assert calls == 0


def test_provider_missing_is_reported_after_hash_and_device_are_valid(tmp_path):
    state = tmp_path / "state.pt"
    state.write_bytes(b"fake-state")
    spec = _spec_for(state)

    result = WeSpeakerResNet152LmAdapter(
        state,
        spec=spec,
        loader=LazyMissingEmbedder,
    ).preflight()

    assert result.available is False
    assert result.reason == "provider_missing"


def test_smoke_preflight_requires_repeatable_finite_unit_nonconstant_cpu_embedding(tmp_path, monkeypatch):
    state = tmp_path / "state.pt"
    state.write_bytes(b"fake-state")
    spec = _spec_for(state)
    cuda_samples = iter((0, 0))
    monkeypatch.setattr(identity_module, "_cuda_allocated_bytes", lambda: next(cuda_samples))

    result = WeSpeakerResNet152LmAdapter(
        state,
        spec=spec,
        embedder=GoodEmbedder(),
    ).preflight(fixture_path=FIXTURE)

    assert result.available is True
    assert result.reason is None
    assert result.descriptor["provider"] == "wespeaker_resnet152_lm"
    assert result.descriptor["smoke"]["cuda_allocated_bytes_before"] == 0
    assert result.descriptor["smoke"]["cuda_allocated_bytes_after"] == 0


def test_smoke_preflight_rejects_cuda_allocation(tmp_path, monkeypatch):
    state = tmp_path / "state.pt"
    state.write_bytes(b"fake-state")
    cuda_samples = iter((0, 128))
    monkeypatch.setattr(identity_module, "_cuda_allocated_bytes", lambda: next(cuda_samples))

    result = WeSpeakerResNet152LmAdapter(
        state,
        spec=_spec_for(state),
        embedder=GoodEmbedder(),
    ).preflight(fixture_path=FIXTURE)

    assert result.available is False
    assert result.reason == "cuda_allocated"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("provider", "other_provider", "provider_mismatch"),
        ("revision", "other_revision", "revision_mismatch"),
        ("embedding_dimension", 128, "dimension_mismatch"),
    ],
)
def test_loaded_provider_manifest_must_match_pinned_contract(tmp_path, field, value, reason):
    state = tmp_path / "state.pt"
    state.write_bytes(b"fake-state")
    spec = _spec_for(state)
    loaded_descriptor = tier_b_provider_manifest(spec)
    loaded_descriptor[field] = value

    result = WeSpeakerResNet152LmAdapter(
        state,
        spec=spec,
        loader=lambda: GoodEmbedder(descriptor=loaded_descriptor),
    ).preflight()

    assert result.available is False
    assert result.reason == reason
    assert result.descriptor["loaded_provider"][field] == value


@pytest.mark.parametrize(
    ("vector", "reason"),
    [
        ([1.0, 0.0], "dimension_mismatch"),
        ([float("nan")] + [0.0] * 255, "smoke_embedding_invalid"),
        ([2.0] + [0.0] * 255, "smoke_embedding_not_unit_normalized"),
        ([0.0625] * 256, "smoke_embedding_constant"),
        ("changing", "smoke_embedding_not_deterministic"),
    ],
)
def test_smoke_preflight_reports_invalid_embedding_shapes(tmp_path, vector, reason):
    state = tmp_path / "state.pt"
    state.write_bytes(b"fake-state")
    embedder = ChangingEmbedder() if vector == "changing" else BadEmbedder(vector)

    result = WeSpeakerResNet152LmAdapter(
        state,
        spec=_spec_for(state),
        embedder=embedder,
    ).preflight(fixture_path=FIXTURE)

    assert result.available is False
    assert result.reason == reason


def test_cli_json_reports_hash_mismatch_before_provider_load(tmp_path):
    state = tmp_path / "state.pt"
    state.write_bytes(b"fake-state")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "moss_transcribe_diarize.speaker_identity_preflight",
            "--state-path",
            str(state),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["available"] is False
    assert payload["reason"] == "asset_hash_mismatch"
    assert payload["expected"]["state_sha256"] == PINNED_TIER_B_ASSET_SPEC.state_sha256


def test_adapter_loads_provider_lazily_and_reuses_loaded_embedder(tmp_path):
    state = tmp_path / "state.pt"
    state.write_bytes(b"fake-state")
    calls = 0

    def loader():
        nonlocal calls
        calls += 1
        return GoodEmbedder(descriptor=tier_b_provider_manifest(_spec_for(state)))

    adapter = WeSpeakerResNet152LmAdapter(state, spec=_spec_for(state), loader=loader)
    assert calls == 0

    assert adapter.preflight().available is True
    assert calls == 1
    assert len(adapter.embed(FIXTURE, [(0.0, 2.0)])) == 256
    assert calls == 1


def test_onnx_embedder_forces_cpu_session_threads_and_feeds_fbank_features(tmp_path, monkeypatch):
    state = tmp_path / "voxceleb_resnet152_LM.onnx"
    state.write_bytes(b"fake-onnx")
    calls = {}

    class SessionOptions:
        inter_op_num_threads = 0
        intra_op_num_threads = 0

    class FakeValueInfo:
        def __init__(self, name, shape):
            self.name = name
            self.shape = shape

    class FakeSession:
        def __init__(self, path, *, sess_options, providers):
            calls["path"] = path
            calls["providers"] = providers
            calls["threads"] = (sess_options.inter_op_num_threads, sess_options.intra_op_num_threads)

        def get_providers(self):
            return ["CPUExecutionProvider"]

        def get_inputs(self):
            return [FakeValueInfo("feats", [1, "T", 80])]

        def get_outputs(self):
            return [FakeValueInfo("embs", [1, 256])]

        def run(self, outputs, inputs):
            calls["outputs"] = outputs
            calls["input_name"] = list(inputs)
            calls["feature_shape"] = inputs["feats"].shape
            return [np.asarray([_unit_vector()], dtype=np.float32)]

    class FakeOrt:
        pass

    FakeOrt.SessionOptions = SessionOptions
    FakeOrt.get_available_providers = staticmethod(lambda: ["CPUExecutionProvider"])
    FakeOrt.InferenceSession = FakeSession
    monkeypatch.setitem(sys.modules, "onnxruntime", FakeOrt)

    embedder = identity_module._OnnxWeSpeakerEmbedder(
        state,
        device="cpu",
        fbank=lambda samples: np.ones((12, 80), dtype=np.float32) * float(np.asarray(samples).shape[0]),
        audio_loader=lambda wav_path: (np.zeros(32000, dtype=np.float32), 16000),
    )

    assert embedder.load()["frontend_version"] == "wespeaker-onnx-fbank-v1"
    assert embedder.embed(FIXTURE, [(0.0, 2.0)]) == _unit_vector()
    assert calls == {
        "path": str(state),
        "providers": ["CPUExecutionProvider"],
        "threads": (1, 1),
        "outputs": ["embs"],
        "input_name": ["feats"],
        "feature_shape": (1, 12, 80),
    }


@pytest.mark.parametrize(
    ("input_shape", "output_shape"),
    [
        (["B", "T", 80], ["B", 256]),
        ([1, "T", 80], [1, 256]),
        ([None, None, 80], [None, 256]),
    ],
)
def test_onnx_preflight_accepts_dynamic_batch_and_time_axes(
    tmp_path,
    monkeypatch,
    input_shape,
    output_shape,
):
    state = tmp_path / "voxceleb_resnet152_LM.onnx"
    state.write_bytes(b"fake-onnx")
    spec = _spec_for(state)
    monkeypatch.setattr(identity_module, "PINNED_TIER_B_ASSET_SPEC", spec)
    _install_fake_ort(
        monkeypatch,
        session_factory=lambda *args, **kwargs: FakeOnnxSession(
            inputs=[FakeOnnxValue("feats", input_shape)],
            outputs=[FakeOnnxValue("embs", output_shape)],
        ),
    )

    result = WeSpeakerResNet152LmAdapter(
        state,
        spec=spec,
        loader=lambda: identity_module._OnnxWeSpeakerEmbedder(state, device="cpu"),
    ).preflight()

    assert result.available is True
    assert result.reason is None


def test_onnx_embedder_real_frontend_matches_wespeaker_fbank_and_cmn(tmp_path, monkeypatch):
    import soundfile as sf
    import torch
    from torchaudio.compliance.kaldi import fbank

    state = tmp_path / "voxceleb_resnet152_LM.onnx"
    state.write_bytes(b"fake-onnx")
    fed_features = []

    class RecordingSession(FakeOnnxSession):
        def run(self, outputs, inputs):
            fed_features.append(np.array(inputs["feats"], copy=True))
            return super().run(outputs, inputs)

    _install_fake_ort(
        monkeypatch,
        session_factory=lambda *args, **kwargs: RecordingSession(),
    )
    embedder = identity_module._OnnxWeSpeakerEmbedder(state, device="cpu")

    embedder.embed(FIXTURE, [(0.0, 2.1)])

    samples, sample_rate = sf.read(
        str(FIXTURE),
        dtype="float32",
        always_2d=False,
    )
    assert sample_rate == 16000
    waveform = torch.as_tensor(
        samples[: int(round(2.1 * sample_rate))],
        dtype=torch.float32,
    ).unsqueeze(0) * float(2**15)
    expected = fbank(
        waveform,
        sample_frequency=16000,
        num_mel_bins=80,
        frame_length=25.0,
        frame_shift=10.0,
        dither=0.0,
        window_type="hamming",
        use_energy=False,
    )
    expected = expected - expected.mean(dim=0, keepdim=True)
    expected = expected.unsqueeze(0).cpu().numpy().astype("float32", copy=False)

    assert len(fed_features) == 1
    assert fed_features[0].shape == (1, 208, 80)
    assert fed_features[0].dtype == np.float32
    np.testing.assert_array_equal(fed_features[0], expected)
    assert float(np.abs(fed_features[0][0].mean(axis=0)).max()) < 1e-4


def test_onnx_embedder_slices_each_interval_before_frontend(tmp_path, monkeypatch):
    state = tmp_path / "voxceleb_resnet152_LM.onnx"
    state.write_bytes(b"fake-onnx")
    fed_features = []

    class RecordingSession(FakeOnnxSession):
        def run(self, outputs, inputs):
            fed_features.append(np.array(inputs["feats"], copy=True))
            return super().run(outputs, inputs)

    _install_fake_ort(
        monkeypatch,
        session_factory=lambda *args, **kwargs: RecordingSession(),
    )
    embedder = identity_module._OnnxWeSpeakerEmbedder(state, device="cpu")
    feature_sample_counts = []
    real_features = embedder._features

    def recording_features(samples):
        feature_sample_counts.append(len(samples))
        return real_features(samples)

    embedder._features = recording_features
    embedder.embed(FIXTURE, [(0.0, 0.5), (1.0, 2.0)])

    assert feature_sample_counts == [8000, 16000]
    assert [features.shape for features in fed_features] == [
        (1, 48, 80),
        (1, 98, 80),
    ]


@pytest.mark.parametrize(
    ("available_providers", "session", "reason"),
    [
        (["CUDAExecutionProvider"], None, "cpu_provider_unavailable"),
        (
            ["CPUExecutionProvider"],
            lambda: FakeOnnxSession(session_providers=["CPUExecutionProvider", "CUDAExecutionProvider"]),
            "execution_provider_mismatch",
        ),
        (
            ["CPUExecutionProvider"],
            lambda: FakeOnnxSession(inputs=[FakeOnnxValue("audio", [1, "T", 80])]),
            "onnx_input_mismatch",
        ),
        (
            ["CPUExecutionProvider"],
            lambda: FakeOnnxSession(inputs=[FakeOnnxValue("feats", [1, "T", 79])]),
            "onnx_input_mismatch",
        ),
        (
            ["CPUExecutionProvider"],
            lambda: FakeOnnxSession(inputs=[FakeOnnxValue("feats", [2, "T", 80])]),
            "onnx_input_mismatch",
        ),
        (
            ["CPUExecutionProvider"],
            lambda: FakeOnnxSession(outputs=[FakeOnnxValue("embedding", [1, 256])]),
            "onnx_output_mismatch",
        ),
        (
            ["CPUExecutionProvider"],
            lambda: FakeOnnxSession(outputs=[FakeOnnxValue("embs", [1, 128])]),
            "onnx_output_mismatch",
        ),
        (
            ["CPUExecutionProvider"],
            lambda: FakeOnnxSession(outputs=[FakeOnnxValue("embs", [2, 256])]),
            "onnx_output_mismatch",
        ),
    ],
)
def test_onnx_preflight_fails_closed_on_provider_and_io_contract(
    tmp_path,
    monkeypatch,
    available_providers,
    session,
    reason,
):
    state = tmp_path / "voxceleb_resnet152_LM.onnx"
    state.write_bytes(b"fake-onnx")
    _install_fake_ort(
        monkeypatch,
        available_providers=available_providers,
        session_factory=lambda *args, **kwargs: session() if session is not None else None,
    )

    adapter = WeSpeakerResNet152LmAdapter(
        state,
        spec=_spec_for(state),
        loader=lambda: identity_module._OnnxWeSpeakerEmbedder(state, device="cpu"),
    )

    result = adapter.preflight()

    assert result.available is False
    assert result.reason == reason


@pytest.mark.parametrize(
    ("audio_loader", "fbank", "session", "match"),
    [
        (
            lambda wav_path: (np.zeros(32000, dtype=np.float32), 8000),
            lambda samples: np.ones((12, 80), dtype=np.float32),
            lambda: FakeOnnxSession(),
            "16 kHz mono",
        ),
        (
            lambda wav_path: (np.zeros((32000, 2), dtype=np.float32), 16000),
            lambda samples: np.ones((12, 80), dtype=np.float32),
            lambda: FakeOnnxSession(),
            "16 kHz mono",
        ),
        (
            lambda wav_path: (np.zeros(32000, dtype=np.float32), 16000),
            lambda samples: np.ones((12, 79), dtype=np.float32),
            lambda: FakeOnnxSession(),
            r"\[1,T,80\]",
        ),
        (
            lambda wav_path: (np.zeros(32000, dtype=np.float32), 16000),
            lambda samples: np.ones((12, 80), dtype=np.float32),
            lambda: FakeOnnxSession(run_output=np.zeros((1, 128), dtype=np.float32)),
            r"\[1,256\]",
        ),
        (
            lambda wav_path: (np.zeros(32000, dtype=np.float32), 16000),
            lambda samples: np.ones((12, 80), dtype=np.float32),
            lambda: FakeOnnxSession(run_output=np.asarray([[float("nan")] + [0.0] * 255], dtype=np.float32)),
            "finite unit vectors",
        ),
    ],
)
def test_onnx_embedder_rejects_audio_feature_and_output_contract_violations(
    tmp_path,
    monkeypatch,
    audio_loader,
    fbank,
    session,
    match,
):
    state = tmp_path / "voxceleb_resnet152_LM.onnx"
    state.write_bytes(b"fake-onnx")
    _install_fake_ort(monkeypatch, session_factory=lambda *args, **kwargs: session())
    embedder = identity_module._OnnxWeSpeakerEmbedder(
        state,
        device="cpu",
        fbank=fbank,
        audio_loader=audio_loader,
    )

    with pytest.raises(ValueError, match=match):
        embedder.embed(FIXTURE, [(0.0, 2.0)])


def test_web_cli_enablement_uses_explicit_cli_arguments_only(monkeypatch):
    from moss_transcribe_diarize.app.web_cli import parse_args

    monkeypatch.setenv("MOSS_SPEAKER_IDENTITY_TIER_B", "1")
    monkeypatch.setenv("MOSS_SPEAKER_IDENTITY_STATE", "/env/state.pt")
    monkeypatch.setenv("MOSS_SPEAKER_IDENTITY_FIXTURE", "/env/fixture.wav")
    monkeypatch.setenv("MOSS_LIVE_ENABLED", "1")
    monkeypatch.setenv("MOSS_LIVE_PROVIDER_MANIFEST", "/env/live-provider.json")
    monkeypatch.setenv("MOSS_LIVE_AUTH_STATE", "/env/live-auth.json")
    monkeypatch.setenv("MOSS_LIVE_TLS_CERTFILE", "/env/live.crt")
    monkeypatch.setenv("MOSS_LIVE_TLS_KEYFILE", "/env/live.key")
    monkeypatch.setattr(sys, "argv", ["mtd-subtitle-web"])

    disabled = parse_args()

    assert disabled.speaker_identity_tier_b is False
    assert disabled.speaker_identity_state is None
    assert disabled.speaker_identity_fixture is None
    assert disabled.live is False
    assert disabled.live_provider_manifest is None
    assert disabled.live_auth_state is None
    assert disabled.live_tls_certfile is None
    assert disabled.live_tls_keyfile is None

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mtd-subtitle-web",
            "--speaker-identity-tier-b",
            "--speaker-identity-state",
            "/cli/state.pt",
            "--speaker-identity-fixture",
            "/cli/fixture.wav",
            "--live",
            "--live-provider-manifest",
            "/cli/live-provider.json",
            "--live-auth-state",
            "/cli/live-auth.json",
            "--live-tls-certfile",
            "/cli/live.crt",
            "--live-tls-keyfile",
            "/cli/live.key",
        ],
    )
    enabled = parse_args()

    assert enabled.speaker_identity_tier_b is True
    assert enabled.speaker_identity_state == "/cli/state.pt"
    assert enabled.speaker_identity_fixture == "/cli/fixture.wav"
    assert enabled.live is True
    assert enabled.live_provider_manifest == "/cli/live-provider.json"
    assert enabled.live_auth_state == "/cli/live-auth.json"
    assert enabled.live_tls_certfile == "/cli/live.crt"
    assert enabled.live_tls_keyfile == "/cli/live.key"


def test_web_cli_live_main_supplies_auth_tls_and_disables_proxy_headers(tmp_path, monkeypatch):
    from moss_transcribe_diarize.app import web_cli

    certfile = tmp_path / "live.der"
    certfile.write_bytes(b"configured leaf cert")
    keyfile = tmp_path / "live.key"
    keyfile.write_text("private key placeholder", encoding="utf-8")
    state = tmp_path / "live-auth.json"
    calls = {}

    def create_app(**kwargs):
        calls["create_app"] = kwargs
        return "app"

    def run(app, **kwargs):
        calls["uvicorn"] = (app, kwargs)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mtd-subtitle-web",
            "--live",
            "--live-provider-manifest",
            str(tmp_path / "live-provider.json"),
            "--live-auth-state",
            str(state),
            "--live-tls-certfile",
            str(certfile),
            "--live-tls-keyfile",
            str(keyfile),
        ],
    )
    monkeypatch.setattr(web_cli, "_live_runtime_factory", lambda args: "runtime-factory")
    monkeypatch.setattr(web_cli, "create_app", create_app)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=run))

    web_cli.main()

    assert calls["create_app"]["live_runtime_factory"] == "runtime-factory"
    assert calls["create_app"]["live_auth_state_path"] == state
    assert calls["create_app"]["live_server_cert_sha256"] == hashlib.sha256(b"configured leaf cert").hexdigest()
    assert calls["uvicorn"] == (
        "app",
        {
            "host": "127.0.0.1",
            "port": 7860,
            "ssl_certfile": str(certfile),
            "ssl_keyfile": str(keyfile),
            "proxy_headers": False,
        },
    )


@pytest.mark.parametrize(
    ("missing_attribute", "missing_flag"),
    [
        ("live_auth_state", "--live-auth-state"),
        ("live_tls_certfile", "--live-tls-certfile"),
        ("live_tls_keyfile", "--live-tls-keyfile"),
    ],
)
def test_web_cli_live_startup_names_each_missing_security_input(
    tmp_path,
    missing_attribute,
    missing_flag,
):
    from moss_transcribe_diarize.app.web_cli import _live_startup_config

    certfile = tmp_path / "live.der"
    certfile.write_bytes(b"configured leaf cert")
    values = {
        "live_auth_state": str(tmp_path / "live-auth.json"),
        "live_tls_certfile": str(certfile),
        "live_tls_keyfile": str(tmp_path / "live.key"),
    }
    values[missing_attribute] = None

    with pytest.raises(SystemExit) as exc_info:
        _live_startup_config(SimpleNamespace(live=True, **values))

    assert missing_flag in str(exc_info.value)


def test_web_cli_live_factory_is_manifest_backed_and_default_off(monkeypatch):
    from moss_transcribe_diarize.app import live_provider_bundle
    from moss_transcribe_diarize.app.web_cli import _live_runtime_factory

    assert _live_runtime_factory(SimpleNamespace(live=False, live_provider_manifest=None)) is None

    with pytest.raises(SystemExit, match="--live-provider-manifest"):
        _live_runtime_factory(SimpleNamespace(live=True, live_provider_manifest=None))

    calls = []

    class Config:
        @classmethod
        def from_manifest(cls, path):
            calls.append(("manifest", path))
            return "config"

    def build_factory(config, runner):
        calls.append(("build", config, runner))
        return "factory"

    monkeypatch.setattr(live_provider_bundle, "LiveProviderBundleConfig", Config)
    monkeypatch.setattr(live_provider_bundle, "build_live_runtime_factory", build_factory)
    args = SimpleNamespace(
        live=True,
        live_provider_manifest="/provider/live-provider.json",
        backend="hf",
        model="fake-model",
        vllm_model=None,
        vllm_base_url=None,
        vllm_api_key="EMPTY",
        vllm_timeout=600.0,
        device="cpu",
        dtype="float32",
    )

    assert _live_runtime_factory(args) == "factory"
    assert calls[0] == ("manifest", "/provider/live-provider.json")
    assert calls[1][0:2] == ("build", "config")
    assert hasattr(calls[1][2], "transcribe")


def test_start_web_is_the_single_environment_adapter(tmp_path):
    fake_home = tmp_path / "home"
    capture_path = tmp_path / "args.txt"
    executable = fake_home / ".local/share/moss-transcribe-diarize/venv/bin/mtd-subtitle-web"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"$CAPTURE_ARGS\"\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    getent = fake_bin / "getent"
    getent.write_text(
        "#!/usr/bin/env bash\nprintf 'tester:x:1000:1000::%s:/bin/bash\\n' \"$FAKE_HOME\"\n",
        encoding="utf-8",
    )
    getent.chmod(0o755)
    env = os.environ | {
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "FAKE_HOME": str(fake_home),
        "CAPTURE_ARGS": str(capture_path),
        "MOSS_SPEAKER_IDENTITY_TIER_B": "1",
        "MOSS_SPEAKER_IDENTITY_STATE": "/provider/state.pt",
        "MOSS_SPEAKER_IDENTITY_FIXTURE": "/provider/smoke.wav",
        "MOSS_LIVE_ENABLED": "1",
        "MOSS_LIVE_PROVIDER_MANIFEST": "/provider/live-provider.json",
        "MOSS_LIVE_AUTH_STATE": "/provider/live-auth.json",
        "MOSS_LIVE_TLS_CERTFILE": "/provider/live.crt",
        "MOSS_LIVE_TLS_KEYFILE": "/provider/live.key",
    }

    enabled = subprocess.run(
        ["bash", "ops/start-web.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert enabled.returncode == 0, enabled.stderr
    enabled_args = capture_path.read_text(encoding="utf-8").splitlines()
    assert enabled_args[-14:] == [
        "--speaker-identity-tier-b",
        "--speaker-identity-state",
        "/provider/state.pt",
        "--speaker-identity-fixture",
        "/provider/smoke.wav",
        "--live",
        "--live-provider-manifest",
        "/provider/live-provider.json",
        "--live-auth-state",
        "/provider/live-auth.json",
        "--live-tls-certfile",
        "/provider/live.crt",
        "--live-tls-keyfile",
        "/provider/live.key",
    ]

    disabled = subprocess.run(
        ["bash", "ops/start-web.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env | {"MOSS_SPEAKER_IDENTITY_TIER_B": "0", "MOSS_LIVE_ENABLED": "0"},
    )
    assert disabled.returncode == 0, disabled.stderr
    disabled_args = capture_path.read_text(encoding="utf-8").splitlines()
    assert not any(arg.startswith("--speaker-identity") for arg in disabled_args)
    assert "--live" not in disabled_args
    assert "--live-provider-manifest" not in disabled_args

    invalid = subprocess.run(
        ["bash", "ops/start-web.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env | {"MOSS_SPEAKER_IDENTITY_TIER_B": "true"},
    )
    assert invalid.returncode == 2
    assert "must be 0 or 1" in invalid.stderr

    invalid_live = subprocess.run(
        ["bash", "ops/start-web.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env | {"MOSS_LIVE_ENABLED": "true"},
    )
    assert invalid_live.returncode == 2
    assert "MOSS_LIVE_ENABLED must be 0 or 1" in invalid_live.stderr

    missing_live_manifest = subprocess.run(
        ["bash", "ops/start-web.sh"],
        check=False,
        capture_output=True,
        text=True,
        env={key: value for key, value in (env | {"MOSS_LIVE_ENABLED": "1"}).items() if key != "MOSS_LIVE_PROVIDER_MANIFEST"},
    )
    assert missing_live_manifest.returncode != 0
    assert "MOSS_LIVE_PROVIDER_MANIFEST is required" in missing_live_manifest.stderr


def _spec_for(path: Path) -> TierBAssetSpec:
    return TierBAssetSpec(state_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def _unit_vector() -> list[float]:
    return [1.0] + [0.0] * 255


class GoodEmbedder:
    def __init__(self, *, descriptor=None):
        self.descriptor = dict(descriptor or tier_b_provider_manifest())

    def load(self):
        return dict(self.descriptor)

    def embed(self, wav_path, intervals):
        assert Path(wav_path).exists()
        assert intervals
        return _unit_vector()


class BadEmbedder:
    def __init__(self, vector):
        self.vector = vector

    def embed(self, wav_path, intervals):
        del wav_path, intervals
        return self.vector


class ChangingEmbedder:
    def __init__(self):
        self.calls = 0

    def embed(self, wav_path, intervals):
        del wav_path, intervals
        self.calls += 1
        vector = _unit_vector()
        if self.calls > 1:
            vector = [0.0, 1.0] + [0.0] * 254
        return vector


class LazyMissingEmbedder:
    def load(self):
        raise ImportError("missing pyannote")

    def embed(self, wav_path, intervals):
        raise AssertionError("embed must not run after provider load fails")


class FakeOnnxValue:
    def __init__(self, name, shape):
        self.name = name
        self.shape = shape


class FakeOnnxSession:
    def __init__(
        self,
        *,
        session_providers=None,
        inputs=None,
        outputs=None,
        run_output=None,
    ):
        self.session_providers = list(session_providers or ["CPUExecutionProvider"])
        self.inputs = list(inputs or [FakeOnnxValue("feats", [1, "T", 80])])
        self.outputs = list(outputs or [FakeOnnxValue("embs", [1, 256])])
        self.run_output = (
            np.asarray([_unit_vector()], dtype=np.float32)
            if run_output is None
            else run_output
        )

    def get_providers(self):
        return self.session_providers

    def get_inputs(self):
        return self.inputs

    def get_outputs(self):
        return self.outputs

    def run(self, outputs, inputs):
        assert outputs == ["embs"]
        assert list(inputs) == ["feats"]
        return [self.run_output]


def _install_fake_ort(
    monkeypatch,
    *,
    available_providers=None,
    session_factory=lambda *args, **kwargs: FakeOnnxSession(),
):
    class SessionOptions:
        inter_op_num_threads = 0
        intra_op_num_threads = 0

    class FakeOrt:
        pass

    FakeOrt.SessionOptions = SessionOptions
    FakeOrt.get_available_providers = staticmethod(
        lambda: list(available_providers or ["CPUExecutionProvider"])
    )
    FakeOrt.InferenceSession = session_factory
    monkeypatch.setitem(sys.modules, "onnxruntime", FakeOrt)
