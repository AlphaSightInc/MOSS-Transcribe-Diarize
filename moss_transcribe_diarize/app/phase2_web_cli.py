"""The packaged Account HTTPS startup path.

This command is the complete product process surface: it builds only the Account app,
binds its canonical SQLite database, and hands the configured certificate to Uvicorn.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .phase2 import DEFAULT_PHASE2_DATABASE_PATH, create_phase2_app
from .phase2_audio import DEFAULT_PHASE2_MEETING_AUDIO_ROOT
from .phase2_file import DEFAULT_PHASE2_FILE_WORK_ROOT
from .phase2_control import DEFAULT_PHASE2_CONTROL_SOCKET_PATH


DEFAULT_MODEL = Path(__file__).resolve().parents[2] / "pretrained" / "moss-transcribe-diarize"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MOSS Phase-2 Account web app over HTTPS.")
    parser.add_argument(
        "--database",
        default=str(DEFAULT_PHASE2_DATABASE_PATH),
        help="The Phase-2 SQLite database path (defaults to the product database).",
    )
    parser.add_argument(
        "--control-socket",
        default=str(DEFAULT_PHASE2_CONTROL_SOCKET_PATH),
        help="Mode-0600 host-local Account control socket.",
    )
    parser.add_argument("--tls-certfile", required=True)
    parser.add_argument("--tls-keyfile", required=True)
    parser.add_argument("--backend", choices=["hf", "vllm"], default="hf")
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--vllm-base-url")
    parser.add_argument("--vllm-model")
    parser.add_argument("--vllm-api-key", default="EMPTY")
    parser.add_argument("--vllm-timeout", type=float, default=600.0)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dtype", default="bf16")
    parser.add_argument(
        "--file-work-root",
        default=str(DEFAULT_PHASE2_FILE_WORK_ROOT),
        help="Dedicated transient directory named file-work.",
    )
    parser.add_argument(
        "--meeting-audio-root",
        default=str(DEFAULT_PHASE2_MEETING_AUDIO_ROOT),
        help="Owner-partitioned durable Meeting MP3 root.",
    )
    parser.add_argument("--prompt")
    parser.add_argument("--max-len", type=int, default=131072)
    parser.add_argument("--max-new-tokens", type=int, default=2048)
    parser.add_argument("--decoding", choices=["greedy", "sample"], default="greedy")
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument(
        "--live-provider-manifest",
        required=True,
        help="Offline production Live provider manifest.",
    )
    parser.add_argument(
        "--live-helper-lease-seconds",
        required=True,
        type=float,
        help="Positive capture heartbeat lease; expiry interrupts the Live Meeting.",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7861)
    return parser.parse_args(argv)


def _build_file_runner(args: argparse.Namespace):
    # Keep model imports out of argument/help and admin paths. The runner crosses into Phase 2
    # only as the owner-bound File-Meeting inference seam.
    from .runner_composition import build_file_runner

    return build_file_runner(
        model_path=Path(args.model).expanduser(),
        device=args.device,
        dtype=args.dtype,
        backend=args.backend,
        vllm_base_url=args.vllm_base_url,
        vllm_model=args.vllm_model,
        vllm_api_key=args.vllm_api_key,
        vllm_timeout=args.vllm_timeout,
    )


def _build_live_runtime_factory(args: argparse.Namespace, file_runner: object):
    if args.live_helper_lease_seconds <= 0:
        raise SystemExit("--live-helper-lease-seconds must be positive.")
    from .live_provider_bundle import LiveProviderBundleConfig, build_live_runtime_factory
    from .runner_composition import LazyLiveRunner, build_terminal_finalizer

    config = LiveProviderBundleConfig.from_manifest(args.live_provider_manifest)
    live_runner = LazyLiveRunner(
        model_path=args.model,
        device=args.device,
        dtype=args.dtype,
        backend=args.backend,
        vllm_base_url=args.vllm_base_url,
        vllm_model=args.vllm_model,
        vllm_api_key=args.vllm_api_key,
        vllm_timeout=args.vllm_timeout,
    )
    return build_live_runtime_factory(
        config,
        live_runner,
        terminal_finalizer=build_terminal_finalizer(
            runner=file_runner,
            prompt=args.prompt,
            max_length=args.max_len,
            max_new_tokens=args.max_new_tokens,
            decoding=args.decoding,
            temperature=args.temperature,
            max_length_cap=args.max_len if args.backend == "vllm" else None,
        ),
    )


def main(argv: Sequence[str] | None = None) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install uvicorn to run mtd-phase2-web.") from exc

    args = parse_args(argv)
    from .phase2_operator import configure_operator_journal

    configure_operator_journal()
    file_runner = _build_file_runner(args)
    live_runtime_factory = _build_live_runtime_factory(args, file_runner)
    app = create_phase2_app(
        database_path=Path(args.database).expanduser(),
        file_runner=file_runner,
        file_work_root=Path(args.file_work_root).expanduser(),
        meeting_audio_root=Path(args.meeting_audio_root).expanduser(),
        file_inference_options={
            "prompt": args.prompt,
            "max_length": args.max_len,
            "max_new_tokens": args.max_new_tokens,
            "decoding": args.decoding,
            "temperature": args.temperature,
        },
        live_runtime_factory=live_runtime_factory,
        live_helper_lease_seconds=args.live_helper_lease_seconds,
        control_socket_path=Path(args.control_socket).expanduser(),
    )
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        ssl_certfile=str(Path(args.tls_certfile).expanduser()),
        ssl_keyfile=str(Path(args.tls_keyfile).expanduser()),
        proxy_headers=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
