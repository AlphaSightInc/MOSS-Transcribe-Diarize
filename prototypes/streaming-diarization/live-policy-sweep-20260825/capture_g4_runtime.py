#!/usr/bin/env python3
"""Capture exact G4 service, source, descriptor, model, queue, and patch provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REPO = Path(__file__).resolve().parents[3]
PRODUCTION_FILES = (
    "moss_transcribe_diarize/app/live_transcript_convergence.py",
    "moss_transcribe_diarize/app/live_coordinator.py",
    "moss_transcribe_diarize/app/live_service_runtime.py",
    "moss_transcribe_diarize/app/live_session.py",
)


def command(*parts: str) -> str:
    return subprocess.check_output(parts, cwd=REPO, text=True).strip()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--patch-output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite {output}")

    patch = subprocess.check_output(
        ["git", "diff", "--binary", "--", *PRODUCTION_FILES], cwd=REPO
    )
    if args.patch_output is not None:
        patch_output = args.patch_output.resolve()
        if patch_output.exists():
            if patch_output.read_bytes() != patch:
                raise RuntimeError(f"existing production patch changed: {patch_output}")
        else:
            patch_output.parent.mkdir(parents=True, exist_ok=True)
            patch_output.write_bytes(patch)

    runtime_response = requests.get("https://127.0.0.1:7861/api/runtime", verify=False, timeout=20)
    runtime_response.raise_for_status()
    models_response = requests.get("http://127.0.0.1:18000/v1/models", timeout=20)
    models_response.raise_for_status()
    metrics_response = requests.get("http://127.0.0.1:18000/metrics", timeout=20)
    metrics_response.raise_for_status()
    queue_lines = [
        line
        for line in metrics_response.text.splitlines()
        if line.startswith("vllm:num_requests_running{")
        or line.startswith("vllm:num_requests_waiting{")
    ]

    process = command("ps", "-p", str(args.pid), "-o", "pid=,ppid=,lstart=,command=")
    cwd_lines = command("lsof", "-a", "-p", str(args.pid), "-d", "cwd", "-Fn").splitlines()
    cwd = next(line[1:] for line in cwd_lines if line.startswith("n"))
    listener = command(
        "lsof", "-nP", "-a", "-p", str(args.pid), "-iTCP", "-sTCP:LISTEN"
    )
    report: dict[str, Any] = {
        "schema": "moss-g4-runtime-provenance.v1",
        "captured_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git": {
            "branch": command("git", "branch", "--show-current"),
            "head": command("git", "rev-parse", "HEAD"),
            "status_short": command("git", "status", "--short"),
            "production_patch_sha256": sha256_bytes(patch),
            "production_file_sha256": {
                relative: sha256_file(REPO / relative) for relative in PRODUCTION_FILES
            },
        },
        "service": {
            "pid": args.pid,
            "process": process,
            "cwd": cwd,
            "listener": listener,
        },
        "runtime": runtime_response.json(),
        "remote_model": models_response.json(),
        "vllm_queue_metrics": queue_lines,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
