#!/usr/bin/env python3
"""Run one immutable Phase-2 qualification attempt."""

from __future__ import annotations

import argparse
from pathlib import Path

from moss_transcribe_diarize.phase2_acceptance import run_acceptance


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wave", required=True, type=int, choices=(1, 2, 3))
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[2]
    return run_acceptance(wave=args.wave, output=args.output, repo=repo)


if __name__ == "__main__":
    raise SystemExit(main())
