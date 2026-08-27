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


def main(argv: Sequence[str] | None = None) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install uvicorn to run mtd-phase2-web.") from exc

    args = parse_args(argv)
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
