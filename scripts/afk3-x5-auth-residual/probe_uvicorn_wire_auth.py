#!/usr/bin/env python3
"""Probe reserved-device and whitespace auth behavior through local Uvicorn.

Question answered: do the auth fixes still reject a newly paired reserved id, a
legacy persisted reserved-id credential, and an all-whitespace bearer when
Uvicorn/h11 rather than TestClient parses the request?

Run:
  env PYTHONPATH="$PWD" .venv/bin/python \
    scripts/afk3-x5-auth-residual/probe_uvicorn_wire_auth.py \
    --output evidence/phase1/x5-auth-residual/iteration-6-uvicorn-wire-auth.json
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import importlib.util
import ipaddress
import json
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

from moss_transcribe_diarize.app.live_auth import _ALLOWED_PEER_NETWORKS
from moss_transcribe_diarize.app.server import create_app
from moss_transcribe_diarize.app.web_cli import _live_shared_token


ROOT = Path(__file__).resolve().parents[2]
FINGERPRINT = "ab" * 32
SHARED_DEVICE_ID = "shared-token"
CONFIGURED_TOKEN = "configured-token"
LEGACY_TOKEN = "legacy-reserved-device-token"
TIMEOUT_SECONDS = 10.0


def _load_runtime_helpers() -> ModuleType:
    source = ROOT / "tests" / "test_live_api.py"
    spec = importlib.util.spec_from_file_location("uvicorn_wire_auth_runtime", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load live runtime helper from {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _private_source_address() -> str:
    """Return a local address that production peer admission recognizes as non-loopback."""
    candidates: set[str] = set()
    try:
        candidates.update(
            address[4][0]
            for address in socket.getaddrinfo(socket.gethostname(), 0, socket.AF_INET)
        )
    except socket.gaierror:
        pass
    for destination in ("192.0.2.1", "8.8.8.8"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect((destination, 9))
                candidates.add(probe.getsockname()[0])
        except OSError:
            pass
    try:
        listed = subprocess.run(
            ["ifconfig"], capture_output=True, text=True, check=False, timeout=2.0
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        listed = None
    if listed is not None and listed.returncode == 0:
        for field in listed.stdout.split():
            try:
                address = ipaddress.ip_address(field)
            except ValueError:
                continue
            if isinstance(address, ipaddress.IPv4Address):
                candidates.add(str(address))

    for candidate in sorted(candidates):
        address = ipaddress.ip_address(candidate)
        if address.is_loopback or not any(address in network for network in _ALLOWED_PEER_NETWORKS):
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind((candidate, 0))
        except OSError:
            continue
        return candidate
    raise RuntimeError("no local non-loopback address accepted by live peer admission")


def _generate_certificate(cert: Path, key: Path) -> None:
    generated = subprocess.run(
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
        timeout=10.0,
    )
    if generated.returncode != 0:
        raise RuntimeError(f"openssl failed: {generated.stderr.strip()}")


def _start_server(app: Any, cert: Path, key: Path) -> tuple[uvicorn.Server, threading.Thread, int]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("0.0.0.0", 0))
    listener.listen(socket.SOMAXCONN)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",
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


def _json_request(
    host: str,
    port: int,
    method: str,
    path: str,
    *,
    source_address: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    encoded = None if body is None else json.dumps(body).encode("utf-8")
    request_headers = dict(headers or {})
    if encoded is not None:
        request_headers["Content-Type"] = "application/json"
    connection = http.client.HTTPSConnection(
        host,
        port,
        context=ssl._create_unverified_context(),
        source_address=(source_address, 0),
        timeout=2.0,
    )
    try:
        connection.request(method, path, body=encoded, headers=request_headers)
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        return response.status, payload
    finally:
        connection.close()


def _raw_whitespace_bearer_status(host: str, port: int, source_address: str) -> int:
    raw = socket.create_connection((host, port), source_address=(source_address, 0), timeout=2.0)
    try:
        with ssl._create_unverified_context().wrap_socket(raw, server_hostname=host) as connection:
            connection.sendall(
                (
                    "POST /api/live/sessions HTTP/1.1\r\n"
                    f"Host: {host}:{port}\r\n"
                    "Authorization: Bearer \r\n"
                    "Content-Length: 0\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                ).encode("ascii")
            )
            response = bytearray()
            while True:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)
    finally:
        raw.close()
    status_line = bytes(response).split(b"\r\n", 1)[0].decode("ascii")
    _, status, _ = status_line.split(" ", 2)
    return int(status)


def _wait_until_ready(port: int) -> None:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status, _ = _json_request(
                "127.0.0.1", port, "GET", "/api/live/descriptor", source_address="127.0.0.1"
            )
            if status == 200:
                return
            last_error = RuntimeError(f"descriptor returned {status}")
        except (ConnectionError, OSError, ssl.SSLError, http.client.HTTPException) as exc:
            last_error = exc
        time.sleep(0.05)
    raise RuntimeError(f"Uvicorn did not become ready: {last_error}")


def _whitespace_token_file_is_refused(path: Path) -> bool:
    path.write_text(" \n", encoding="utf-8")
    args = argparse.Namespace(live_shared_token_file=str(path), live=True)
    try:
        _live_shared_token(args)
    except SystemExit as exc:
        return str(exc) == "--live-shared-token-file must contain exactly one non-empty line."
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    helpers = _load_runtime_helpers()
    source_address = _private_source_address()
    with tempfile.TemporaryDirectory() as tmpdir:
        scratch = Path(tmpdir)
        cert, key = scratch / "live.crt", scratch / "live.key"
        state = scratch / "live-auth.json"
        _generate_certificate(cert, key)
        state.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "devices": {
                        SHARED_DEVICE_ID: {
                            "token_digest": hashlib.sha256(LEGACY_TOKEN.encode("utf-8")).hexdigest(),
                            "paired_at": 1.0,
                            "revoked": False,
                            "revoked_at": None,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        app = create_app(
            model_path="fake-model",
            runs_dir=scratch / "runs",
            live_enabled=True,
            live_runtime_factory=lambda: helpers.make_live_runtime(session_id="uvicorn-wire-session"),
            live_auth_state_path=state,
            live_server_cert_sha256=FINGERPRINT,
            live_shared_token=CONFIGURED_TOKEN,
            live_helper_lease_seconds=30.0,
        )
        server, thread, port = _start_server(app, cert, key)
        try:
            _wait_until_ready(port)
            issued_status, issued = _json_request(
                "127.0.0.1", port, "POST", "/api/live/pairing-codes", source_address="127.0.0.1"
            )
            reserved_status, reserved = _json_request(
                source_address,
                port,
                "POST",
                "/api/live/pairings",
                source_address=source_address,
                body={"device_id": SHARED_DEVICE_ID, "pairing_payload": issued["pairing_payload"]},
            )
            legacy_status, _ = _json_request(
                source_address,
                port,
                "POST",
                "/api/live/sessions",
                source_address=source_address,
                headers={"Authorization": f"Bearer {LEGACY_TOKEN}"},
            )
            configured_status, configured = _json_request(
                source_address,
                port,
                "POST",
                "/api/live/sessions",
                source_address=source_address,
                headers={"Authorization": f"Bearer {CONFIGURED_TOKEN}"},
            )
            whitespace_bearer_status = _raw_whitespace_bearer_status(source_address, port, source_address)
            whitespace_token_file_refused = _whitespace_token_file_is_refused(scratch / "whitespace-token")
        finally:
            server.should_exit = True
            thread.join(timeout=TIMEOUT_SECONDS)

    result = {
        "probe": "scripts/afk3-x5-auth-residual/probe_uvicorn_wire_auth.py",
        "transport": "locally-run Uvicorn over TLS HTTP/1.1",
        "private_peer_ip": source_address,
        "checks": {
            "loopback_pairing_code_status": issued_status,
            "reserved_device_pairing_status": reserved_status,
            "reserved_device_pairing_detail": reserved.get("detail"),
            "legacy_reserved_device_token_status": legacy_status,
            "configured_token_create_session_status": configured_status,
            "configured_token_owner_device_id": configured.get("owner_device_id"),
            "raw_whitespace_bearer_status": whitespace_bearer_status,
            "whitespace_token_file_refused_before_start": whitespace_token_file_refused,
        },
    }
    required = (
        result["checks"]["loopback_pairing_code_status"] == 200,
        result["checks"]["reserved_device_pairing_status"] == 403,
        result["checks"]["reserved_device_pairing_detail"] == "device_id is reserved.",
        result["checks"]["legacy_reserved_device_token_status"] == 401,
        result["checks"]["configured_token_create_session_status"] == 200,
        result["checks"]["configured_token_owner_device_id"] == SHARED_DEVICE_ID,
        result["checks"]["raw_whitespace_bearer_status"] == 401,
        result["checks"]["whitespace_token_file_refused_before_start"],
    )
    result["success"] = all(required)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
