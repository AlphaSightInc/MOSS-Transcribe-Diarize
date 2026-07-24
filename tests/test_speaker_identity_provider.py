from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

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
        "state_sha256": "b0446afc11bb51b0eb79559b60508e967310980cf1a5580804473104024239bc",
        "embedding_dimension": 256,
        "frontend_version": "pytorch-offline-trial",
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


def test_web_cli_enablement_uses_explicit_cli_arguments_only(monkeypatch):
    from moss_transcribe_diarize.app.web_cli import parse_args

    monkeypatch.setenv("MOSS_SPEAKER_IDENTITY_TIER_B", "1")
    monkeypatch.setenv("MOSS_SPEAKER_IDENTITY_STATE", "/env/state.pt")
    monkeypatch.setenv("MOSS_SPEAKER_IDENTITY_FIXTURE", "/env/fixture.wav")
    monkeypatch.setenv("MOSS_LIVE_ENABLED", "1")
    monkeypatch.setenv("MOSS_LIVE_PROVIDER_MANIFEST", "/env/live-provider.json")
    monkeypatch.setattr(sys, "argv", ["mtd-subtitle-web"])

    disabled = parse_args()

    assert disabled.speaker_identity_tier_b is False
    assert disabled.speaker_identity_state is None
    assert disabled.speaker_identity_fixture is None
    assert disabled.live is False
    assert disabled.live_provider_manifest is None

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
        ],
    )
    enabled = parse_args()

    assert enabled.speaker_identity_tier_b is True
    assert enabled.speaker_identity_state == "/cli/state.pt"
    assert enabled.speaker_identity_fixture == "/cli/fixture.wav"
    assert enabled.live is True
    assert enabled.live_provider_manifest == "/cli/live-provider.json"


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
    assert enabled_args[-8:] == [
        "--speaker-identity-tier-b",
        "--speaker-identity-state",
        "/provider/state.pt",
        "--speaker-identity-fixture",
        "/provider/smoke.wav",
        "--live",
        "--live-provider-manifest",
        "/provider/live-provider.json",
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
