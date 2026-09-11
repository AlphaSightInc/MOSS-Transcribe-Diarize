"""Compose the Account product's replaceable inference runners.

This module is deliberately below the web product.  It knows model/provider objects and
the one inference-option rule shared by File and Live terminal decoding; it knows nothing
about HTTP routes, Account authority, persistence, or product scheduling.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def resolve_prompt(prompt: str | None, default_prompt: str | None = None) -> str:
    """Resolve omitted/blank prompts identically for live, File and terminal requests."""
    from moss_transcribe_diarize.inference_utils import DEFAULT_PROMPT

    for value in (prompt, default_prompt):
        if value is not None and value.strip():
            return value
    return DEFAULT_PROMPT


def resolve_inference_options(
    *,
    prompt: str | None,
    max_length: int | None,
    max_new_tokens: int | None,
    decoding: str | None,
    temperature: float | None,
    default_prompt: str | None,
    default_max_length: int,
    default_max_new_tokens: int,
    default_decoding: str,
    default_temperature: float | None,
    max_length_cap: int | None,
) -> dict[str, Any]:
    """Resolve one decode's overrides against the deployed inference configuration."""

    prompt_value = resolve_prompt(prompt, default_prompt)
    max_length_value = default_max_length if max_length is None else int(max_length)
    max_new_tokens_value = (
        default_max_new_tokens if max_new_tokens is None else int(max_new_tokens)
    )
    decoding_value = decoding or default_decoding
    if decoding_value not in {"greedy", "sample"}:
        raise ValueError("decoding must be greedy or sample.")
    if max_length_value <= 0:
        raise ValueError("max_length must be greater than 0.")
    if max_length_cap is not None and max_length_value > max_length_cap:
        raise ValueError(f"max_len must be less than or equal to {max_length_cap}.")
    if max_new_tokens_value <= 0:
        raise ValueError("max_new_tokens must be greater than 0.")

    temperature_value = default_temperature if temperature is None else float(temperature)
    if decoding_value == "greedy":
        temperature_value = None
    else:
        if temperature_value is None:
            temperature_value = 1.0
        if temperature_value <= 0:
            raise ValueError("temperature must be greater than 0.")

    return {
        "prompt": prompt_value,
        "max_length": max_length_value,
        "max_new_tokens": max_new_tokens_value,
        "decoding": decoding_value,
        "temperature": temperature_value,
    }


def build_file_runner(
    *,
    model_path: str | Path,
    device: str,
    dtype: str,
    backend: str,
    vllm_base_url: str | None,
    vllm_model: str | None,
    vllm_api_key: str | None,
    vllm_timeout: float,
):
    """Build the single runner shared by Account File and Live terminal decoding."""

    if backend == "vllm":
        if not vllm_base_url:
            raise ValueError("--vllm-base-url is required when backend='vllm'.")
        from .speaker_identity import IdentityResolver, IdentityResolverConfig
        from .vllm_runner import VllmRunner
        from .windowed_transcription import WindowedRunner

        return WindowedRunner(
            VllmRunner(
                base_url=vllm_base_url,
                model=vllm_model or str(model_path),
                api_key=vllm_api_key,
                timeout=vllm_timeout,
            ),
            identity_resolver=IdentityResolver(config=IdentityResolverConfig()),
        )
    from .model_runner import ModelRunner

    return ModelRunner(Path(model_path), device=device, dtype=dtype)


class LazyLiveRunner:
    """Keep the rolling runner lazy and independent from the File runner's thread."""

    def __init__(
        self,
        *,
        model_path: str | Path,
        device: str,
        dtype: str,
        backend: str,
        vllm_base_url: str | None,
        vllm_model: str | None,
        vllm_api_key: str | None,
        vllm_timeout: float,
    ) -> None:
        self._configuration = {
            "model_path": model_path,
            "device": device,
            "dtype": dtype,
            "backend": backend,
            "vllm_base_url": vllm_base_url,
            "vllm_model": vllm_model,
            "vllm_api_key": vllm_api_key,
            "vllm_timeout": vllm_timeout,
        }
        self._runner: Any | None = None
        self.model_path = str(vllm_model or model_path)

    def transcribe(self, audio_path: str | Path, **kwargs: object):
        if self._runner is None:
            self._runner = self._build_runner()
            self.model_path = getattr(self._runner, "model_path", self.model_path)
        return self._runner.transcribe(audio_path, **kwargs)

    def _build_runner(self):
        config = self._configuration
        if config["backend"] == "vllm":
            if not config["vllm_base_url"]:
                raise ValueError("--vllm-base-url is required when backend='vllm'.")
            from .vllm_runner import VllmRunner

            return VllmRunner(
                base_url=config["vllm_base_url"],
                model=config["vllm_model"] or str(config["model_path"]),
                api_key=config["vllm_api_key"],
                timeout=config["vllm_timeout"],
            )
        from .model_runner import ModelRunner

        return ModelRunner(
            Path(config["model_path"]).expanduser(),
            device=str(config["device"]),
            dtype=str(config["dtype"]),
        )


def build_terminal_finalizer(
    *,
    runner: object,
    prompt: str | None,
    max_length: int,
    max_new_tokens: int,
    decoding: str,
    temperature: float | None,
    max_length_cap: int | None,
):
    """Bind Live's last listener to the exact File runner and inference rule."""

    from .live_transcript_convergence import TerminalTranscriptFinalizer

    return TerminalTranscriptFinalizer(
        runner=runner,
        transcribe_kwargs=resolve_inference_options(
            prompt=None,
            max_length=None,
            max_new_tokens=None,
            decoding=None,
            temperature=None,
            default_prompt=prompt,
            default_max_length=max_length,
            default_max_new_tokens=max_new_tokens,
            default_decoding=decoding,
            default_temperature=temperature,
            max_length_cap=max_length_cap,
        ),
    )
