"""THROWAWAY: start the packaged HTTPS app with the disposable SQLite runtime.

This control intentionally submits no audio frames.  It can falsify a production CLI,
TLS, SQLite, or live-provider-manifest startup gap without loading the local model or
creating a decoder request.  `short_stack_run.py` supplies the separate headed
instrument/rendering control using a synthetic local transcript.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import time
from typing import Sequence
from urllib.request import Request, urlopen


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _certificate(root: Path) -> tuple[Path, Path]:
    certificate = root / "certificate.pem"
    key = root / "private-key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
            "-keyout", str(key), "-out", str(certificate),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return certificate, key


def _request(
    url: str, *, method: str, cookies: dict[str, str]
) -> tuple[int, str]:
    context = ssl._create_unverified_context()
    headers = {"Content-Type": "application/json"}
    if cookies:
        headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in cookies.items())
    request = Request(url, data=b"" if method == "POST" else None, method=method, headers=headers)
    with urlopen(request, context=context, timeout=1) as response:
        for header in response.headers.get_all("Set-Cookie") or []:
            name, _, value = header.partition("=")
            cookies[name] = value.split(";", 1)[0]
        return int(response.status), response.read().decode("utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output must not already exist")
    port = _free_port()
    failure = None
    with tempfile.TemporaryDirectory(prefix="moss-headed-cli-") as temporary:
        root = Path(temporary)
        certificate, key = _certificate(root)
        log_path = root / "server.log"
        command = [
            str(args.runtime), "-m", "moss_transcribe_diarize.app.phase2_web_cli",
            "--database", str(root / "phase2.sqlite3"),
            "--control-socket", str(root / "control.sock"),
            "--tls-certfile", str(certificate), "--tls-keyfile", str(key),
            "--backend", "hf", "--model", str(args.model), "--device", "cpu", "--dtype", "bf16",
            "--file-work-root", str(root / "file-work"),
            "--meeting-audio-root", str(root / "meeting-audio"),
            "--live-provider-manifest", str(args.manifest), "--live-helper-lease-seconds", "30",
            "--host", "127.0.0.1", "--port", str(port), "--llm-upstreams", "[]",
        ]
        with log_path.open("w") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            index = descriptor = ""
            bootstrap_status = None
            cookies: dict[str, str] = {}
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(f"production CLI exited {process.returncode}")
                    try:
                        bootstrap_status, _ = _request(
                            f"https://127.0.0.1:{port}/api/workspace/bootstrap",
                            method="POST", cookies=cookies,
                        )
                        index_status, index = _request(
                            f"https://127.0.0.1:{port}/", method="GET", cookies=cookies
                        )
                        descriptor_status, descriptor = _request(
                            f"https://127.0.0.1:{port}/api/live/descriptor",
                            method="GET", cookies=cookies,
                        )
                        failure = None
                        break
                    except Exception as exc:  # server is still booting
                        failure = str(exc)
                        time.sleep(0.2)
                else:
                    raise RuntimeError(f"production CLI did not serve before deadline: {failure}")
            except Exception as exc:
                failure = str(exc)
                index_status = descriptor_status = None
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        descriptor_body = json.loads(descriptor).get("descriptor", {}) if descriptor else {}
        receipt = {
            "schema": "moss-headed-session-production-cli-startup.v1",
            "runtime_python": str(args.runtime),
            "sqlite_runtime": sqlite3.sqlite_version,
            "binding": f"https://127.0.0.1:{port}",
            "index_status": index_status,
            "bootstrap_status": bootstrap_status,
            "descriptor_status": descriptor_status,
            "frontend_markers": {
                "title_moss": "<title>MOSS</title>" in index,
                "signed_in_surface": 'data-auth-state="signed-in"' in index,
            },
            "provider": {
                key: descriptor_body.get(key)
                for key in ("source_revision", "provider_name", "provider_revision", "sample_rate")
            },
            "audio_frames_submitted": 0,
            "remote_decoder_requests": 0,
            "microphone_opened": False,
            "audio_playback": False,
            "gpu_used": False,
            "failure": failure,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True), flush=True)
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
