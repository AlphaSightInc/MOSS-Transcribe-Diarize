#!/usr/bin/env python3
"""THROWAWAY: run D34 row 10 through Chromium, local stack, and loopback vLLM."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import runpy
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path("/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python")
MANIFEST = Path("/Users/gao/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json")
MODEL = Path("/Users/gao/.cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/e8681d68e7042738ffca8ac8212bc8fcb1131ab8")
STACK_PORT = 17842
STUB_PORT = 19443
PROXY_PORT = 19444


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def listener_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def stop(process: subprocess.Popen[bytes] | None) -> None:
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=15)


def wait_stub(process: subprocess.Popen[bytes]) -> None:
    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError("loopback_stub_start_failed")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{STUB_PORT}/v1/models", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(.1)
    raise RuntimeError("loopback_stub_not_ready")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.is_file() else {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loopback", action="store_true", required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/round5/i4/loopback")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out = args.out.resolve()
    if out.exists() or not MANIFEST.is_file() or not MODEL.is_dir():
        raise SystemExit("REFUSE: output exists or required manifest/model is unavailable")
    if not all(port_is_free(port) for port in (STACK_PORT, STUB_PORT, PROXY_PORT)):
        raise SystemExit("REFUSE: owned loopback port is occupied")
    out.mkdir(parents=True)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=".")
    for name in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "MOSS_LLM_UPSTREAMS"):
        environment.pop(name, None)

    stub = stack = proxy = None
    result: dict[str, Any] = {
        "schema_version": 1,
        "mode": "loopback_vllm_stub",
        "ports": {"stack": STACK_PORT, "stub": STUB_PORT, "proxy": PROXY_PORT},
        "decoder_requests_real": 0,
    }
    try:
        stub = subprocess.Popen(
            [str(PYTHON), str(Path(__file__).with_name("loopback_vllm_stub.py")), "--port", str(STUB_PORT), "--out", str(out / "stub")],
            cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
        wait_stub(stub)
        from tools.qualify.decoder import Decoder
        proxy = Decoder(PROXY_PORT, STUB_PORT, 800, out / "decoder-proxy.jsonl")
        proxy.start()
        launcher = runpy.run_path(str(ROOT / "prototypes/feature-rows/launch.py"))
        with tempfile.TemporaryDirectory(prefix="moss-row10-d34-", dir="/private/tmp") as temporary:
            temporary_path = Path(temporary)
            cert, key = launcher["_certificate"](temporary_path)
            with (temporary_path / "stack.log").open("wb") as stack_log:
                from tools.qualify.run import local_stack_command
                stack = subprocess.Popen(
                    local_stack_command(
                        state=temporary_path / "stack", cert=cert, key=key, port=STACK_PORT,
                        manifest=MANIFEST, vllm_base_url=f"http://127.0.0.1:{PROXY_PORT}/v1",
                        max_requests=800, model=MODEL,
                    ),
                    cwd=ROOT, env=environment, stdout=stack_log, stderr=subprocess.STDOUT, start_new_session=True,
                )
                result["stack_ready_seconds"] = round(float(launcher["_wait_ready"](f"https://127.0.0.1:{STACK_PORT}", stack)), 3)
                recipe = runpy.run_path(str(Path("/private/tmp/moss-round5-dryrun-p2/prototypes/round5-dryrun-p2/minimal_row10.py")))
                recipe["ROOT"] = ROOT
                recipe["CORPUS"] = ROOT / "evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s"
                verify = recipe["_verify_module"]()
                recipe["VERIFY"] = verify
                recipe["Harness"] = verify.Harness
                recipe["QuietHandler"] = verify.QuietHandler
                recipe["browser_executable"] = verify.browser_executable
                result["recipe"] = recipe["run_minimal"](
                    f"https://127.0.0.1:{STACK_PORT}", out / "workspace", 1,
                )
    except Exception as exc:
        result["exception"] = type(exc).__name__
    finally:
        stop(stack)
        if proxy is not None:
            proxy.close()
        stop(stub)

    workspace = read_json(out / "workspace/capture-1/workspace/results.json")
    row = workspace.get("rows", {}).get("10", {})
    attempts = row.get("attempts", []) if isinstance(row, dict) else []
    result["row10"] = {
        "status": row.get("status") if isinstance(row, dict) else None,
        "reason_code": row.get("reason_code") if isinstance(row, dict) else None,
        "attempt_count": len(attempts),
        "attempts": [
            {key: attempt.get(key) for key in ("attempt", "recognition_seconds", "timing_attribution", "meeting", "prior_durability")}
            for attempt in attempts if isinstance(attempt, dict)
        ],
        "timing_receipts": sum((out / "workspace/capture-1/workspace" / f"row-10-timing-attempt-{number}.json").is_file() for number in range(1, 6)),
    }
    result["workspace_exit_code"] = 0 if result["row10"]["status"] == "BEST_EFFORT_FAIL" else 1
    request_log = out / "stub/requests.jsonl"
    result["stub_requests"] = sum(1 for _ in request_log.open()) if request_log.is_file() else 0
    result["proxy"] = asdict(proxy.snapshot()) if proxy is not None else None
    result["listeners_after"] = {"stack": listener_open(STACK_PORT), "stub": listener_open(STUB_PORT), "proxy": listener_open(PROXY_PORT)}
    result["status"] = (
        "SUPPORTED" if result.get("workspace_exit_code") == 0 and result["row10"]["status"] == "BEST_EFFORT_FAIL"
        and result["row10"]["attempt_count"] == 5 and result["row10"]["timing_receipts"] == 5
        and not any(result["listeners_after"].values()) else "FALSIFIED"
    )
    (out / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "SUPPORTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
