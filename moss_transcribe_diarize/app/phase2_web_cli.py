"""The packaged Account HTTPS startup path.

This command is the complete product process surface: it builds only the Account app,
binds its canonical SQLite database, and hands the configured certificate to Uvicorn.
"""

from __future__ import annotations

import argparse
import asyncio
import os
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
    parser.add_argument("--live-engine", choices=["moss", "gemini"], default="moss",
                        help="Live transcription engine; Gemini requires the measured provider adapter.")
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--vllm-base-url")
    parser.add_argument("--vllm-model")
    parser.add_argument("--vllm-api-key", default="EMPTY")
    parser.add_argument("--vllm-timeout", type=float, default=600.0)
    parser.add_argument("--file-identity", choices=["album", "legacy"], default="album",
                        help="File cross-window identity; legacy is the one-release fallback.")
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
    parser.add_argument("--live-draft-lane-seconds", type=float, default=None,
                        help="Optional reader-only draft cadence; omitted means off.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument("--llm-upstreams", default=os.environ.get("MOSS_LLM_UPSTREAMS", ""),
                        help="JSON list of key-less tailnet LLM upstreams; defaults to MOSS_LLM_UPSTREAMS.")
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
        file_identity=args.file_identity,
        identity_manifest=args.live_provider_manifest,
        inference_scheduler=getattr(args, "_inference_scheduler", None),
    )


def _build_live_runtime_factory(args: argparse.Namespace, file_runner: object):
    if args.live_helper_lease_seconds <= 0:
        raise SystemExit("--live-helper-lease-seconds must be positive.")
    if args.live_engine == "gemini":
        # Phase 1 ships the runtime contract and deterministic fake only. Do not start
        # a meeting under a fake provider while the measured engine is still undecided.
        raise SystemExit("Gemini Live engine is not installed; await the bake-off adapter.")
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
        inference_scheduler=getattr(args, "_inference_scheduler", None),
    )
    return build_live_runtime_factory(
        config,
        live_runner,
        tape_storage_root=Path(args.file_work_root).expanduser() / "live-tapes",
        draft_lane_seconds=getattr(args, "live_draft_lane_seconds", None),
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
    if args.live_engine == "gemini":
        # A phase-1 binary must refuse before constructing the MOSS file runner, which
        # may load the local model/GPU. Real Gemini selection is wired after the bake-off.
        raise SystemExit("Gemini Live engine is not installed; await the bake-off adapter.")
    from .inference_scheduler import InferenceDispatchScheduler

    args._inference_scheduler = InferenceDispatchScheduler(
        max_calls=2,
        max_background_calls=1,
    )
    from .phase2_llm import parse_upstreams
    parse_upstreams(args.llm_upstreams)
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
        llm_upstreams=args.llm_upstreams,
        open_workspace=os.environ.get("MOSS_OPEN_WORKSPACE") == "1",
        inference_scheduler=args._inference_scheduler,
    )
    from .tls_reload import serve_with_certificate_reload

    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        ssl_certfile=str(Path(args.tls_certfile).expanduser()),
        ssl_keyfile=str(Path(args.tls_keyfile).expanduser()),
        proxy_headers=False,
        access_log=False,
    )
    asyncio.run(serve_with_certificate_reload(config), loop_factory=config.get_loop_factory())


if __name__ == "__main__":
    main()
