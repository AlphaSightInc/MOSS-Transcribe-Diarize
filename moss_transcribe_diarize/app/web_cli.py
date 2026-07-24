from __future__ import annotations

import argparse
import os
from pathlib import Path

from moss_transcribe_diarize.inference_utils import DEFAULT_PROMPT

from .cli import DEFAULT_MODEL
from .server import create_app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local MOSS subtitle web app.")
    parser.add_argument("--backend", choices=["hf", "vllm"], default="hf")
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--vllm-base-url", default=None, help="OpenAI-compatible vLLM base URL, e.g. http://127.0.0.1:8000/v1.")
    parser.add_argument("--vllm-model", default=None, help="vLLM served model name. Defaults to --model.")
    parser.add_argument("--vllm-api-key", default="EMPTY")
    parser.add_argument("--vllm-timeout", type=float, default=600.0)
    parser.add_argument(
        "--speaker-identity-tier-b",
        action="store_true",
        default=_env_flag("MOSS_SPEAKER_IDENTITY_TIER_B", default=False),
        help="Enable the default-off file-mode Tier B speaker identity provider.",
    )
    parser.add_argument(
        "--speaker-identity-state",
        default=os.environ.get("MOSS_SPEAKER_IDENTITY_STATE"),
        help="Existing local WeSpeaker ResNet152-LM state file required when Tier B is enabled.",
    )
    parser.add_argument(
        "--speaker-identity-fixture",
        default=os.environ.get("MOSS_SPEAKER_IDENTITY_FIXTURE"),
        help="Optional tiny WAV fixture for Tier B smoke preflight.",
    )
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dtype", default="bf16")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--max-new-tokens", type=int, default=2048)
    parser.add_argument("--max-len", type=int, default=131072)
    parser.add_argument("--decoding", choices=["greedy", "sample"], default="greedy")
    parser.add_argument("--temperature", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install uvicorn to run mtd-subtitle-web.") from exc

    args = parse_args()
    app = create_app(
        model_path=Path(args.model).expanduser(),
        runs_dir=Path(args.runs_dir).expanduser(),
        device=args.device,
        dtype=args.dtype,
        prompt=args.prompt,
        max_length=args.max_len,
        max_new_tokens=args.max_new_tokens,
        decoding=args.decoding,
        temperature=args.temperature,
        backend=args.backend,
        vllm_base_url=args.vllm_base_url,
        vllm_model=args.vllm_model,
        vllm_api_key=args.vllm_api_key,
        vllm_timeout=args.vllm_timeout,
        speaker_identity_tier_b=args.speaker_identity_tier_b,
        speaker_identity_state=args.speaker_identity_state,
        speaker_identity_fixture=args.speaker_identity_fixture,
    )
    uvicorn.run(app, host=args.host, port=args.port)


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    main()
