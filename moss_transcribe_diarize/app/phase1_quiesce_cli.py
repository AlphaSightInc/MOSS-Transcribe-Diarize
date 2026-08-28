from __future__ import annotations

import argparse
import json
from pathlib import Path

from .phase1_creation_quiesce import (
    Phase1CreationGate,
    default_phase1_creation_marker,
    disable_phase1_creation_quiesce,
    enable_phase1_creation_quiesce,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enable, disable, or inspect Phase-1 creation quiescence."
    )
    parser.add_argument("operation", choices=("enable", "disable", "status"))
    parser.add_argument(
        "--marker-path",
        default=str(default_phase1_creation_marker()),
        help="Shared ext4 marker path used by both Phase-1 web processes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    marker = Path(args.marker_path).expanduser()
    if args.operation == "enable":
        enable_phase1_creation_quiesce(marker)
    elif args.operation == "disable":
        disable_phase1_creation_quiesce(marker)
    snapshot = Phase1CreationGate(marker).snapshot()
    print(
        json.dumps(
            {
                "schema": "moss.phase1-creation-quiesce.v1",
                "state": snapshot.state,
                "marker_path": str(marker),
            },
            sort_keys=True,
        )
    )
