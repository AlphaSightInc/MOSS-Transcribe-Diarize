"""Attended Phase-2 cutover and incomplete-attempt whole restore."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from ..phase2_cutover import CutoverRefused, CutoverRun, result_payload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="operation", required=True)
    run = subcommands.add_parser("run", help="start one new cutover attempt")
    run.add_argument("--profile", required=True, type=Path)
    run.add_argument("--attempt", required=True, type=Path)
    run.add_argument("--terminal", required=True, choices=("restored", "preadmission"))
    restore = subcommands.add_parser(
        "restore", help="restore one nonterminal interrupted attempt"
    )
    restore.add_argument("--attempt", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.operation == "run":
            result = CutoverRun.prepare(
                profile_path=args.profile,
                attempt=args.attempt,
                terminal=args.terminal,
            ).run()
        else:
            result = CutoverRun.open_incomplete(attempt=args.attempt).restore()
    except CutoverRefused as exc:
        print(
            json.dumps(
                {
                    "schema": "moss-phase2-cutover-result.v1",
                    "terminal": "REFUSED",
                    "g7": "UNCLAIMED",
                    "admitted": False,
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result_payload(result), sort_keys=True))
    if result.terminal == "preadmission":
        return 0
    if result.terminal == "restored":
        return 0 if args.operation == "restore" or result.error is None else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
