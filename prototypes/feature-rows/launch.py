#!/usr/bin/env python3
"""Launch the isolated F3s stack, run its summary row, and tear it down."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ROW_RUNNER = Path(__file__).with_name("run.py")
sys.path.insert(0, str(ROOT))

from tools.qualify.run import Bundle, Decoder, local_stack_command, ready_descriptor

DEFAULT_PORT = 17836
DEFAULT_PROXY_PORT = 19136
ROW_OWNER = "summaries"


def request_plan(frozen_sha: str) -> dict[str, Any]:
    plan = runpy.run_path(str(ROW_RUNNER))["summary_plan"]()
    return {**plan, "frozen_sha": frozen_sha}


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _product_diff(frozen_sha: str) -> list[str]:
    output = subprocess.check_output(
        ["git", "diff", "--name-only", frozen_sha, "--", "moss_transcribe_diarize", "frontend"],
        cwd=ROOT,
        text=True,
    )
    return output.splitlines()


def _certificate(state: Path) -> tuple[Path, Path]:
    cert, key = state / "cert.pem", state / "key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-days", "1", "-subj", "/CN=127.0.0.1",
            "-addext", "subjectAltName=IP:127.0.0.1",
            "-keyout", str(key), "-out", str(cert),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return cert, key


def _start_stack(
    args: argparse.Namespace,
    state: Path,
    cert: Path,
    key: Path,
    log: Any,
) -> subprocess.Popen[bytes]:
    command = local_stack_command(
        state=state / "stack",
        cert=cert,
        key=key,
        port=args.port,
        manifest=args.manifest,
        vllm_base_url=f"http://127.0.0.1:{args.proxy_port}/v1",
        max_requests=args.budget,
        model=args.model,
    )
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT))
    environment.pop("OPENROUTER_API_KEY", None)
    return subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _wait_ready(base: str, process: subprocess.Popen[bytes]) -> float:
    started = time.monotonic()
    last_error: Exception | None = None
    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError("stack exited before readiness")
        try:
            descriptor = ready_descriptor(base)
            if descriptor.get("source_revision"):
                return time.monotonic() - started
        except Exception as exc:
            last_error = exc
        time.sleep(1)
    raise RuntimeError("stack did not become ready") from last_error


def _stop_stack(process: subprocess.Popen[bytes] | None) -> None:
    if process is not None:
        Bundle.stop(process)


def _validate_execution(args: argparse.Namespace, plan: dict[str, Any]) -> list[str]:
    missing = []
    if not args.allow_decoder:
        missing.append("--allow-decoder")
    if not args.allow_provider:
        missing.append("--allow-provider")
    if not os.environ.get("OPENROUTER_API_KEY"):
        missing.append("exported OPENROUTER_API_KEY")
    if missing:
        raise SystemExit("REFUSE: missing explicit row authority: " + ", ".join(missing))
    if args.decoder_upstream_port is None:
        raise SystemExit("REFUSE: --decoder-upstream-port is required; no tunnel is opened")
    if args.budget != int(plan["planned_decoder"]):
        raise SystemExit("REFUSE: --budget must equal the exact F3s decoder plan")
    if args.out.exists():
        raise SystemExit(f"REFUSE: output exists: {args.out}")
    if not args.model.is_dir() or not args.manifest.is_file():
        raise SystemExit("REFUSE: model or manifest is unavailable")
    product_changes = _product_diff(args.frozen_sha)
    if product_changes:
        raise SystemExit("REFUSE: product differs from --frozen-sha")
    return product_changes


def execute(args: argparse.Namespace, plan: dict[str, Any]) -> int:
    product_changes = _validate_execution(args, plan)
    args.out.mkdir(parents=True)
    proxy_log = args.out / "decoder-requests.jsonl"
    receipt_path = args.out / "receipt.json"
    state = Path(tempfile.mkdtemp(prefix="moss-r4-f3s-", dir="/private/tmp"))
    proxy: Any | None = None
    stack: subprocess.Popen[bytes] | None = None
    stack_log = (args.out / "stack.log").open("wb")
    receipt: dict[str, Any] = {
        **plan,
        "mode": "EXECUTION_STARTED",
        "status": "INCOMPLETE",
        "product_changes_since_frozen_sha": product_changes,
        "actual_calls": {"decoder": 0, "provider": 0},
    }
    teardown_complete = False
    try:
        cert, key = _certificate(state)
        proxy = Decoder(args.proxy_port, args.decoder_upstream_port, args.budget, proxy_log)
        proxy.set_row_owner(ROW_OWNER)
        proxy.start()
        stack = _start_stack(args, state, cert, key, stack_log)
        base = f"https://127.0.0.1:{args.port}"
        ready_seconds = _wait_ready(base, stack)
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT))
        completed = subprocess.run(
            [
                sys.executable,
                str(ROW_RUNNER),
                "--base", base,
                "--decoder-proxy-log", str(proxy_log),
                "--allow-decoder",
                "--allow-provider",
                "--out", str(receipt_path),
            ],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=1800,
        )
        if not receipt_path.is_file():
            raise RuntimeError("feature row did not write its receipt")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt.update(
            frozen_sha=args.frozen_sha,
            product_changes_since_frozen_sha=product_changes,
            launcher={
                "stack_ready": True,
                "stack_ready_seconds": round(ready_seconds, 3),
                "row_exit": completed.returncode,
                "row_owner": ROW_OWNER,
                "budget": args.budget,
                "max_in_flight": 2,
                "tunnel_opened": False,
            },
        )
        if (receipt.get("status") == "PASS") != (completed.returncode == 0):
            receipt["status"] = "INCOMPLETE"
            receipt["reason"] = "row exit and receipt status disagree"
    except Exception as exc:
        receipt.update(
            status="INCOMPLETE",
            reason=f"{type(exc).__name__}; inspect stack.log and decoder receipt",
        )
    finally:
        try:
            _stop_stack(stack)
            if proxy is not None:
                proxy.clear_row_owner(ROW_OWNER)
                proxy.close()
            teardown_complete = True
        except Exception:
            receipt["status"] = "INCOMPLETE"
            receipt["reason"] = "owned stack or proxy teardown failed"
        stack_log.close()
        import shutil

        shutil.rmtree(state)
        receipt.setdefault("launcher", {})["teardown_complete"] = teardown_complete
        _write(receipt_path, receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt.get("status") == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan-only", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--frozen-sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--decoder-upstream-port", type=int)
    parser.add_argument("--budget", type=int, default=0)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--proxy-port", type=int, default=DEFAULT_PROXY_PORT)
    parser.add_argument("--allow-decoder", action="store_true")
    parser.add_argument("--allow-provider", action="store_true")
    parser.add_argument("--model", type=Path, default=Path.home() / ".cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/e8681d68e7042738ffca8ac8212bc8fcb1131ab8")
    parser.add_argument("--manifest", type=Path, default=Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json")
    args = parser.parse_args(argv)
    plan = request_plan(args.frozen_sha)
    if args.plan_only:
        _write(args.out, plan)
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    return execute(args, plan)


if __name__ == "__main__":
    raise SystemExit(main())
