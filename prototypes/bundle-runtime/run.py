"""PROTOTYPE: prove the candidate process can start without a decoder request.

Question: does the disposable SQLite 3.53.4 interpreter start the unmodified
candidate web process, serve its root/descriptor, and own its operator socket?
Hypothesis: yes; a dead loopback decoder is never contacted before audio or file
work is admitted.  Falsifier: startup, root/descriptor, or socket status fails.

Run with the disposable interpreter from the checkout root::

  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
    /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python \
    prototypes/bundle-runtime/run.py --out evidence/round4/bundle-runtime/stack-probe.json

This harness deliberately uses no frame, file, URL, or meeting endpoint.  Its
decoder URL is an unbound loopback port, never a provider.  Temporary server
state and the short-lived certificate are deleted at exit.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
RUNTIME_PYTHON = Path("/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python")
DEAD_LOOPBACK_DECODER = "http://127.0.0.1:9/v1"


def _free(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0


def _json(url: str) -> tuple[int, dict[str, Any]]:
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(url, context=context, timeout=2) as response:
        payload = json.loads(response.read().decode("utf-8"))
        return response.status, payload


def _wait(base: str, process: subprocess.Popen[bytes]) -> tuple[int, dict[str, Any]]:
    from tests.e2e.verify_demo_lanes import Client

    client = Client(base, ssl._create_unverified_context())
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("candidate process exited before descriptor readiness")
        try:
            client.call("POST", "/api/workspace/bootstrap")
            return 200, client.call("GET", "/api/live/descriptor")
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("candidate process did not reach descriptor readiness")


def _status(url: str) -> int:
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(url, context=context, timeout=2) as response:
        return response.status


def _certificate(directory: Path) -> tuple[Path, Path]:
    cert, key = directory / "cert.pem", directory / "key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-days", "1", "-subj", "/CN=127.0.0.1",
            "-addext", "subjectAltName=IP:127.0.0.1", "-keyout", str(key),
            "-out", str(cert),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return cert, key


def _operator_status(python: Path, socket_path: Path, env: dict[str, str]) -> dict[str, Any]:
    result = subprocess.run(
        [
            str(python), "-m", "moss_transcribe_diarize.app.phase2_admin",
            "--socket", str(socket_path), "status", "--json",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--port", type=int, default=17845)
    parser.add_argument("--python", type=Path, default=RUNTIME_PYTHON)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=Path.home()
        / ".cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/e8681d68e7042738ffca8ac8212bc8fcb1131ab8",
    )
    args = parser.parse_args(argv)
    if args.out.exists():
        raise SystemExit(f"REFUSE: output already exists: {args.out}")
    if not args.python.is_file() or not args.manifest.is_file() or not args.model.is_dir():
        raise SystemExit("REFUSE: disposable Python, manifest, or model metadata is unavailable")
    if not _free(args.port):
        raise SystemExit(f"REFUSE: port {args.port} is occupied")

    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT))
    for key in ("MOSS_LLM_UPSTREAMS", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        env.pop(key, None)
    result: dict[str, Any] = {
        "schema": "moss-r4-bundle-runtime-stack-probe.v1",
        "question": "can the disposable runtime start the candidate before any decoder work?",
        "python": str(args.python),
        "decoder_base_url": DEAD_LOOPBACK_DECODER,
        "decoder_requests": 0,
        "frames_sent": 0,
        "file_or_url_jobs_started": 0,
    }
    with tempfile.TemporaryDirectory(prefix="moss-r4-bundle-runtime-") as temporary:
        state = Path(temporary)
        cert, key = _certificate(state)
        control = state / "operator.sock"
        command = [
            str(args.python), "-m", "moss_transcribe_diarize.app.phase2_web_cli",
            "--database", str(state / "phase2.sqlite"),
            "--control-socket", str(control),
            "--tls-certfile", str(cert), "--tls-keyfile", str(key),
            "--backend", "vllm", "--model", str(args.model),
            "--vllm-base-url", DEAD_LOOPBACK_DECODER,
            "--vllm-model", "OpenMOSS-Team/MOSS-Transcribe-Diarize",
            "--vllm-timeout", "1", "--file-work-root", str(state / "file-work"),
            "--meeting-audio-root", str(state / "meeting-audio"),
            "--live-provider-manifest", str(args.manifest),
            "--live-helper-lease-seconds", "30", "--host", "127.0.0.1",
            "--port", str(args.port), "--max-len", "16384", "--max-new-tokens", "12000",
        ]
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            base = f"https://127.0.0.1:{args.port}"
            descriptor_status, descriptor = _wait(base, process)
            root_status = _status(base + "/")
            result.update(
                root_status=root_status,
                descriptor_status=descriptor_status,
                descriptor=descriptor.get("descriptor"),
                control_socket={
                    "exists": control.exists(),
                    "mode": oct(stat.S_IMODE(control.stat().st_mode)) if control.exists() else None,
                    "status": _operator_status(args.python, control, env),
                },
            )
            result["verdict"] = "RUNNABLE"
        finally:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
