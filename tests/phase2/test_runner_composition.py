from __future__ import annotations

from pathlib import Path
import sys
from types import ModuleType

import pytest

from moss_transcribe_diarize.app import runner_composition


def test_inference_options_share_file_defaults_and_drop_greedy_temperature():
    assert runner_composition.resolve_inference_options(
        prompt=" ",
        max_length=None,
        max_new_tokens=None,
        decoding=None,
        temperature=0.25,
        default_prompt="deployed prompt",
        default_max_length=4096,
        default_max_new_tokens=512,
        default_decoding="greedy",
        default_temperature=1.0,
        max_length_cap=4096,
    ) == {
        "prompt": "deployed prompt",
        "max_length": 4096,
        "max_new_tokens": 512,
        "decoding": "greedy",
        "temperature": None,
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"decoding": "beam"}, "decoding must be greedy or sample"),
        ({"max_length": 0}, "max_length must be greater than 0"),
        ({"max_length": 4097}, "max_len must be less than or equal to 4096"),
        ({"max_new_tokens": 0}, "max_new_tokens must be greater than 0"),
        ({"decoding": "sample", "temperature": 0}, "temperature must be greater than 0"),
    ],
)
def test_inference_options_retain_the_deployed_refusal_contract(overrides, message):
    values = {
        "prompt": None,
        "max_length": None,
        "max_new_tokens": None,
        "decoding": None,
        "temperature": None,
        "default_prompt": None,
        "default_max_length": 4096,
        "default_max_new_tokens": 512,
        "default_decoding": "greedy",
        "default_temperature": 1.0,
        "max_length_cap": 4096,
        **overrides,
    }
    with pytest.raises(ValueError, match=message):
        runner_composition.resolve_inference_options(**values)


def test_live_runner_stays_lazy_and_reuses_one_runner(monkeypatch, tmp_path: Path):
    built: list[tuple[Path, str, str]] = []

    class Runner:
        model_path = "loaded-model"

        def __init__(self, model_path, *, device, dtype):
            built.append((model_path, device, dtype))

        def transcribe(self, audio_path, **kwargs):
            return (audio_path, kwargs)

    model_runner = ModuleType("moss_transcribe_diarize.app.model_runner")
    model_runner.ModelRunner = Runner  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, model_runner.__name__, model_runner)
    lazy = runner_composition.LazyLiveRunner(
        model_path=tmp_path / "model",
        device="cpu",
        dtype="float32",
        backend="hf",
        vllm_base_url=None,
        vllm_model=None,
        vllm_api_key=None,
        vllm_timeout=30,
    )

    assert built == []
    assert lazy.transcribe("first.wav", decoding="greedy") == (
        "first.wav",
        {"decoding": "greedy"},
    )
    assert lazy.transcribe("second.wav") == ("second.wav", {})
    assert built == [(tmp_path / "model", "cpu", "float32")]
    assert lazy.model_path == "loaded-model"
