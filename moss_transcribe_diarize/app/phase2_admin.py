"""Host-local exact-email admission commands for the Phase-2 persistence seam."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Sequence

from .phase2_control import DEFAULT_PHASE2_CONTROL_SOCKET_PATH, request_control


async def execute(socket: str | Path, command: str, email: str | None = None) -> object:
    if command not in {"allow", "revoke", "list"}:
        raise ValueError(f"Unknown accounts command: {command}")
    if command != "list" and email is None:
        raise ValueError("EMAIL is required.")
    return await request_control(socket, f"accounts.{command}", email)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Host-local MOSS Phase-2 administration.")
    parser.add_argument(
        "--socket",
        default=str(DEFAULT_PHASE2_CONTROL_SOCKET_PATH),
        help="The running product's host-local control socket.",
    )
    commands = parser.add_subparsers(dest="area", required=True)
    accounts = commands.add_parser("accounts")
    account_commands = accounts.add_subparsers(dest="command", required=True)
    allow = account_commands.add_parser("allow")
    allow.add_argument("email", metavar="EMAIL")
    revoke = account_commands.add_parser("revoke")
    revoke.add_argument("email", metavar="EMAIL")
    account_commands.add_parser("list")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if args.area != "accounts":  # argparse keeps this defensive branch unreachable.
        raise SystemExit(2)
    result = asyncio.run(execute(args.socket, args.command, getattr(args, "email", None)))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
