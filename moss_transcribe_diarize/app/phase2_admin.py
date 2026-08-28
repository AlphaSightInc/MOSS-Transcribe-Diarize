"""Host-local exact-email admission commands for the Phase-2 persistence seam."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Sequence

from .phase2_control import DEFAULT_PHASE2_CONTROL_SOCKET_PATH, request_control
from .phase2_operator import render_operator_status


async def execute(socket: str | Path, command: str, email: str | None = None) -> object:
    if command not in {"allow", "revoke", "list"}:
        raise ValueError(f"Unknown accounts command: {command}")
    if command != "list" and email is None:
        raise ValueError("EMAIL is required.")
    return await request_control(socket, f"accounts.{command}", email)


async def execute_status(socket: str | Path) -> object:
    return await request_control(socket, "status")


async def execute_interrupt(socket: str | Path, meeting_id: str) -> object:
    if not meeting_id:
        raise ValueError("MEETING_ID is required.")
    return await request_control(
        socket,
        "meetings.interrupt",
        meeting_id=meeting_id,
    )


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
    meetings = commands.add_parser("meetings")
    meeting_commands = meetings.add_subparsers(dest="command", required=True)
    interrupt = meeting_commands.add_parser("interrupt")
    interrupt.add_argument("meeting_id", metavar="MEETING_ID")
    status = commands.add_parser("status")
    status.add_argument(
        "--json",
        action="store_true",
        help="Print the exact machine-readable allowlisted snapshot.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if args.area == "accounts":
        result = asyncio.run(execute(args.socket, args.command, getattr(args, "email", None)))
        print(json.dumps(result, sort_keys=True))
        return
    if args.area == "status":
        result = asyncio.run(execute_status(args.socket))
        if not isinstance(result, dict):
            raise RuntimeError("Product status response is invalid.")
        print(json.dumps(result, sort_keys=True) if args.json else render_operator_status(result))
        return
    if args.area == "meetings" and args.command == "interrupt":
        result = asyncio.run(execute_interrupt(args.socket, args.meeting_id))
        print(json.dumps(result, sort_keys=True))
        return
    raise SystemExit(2)  # argparse keeps this defensive branch unreachable.


if __name__ == "__main__":
    main()
