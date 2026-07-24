from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

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
        loader=lambda: (_ for _ in ()).throw(ImportError("missing pyannote")),
    ).preflight()

    assert result.available is False
    assert result.reason == "provider_missing"


def test_smoke_preflight_requires_repeatable_finite_unit_nonconstant_embedding(tmp_path):
    state = tmp_path / "state.pt"
    state.write_bytes(b"fake-state")
    spec = _spec_for(state)

    result = WeSpeakerResNet152LmAdapter(
        state,
        spec=spec,
        embedder=GoodEmbedder(),
    ).preflight(fixture_path=FIXTURE)

    assert result.available is True
    assert result.reason is None
    assert result.descriptor["provider"] == "wespeaker_resnet152_lm"
    assert result.descriptor["smoke"]["cuda_allocated_bytes_after"] in (None, 0)


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


def test_cli_json_reports_unavailable_without_importing_provider(tmp_path):
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
        return GoodEmbedder()

    adapter = WeSpeakerResNet152LmAdapter(state, spec=_spec_for(state), loader=loader)
    assert calls == 0

    assert adapter.preflight().available is True
    assert calls == 1
    assert len(adapter.embed(FIXTURE, [(0.0, 2.0)])) == 256
    assert calls == 1


def _spec_for(path: Path) -> TierBAssetSpec:
    return TierBAssetSpec(state_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def _unit_vector() -> list[float]:
    return [1.0] + [0.0] * 255


class GoodEmbedder:
    descriptor = {"provider": "fake-good"}

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
