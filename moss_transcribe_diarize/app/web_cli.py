from __future__ import annotations

import argparse
import hashlib
import ssl
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
        help="Enable the default-off file-mode Tier B speaker identity provider.",
    )
    parser.add_argument(
        "--speaker-identity-state",
        help="Existing local WeSpeaker ResNet152-LM state file required when Tier B is enabled.",
    )
    parser.add_argument(
        "--speaker-identity-fixture",
        help="Tiny WAV fixture required for Tier B smoke preflight when enabled.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable default-off live HTTP routes with an explicit offline provider manifest.",
    )
    parser.add_argument(
        "--live-provider-manifest",
        help="Offline live provider manifest required when --live is enabled.",
    )
    parser.add_argument(
        "--live-auth-state",
        help="Private live access registry state file required when --live is enabled.",
    )
    parser.add_argument(
        "--live-tls-certfile",
        help="TLS certificate file required when --live is enabled.",
    )
    parser.add_argument(
        "--live-tls-keyfile",
        help="TLS private key file required when --live is enabled.",
    )
    parser.add_argument(
        "--live-helper-lease-seconds",
        type=float,
        default=None,
        help="Strictly positive helper lease required when --live is enabled.",
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


class _LiveCliRunnerProxy:
    def __init__(self, args: argparse.Namespace):
        self._args = args
        self._runner = None
        self.model_path = str(args.vllm_model or args.model)

    def transcribe(self, audio_path, **kwargs):
        if self._runner is None:
            self._runner = self._build_runner()
            self.model_path = getattr(self._runner, "model_path", self.model_path)
        return self._runner.transcribe(audio_path, **kwargs)

    def _build_runner(self):
        if self._args.backend == "vllm":
            if not self._args.vllm_base_url:
                raise ValueError("--vllm-base-url is required when backend='vllm'.")
            from .vllm_runner import VllmRunner

            return VllmRunner(
                base_url=self._args.vllm_base_url,
                model=self._args.vllm_model or str(self._args.model),
                api_key=self._args.vllm_api_key,
                timeout=self._args.vllm_timeout,
            )
        from .model_runner import ModelRunner

        return ModelRunner(
            Path(self._args.model).expanduser(),
            device=self._args.device,
            dtype=self._args.dtype,
        )


def _live_runtime_factory(args: argparse.Namespace):
    if not args.live:
        return None
    if not args.live_provider_manifest:
        raise SystemExit("--live-provider-manifest is required when --live is enabled.")
    from .live_provider_bundle import LiveProviderBundleConfig, build_live_runtime_factory

    config = LiveProviderBundleConfig.from_manifest(args.live_provider_manifest)
    return build_live_runtime_factory(config, _LiveCliRunnerProxy(args))


def _live_startup_config(args: argparse.Namespace) -> dict[str, object]:
    if not args.live:
        return {
            "live_auth_state_path": None,
            "live_server_cert_sha256": None,
            "live_helper_lease_seconds": None,
            "ssl_certfile": None,
            "ssl_keyfile": None,
        }
    missing = [
        flag
        for flag, value in (
            ("--live-auth-state", args.live_auth_state),
            ("--live-tls-certfile", args.live_tls_certfile),
            ("--live-tls-keyfile", args.live_tls_keyfile),
            ("--live-helper-lease-seconds", args.live_helper_lease_seconds),
        )
        if value is None
    ]
    if missing:
        raise SystemExit(f"{', '.join(missing)} are required when --live is enabled.")
    if args.live_helper_lease_seconds <= 0:
        raise SystemExit("--live-helper-lease-seconds must be positive when --live is enabled.")
    certfile = Path(args.live_tls_certfile).expanduser()
    return {
        "live_auth_state_path": Path(args.live_auth_state).expanduser(),
        "live_server_cert_sha256": _certificate_sha256(certfile),
        "live_helper_lease_seconds": args.live_helper_lease_seconds,
        "ssl_certfile": str(certfile),
        "ssl_keyfile": str(Path(args.live_tls_keyfile).expanduser()),
    }


def _certificate_sha256(certfile: Path) -> str:
    data = certfile.read_bytes()
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        der = data
    else:
        der = ssl.PEM_cert_to_DER_cert(text) if "-----BEGIN CERTIFICATE-----" in text else data
    return hashlib.sha256(der).hexdigest()


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install uvicorn to run mtd-subtitle-web.") from exc

    args = parse_args()
    live_runtime_factory = _live_runtime_factory(args)
    live_startup = _live_startup_config(args)
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
        live_enabled=args.live,
        live_runtime_factory=live_runtime_factory,
        live_auth_state_path=live_startup["live_auth_state_path"],
        live_server_cert_sha256=live_startup["live_server_cert_sha256"],
        live_helper_lease_seconds=live_startup["live_helper_lease_seconds"],
    )
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        ssl_certfile=live_startup["ssl_certfile"],
        ssl_keyfile=live_startup["ssl_keyfile"],
        proxy_headers=False,
    )

if __name__ == "__main__":
    main()
