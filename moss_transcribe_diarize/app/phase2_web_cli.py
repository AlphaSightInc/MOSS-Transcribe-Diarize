"""The packaged Phase-2 HTTPS startup path.

Phase 1 keeps its own entry point until the cutover ticket.  This command is the complete
Phase-2 process surface I12 installs: it builds only the Account app, binds its canonical SQLite
database by default, and hands the configured certificate directly to Uvicorn.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .phase2 import AuthlibGoogleOidc, DEFAULT_PHASE2_DATABASE_PATH, create_phase2_app
from .phase2_audio import DEFAULT_PHASE2_MEETING_AUDIO_ROOT
from .phase2_file import DEFAULT_PHASE2_FILE_WORK_ROOT


DEFAULT_MODEL = Path(__file__).resolve().parents[2] / "pretrained" / "moss-transcribe-diarize"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MOSS Phase-2 Account web app over HTTPS.")
    parser.add_argument(
        "--database",
        default=str(DEFAULT_PHASE2_DATABASE_PATH),
        help="The Phase-2 SQLite database path (defaults to the product database).",
    )
    parser.add_argument("--google-client-id", required=True)
    parser.add_argument("--google-client-secret-file", required=True)
    parser.add_argument("--oauth-cookie-secret-file", required=True)
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
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7861)
    return parser.parse_args(argv)


def _secret_from_file(path_text: str, *, flag: str) -> str:
    path = Path(path_text).expanduser()
    try:
        secret = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SystemExit(f"{flag} could not be read: {path}: {exc.strerror}") from exc
    if not secret:
        raise SystemExit(f"{flag} must contain a non-empty value.")
    return secret


def _build_file_runner(args: argparse.Namespace):
    # Keep model imports out of argument/help and admin paths. The runner crosses into Phase 2
    # only as the owner-bound File-Meeting inference seam.
    from .server import build_file_mode_runner

    return build_file_mode_runner(
        model_path=Path(args.model).expanduser(),
        device=args.device,
        dtype=args.dtype,
        backend=args.backend,
        vllm_base_url=args.vllm_base_url,
        vllm_model=args.vllm_model,
        vllm_api_key=args.vllm_api_key,
        vllm_timeout=args.vllm_timeout,
        speaker_identity_tier_b=False,
        speaker_identity_state=None,
        speaker_identity_fixture=None,
    )


def main(argv: Sequence[str] | None = None) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install uvicorn to run mtd-phase2-web.") from exc

    args = parse_args(argv)
    file_runner = _build_file_runner(args)
    oidc = AuthlibGoogleOidc.configured(
        client_id=args.google_client_id,
        client_secret=_secret_from_file(
            args.google_client_secret_file, flag="--google-client-secret-file"
        ),
    )
    app = create_phase2_app(
        database_path=Path(args.database).expanduser(),
        oidc=oidc,
        oauth_cookie_secret=_secret_from_file(
            args.oauth_cookie_secret_file, flag="--oauth-cookie-secret-file"
        ),
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
