"""Host-local exact-email admission commands for the Phase-2 persistence seam."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Sequence

from .phase2 import DEFAULT_PHASE2_DATABASE_PATH, Phase2Store, normalize_email


async def execute(database: str | Path, command: str, email: str | None = None) -> object:
    store = await Phase2Store.open(database)
    try:
        if command == "allow":
            if email is None:
                raise ValueError("EMAIL is required.")
            normalized = normalize_email(email)
            await store.allow_email(normalized)
            return {"email": normalized, "enabled": True}
        if command == "revoke":
            if email is None:
                raise ValueError("EMAIL is required.")
            return {"email": normalize_email(email), "revoked": await store.revoke_email(email)}
        if command == "list":
            return await store.list_allowlist()
        raise ValueError(f"Unknown accounts command: {command}")
    finally:
        await store.close()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Host-local MOSS Phase-2 administration.")
    parser.add_argument(
        "--database",
        default=str(DEFAULT_PHASE2_DATABASE_PATH),
        help="The Phase-2 SQLite database path (defaults to the product database).",
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
    result = asyncio.run(execute(args.database, args.command, getattr(args, "email", None)))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
