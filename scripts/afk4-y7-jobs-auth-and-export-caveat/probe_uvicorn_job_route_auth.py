#!/usr/bin/env python3
"""Exercise protected job routes through a locally-run Uvicorn TLS service.

Question answered: does the deployed ASGI request path reject missing and wrong
shared bearers on every named job route, while a configured bearer can upload,
list, fetch, and delete a job?

The service uses the production app, job manager, and live auth registry.  Its
transcriber is deterministic so this wire-level auth probe needs neither a
model nor GPU.  It therefore proves request admission, not a real decode.

Run:
  env PYTHONPATH="$PWD" .venv/bin/python \
    scripts/afk4-y7-jobs-auth-and-export-caveat/probe_uvicorn_job_route_auth.py \
    --output evidence/phase1/y7-jobs-auth-and-export-caveat/iteration-6-uvicorn-job-route-auth.json
"""

from __future__ import annotations

import argparse
import http.client
import importlib.util
import json
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import uvicorn

from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.server import create_app


ROOT = Path(__file__).resolve().parents[2]
FINGERPRINT = "ab" * 32
TIMEOUT_SECONDS = 10.0
MISSING_JOB_ID = "not-present"


class _DeterministicRunner:
    """Completes the real JobManager lifecycle without loading a model."""

    model_path = "wire-auth-deterministic-runner"

    def runtime_info(self) -> dict[str, str]:
        return {"backend": "deterministic", "path": self.model_path}

    def transcribe(self, audio_path: Path, **kwargs: Any) -> TranscriptionResult:
        callback = kwargs.get("status_callback")
        if callback is not None:
            callback("transcribing", 0.5, 1)
        return TranscriptionResult(
            text="[0][S01]wire auth evidence[1]",
            prompt_len=1,
            generated_tokens=1,
            elapsed_sec=0.01,
            model=self.model_path,
            audio=str(audio_path),
            decoding="greedy",
            temperature=None,
        )


def _load_live_runtime_helpers() -> ModuleType:
    """Load the repository's existing deterministic live runtime factory."""
    source = ROOT / "tests" / "test_live_api.py"
    spec = importlib.util.spec_from_file_location("y7_wire_auth_live_runtime", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load live runtime helper from {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _generate_certificate(cert: Path, key: Path) -> None:
    completed = subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"openssl failed: {completed.stderr.strip()}")


def _start_server(app: Any, cert: Path, key: Path) -> tuple[uvicorn.Server, threading.Thread, int]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(socket.SOMAXCONN)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            ssl_certfile=str(cert),
            ssl_keyfile=str(key),
            proxy_headers=False,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    return server, thread, int(listener.getsockname()[1])


def _request(
    port: int,
    method: str,
    path: str,
    *,
    bearer: str | None = None,
    body: bytes | None = None,
    content_type: str | None = None,
) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    if body is not None:
        headers["Content-Length"] = str(len(body))
    if content_type is not None:
        headers["Content-Type"] = content_type
    connection = http.client.HTTPSConnection(
        "127.0.0.1",
        port,
        context=ssl._create_unverified_context(),
        timeout=2.0,
    )
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {"raw_response": raw.decode("utf-8", errors="replace")}
        return response.status, payload
    finally:
        connection.close()


def _multipart_upload() -> tuple[bytes, str]:
    boundary = f"mtd-{secrets.token_hex(12)}"
    body = b"\r\n".join(
        (
            f"--{boundary}".encode(),
            b'Content-Disposition: form-data; name="file"; filename="sample.wav"',
            b"Content-Type: audio/wav",
            b"",
            b"wire-auth-evidence",
            f"--{boundary}--".encode(),
            b"",
        )
    )
    return body, f"multipart/form-data; boundary={boundary}"


def _wait_until_ready(port: int) -> None:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status, _ = _request(port, "GET", "/api/runtime")
            if status == 200:
                return
            last_error = RuntimeError(f"/api/runtime returned {status}")
        except (ConnectionError, OSError, ssl.SSLError, http.client.HTTPException) as exc:
            last_error = exc
        time.sleep(0.05)
    raise RuntimeError(f"Uvicorn did not become ready: {last_error}")


def _protected_statuses(
    port: int,
    bearer: str | None,
    upload: bytes,
    upload_content_type: str,
) -> dict[str, int]:
    return {
        "list": _request(port, "GET", "/api/jobs", bearer=bearer)[0],
        "create": _request(
            port,
            "POST",
            "/api/jobs",
            bearer=bearer,
            body=upload,
            content_type=upload_content_type,
        )[0],
        "get": _request(port, "GET", f"/api/jobs/{MISSING_JOB_ID}", bearer=bearer)[0],
        "delete": _request(port, "DELETE", f"/api/jobs/{MISSING_JOB_ID}", bearer=bearer)[0],
    }


def _wait_for_review(port: int, bearer: str, job_id: str) -> tuple[int, str | None]:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    status, payload = 0, {}
    while time.monotonic() < deadline:
        status, payload = _request(port, "GET", f"/api/jobs/{job_id}", bearer=bearer)
        if status == 200 and payload.get("status") == "waiting_review":
            return status, str(payload["status"])
        time.sleep(0.025)
    return status, payload.get("status") if isinstance(payload.get("status"), str) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    helpers = _load_live_runtime_helpers()
    configured_bearer = secrets.token_urlsafe(24)
    result: dict[str, Any] = {
        "probe": "scripts/afk4-y7-jobs-auth-and-export-caveat/probe_uvicorn_job_route_auth.py",
        "transport": "locally-run Uvicorn over TLS HTTP/1.1 on loopback",
        "auth_seam": "production LiveAccessRegistry shared bearer",
        "job_execution": "deterministic runner; proves admission and JobManager lifecycle, not a model decode",
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        scratch = Path(tmpdir)
        cert, key = scratch / "server.crt", scratch / "server.key"
        _generate_certificate(cert, key)
        app = create_app(
            model_path="not-loaded-by-wire-auth-probe",
            runs_dir=scratch / "runs",
            live_enabled=True,
            live_runtime_factory=helpers.make_live_runtime,
            live_auth_state_path=scratch / "live-auth.json",
            live_server_cert_sha256=FINGERPRINT,
            live_shared_token=configured_bearer,
            live_helper_lease_seconds=30.0,
        )
        app.state.manager.model_runner = _DeterministicRunner()
        server, thread, port = _start_server(app, cert, key)
        try:
            _wait_until_ready(port)
            upload, upload_content_type = _multipart_upload()
            missing = _protected_statuses(port, None, upload, upload_content_type)
            wrong = _protected_statuses(port, secrets.token_urlsafe(24), upload, upload_content_type)
            created_status, created = _request(
                port,
                "POST",
                "/api/jobs",
                bearer=configured_bearer,
                body=upload,
                content_type=upload_content_type,
            )
            job_id = created.get("id") if created_status == 200 else None
            get_status, job_status = (
                _wait_for_review(port, configured_bearer, job_id)
                if isinstance(job_id, str)
                else (0, None)
            )
            admitted = {
                "create": created_status,
                "list": _request(port, "GET", "/api/jobs", bearer=configured_bearer)[0],
                "get": get_status,
                "delete": (
                    _request(port, "DELETE", f"/api/jobs/{job_id}", bearer=configured_bearer)[0]
                    if isinstance(job_id, str)
                    else 0
                ),
                "observed_job_status_before_delete": job_status,
            }
            result["checks"] = {
                "missing_bearer_statuses": missing,
                "wrong_bearer_statuses": wrong,
                "configured_bearer_statuses": admitted,
            }
        finally:
            server.should_exit = True
            thread.join(timeout=TIMEOUT_SECONDS)
            result["server_stopped"] = not thread.is_alive()

    expected_rejections = {"list": 401, "create": 401, "get": 401, "delete": 401}
    configured = result.get("checks", {}).get("configured_bearer_statuses", {})
    result["success"] = (
        result.get("checks", {}).get("missing_bearer_statuses") == expected_rejections
        and result.get("checks", {}).get("wrong_bearer_statuses") == expected_rejections
        and {name: configured.get(name) for name in expected_rejections} == {
            "list": 200,
            "create": 200,
            "get": 200,
            "delete": 200,
        }
        and configured.get("observed_job_status_before_delete") == "waiting_review"
        and result["server_stopped"]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
