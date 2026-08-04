#!/usr/bin/env python3
"""Capture raw diagnosis-only legacy-ingest test transcripts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="append", required=True)
    parser.add_argument("--transcript-output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()

    command = [sys.executable, "-m", "unittest", "-v", *args.test]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        cwd=Path(__file__).resolve().parent,
        text=True,
    )
    transcript = (
        "COMMAND " + " ".join(command) + "\n"
        + f"EXIT {completed.returncode}\n"
        + "STDOUT\n" + completed.stdout
        + "STDERR\n" + completed.stderr
    )
    args.transcript_output.parent.mkdir(parents=True, exist_ok=True)
    args.transcript_output.write_text(transcript, encoding="utf-8")
    result = {
        "command": command,
        "exit_code": completed.returncode,
        "overall": "PASS" if completed.returncode == 0 else "FAIL",
        "schema": "moss-l2-stage0-legacy-ingest-test-run.v1",
        "tests": args.test,
        "transcript_path": str(args.transcript_output),
        "transcript_sha256": sha256_file(args.transcript_output),
    }
    args.json_output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(transcript, end="")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
