#!/usr/bin/env python3
"""Probe shared-principal revocation across REAL process restarts, on the real wire.

Question answered: when an operator revokes the leaked shared bearer through the
production route (`DELETE /api/live/devices/shared-token`, loopback only), and the
service is then stopped and started again as a new OS process against the same state
directory --

  1. is the leaked bearer still dead?                          (durability)
  2. does a device paired the normal way still work?           (no collateral lockout)
  3. does rotating the shared token in configuration recover?  (operator not bricked)
  4. does a padded `Authorization` header still authenticate?  (h11, not TestClient)

`probe_shared_revocation_restart.py` answers (1) by constructing a second registry inside
one interpreter. That shares a process, an import table and a page cache with the first,
so it cannot see anything that only a real restart would expose. This probe spawns three
successive `uvicorn` child processes over TLS on a loopback port and talks to them with
`http.client` and a raw TLS socket.

Run:
  env PYTHONPATH="$PWD" .venv/bin/python \
    scripts/afk3-x5-auth-residual/probe_shared_revocation_process_restart.py \
    --output evidence/phase1/x5-auth-residual/shared-revocation-process-restart.json
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

FINGERPRINT = "ab" * 32
SHARED_DEVICE_ID = "shared-token"
LEAKED_TOKEN = "leaked-shared-token"
ROTATED_TOKEN = "rotated-shared-token"
PAIRED_DEVICE_ID = "already-paired-macbook"
PAIRED_TOKEN = "already-paired-device-token"
TIMEOUT_SECONDS = 30.0


# --------------------------------------------------------------------------- child mode


def _serve(state_path: str, cert: str, key: str, token: str, port_file: str) -> int:
    """Run one live service process. This is the thing that gets restarted."""
    import importlib.util
    import uvicorn

    from moss_transcribe_diarize.app.server import create_app

    spec = importlib.util.spec_from_file_location(
        "restart_probe_runtime", ROOT / "tests" / "test_live_api.py"
    )
    helpers = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = helpers
    spec.loader.exec_module(helpers)

    app = create_app(
        model_path="fake-model",
        runs_dir=str(Path(state_path).parent / "runs"),
        live_enabled=True,
        # Each successful create consumes one id; a probe that authenticates several times
        # per process needs several, or the second success is indistinguishable from a 500.
        live_runtime_factory=lambda: helpers.make_live_runtime(
            session_ids=tuple(f"restart-probe-{index}" for index in range(8))
        ),
        live_auth_state_path=state_path,
        live_server_cert_sha256=FINGERPRINT,
        live_shared_token=token,
        live_helper_lease_seconds=30.0,
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(socket.SOMAXCONN)
    Path(port_file).write_text(str(listener.getsockname()[1]), encoding="utf-8")
    uvicorn.Server(
        uvicorn.Config(
            app,
            ssl_certfile=cert,
            ssl_keyfile=key,
            proxy_headers=False,
            log_level="warning",
        )
    ).run(sockets=[listener])
    return 0


# -------------------------------------------------------------------------- parent mode


class LiveProcess:
    """One live service OS process. Entering starts it, leaving kills it and reaps it."""

    def __init__(self, *, state_path: Path, cert: Path, key: Path, token: str, scratch: Path):
        self._argv = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--serve",
            "--state",
            str(state_path),
            "--cert",
            str(cert),
            "--key",
            str(key),
            "--token",
            token,
        ]
        self._scratch = scratch
        self._proc: subprocess.Popen | None = None
        self.port = 0
        self.pid = 0

    def __enter__(self) -> "LiveProcess":
        port_file = self._scratch / f"port-{time.monotonic_ns()}"
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        self._log_path = self._scratch / f"serve-{time.monotonic_ns()}.log"
        log = open(self._log_path, "wb")
        self._proc = subprocess.Popen(
            self._argv + ["--port-file", str(port_file)],
            env=env,
            cwd=str(ROOT),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        self.pid = self._proc.pid
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"live service exited early with {self._proc.returncode}: "
                    f"{self._log_path.read_text(errors='replace')}"
                )
            if port_file.exists():
                text = port_file.read_text(encoding="utf-8").strip()
                if text:
                    self.port = int(text)
                    break
            time.sleep(0.05)
        else:
            raise RuntimeError("live service never published a port")
        self._wait_until_ready()
        return self

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                status, _ = request(self.port, "GET", "/api/live/descriptor")
                if status == 200:
                    return
                last = RuntimeError(f"descriptor returned {status}")
            except (OSError, ssl.SSLError, http.client.HTTPException, ValueError) as exc:
                last = exc
            time.sleep(0.05)
        raise RuntimeError(f"live service never became ready: {last}")

    def __exit__(self, *exc: object) -> None:
        if self._proc is None:
            return
        self._proc.send_signal(signal.SIGTERM)
        try:
            self._proc.wait(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=TIMEOUT_SECONDS)
        # The port must be gone before the next process claims it, or "restarted" is a lie.
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.25):
                    time.sleep(0.05)
                    continue
            except OSError:
                return
        raise RuntimeError(f"port {self.port} still accepting connections after shutdown")


def request(
    port: int,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    encoded = None if body is None else json.dumps(body).encode("utf-8")
    request_headers = dict(headers or {})
    if encoded is not None:
        request_headers["Content-Type"] = "application/json"
    connection = http.client.HTTPSConnection(
        "127.0.0.1", port, context=ssl._create_unverified_context(), timeout=5.0
    )
    try:
        connection.request(method, path, body=encoded, headers=request_headers)
        response = connection.getresponse()
        raw = response.read().decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return response.status, payload
    finally:
        connection.close()


def raw_authorization_status(port: int, header_value: str) -> int:
    """Send an Authorization header h11 has to parse, byte for byte."""
    raw = socket.create_connection(("127.0.0.1", port), timeout=5.0)
    try:
        with ssl._create_unverified_context().wrap_socket(raw, server_hostname="127.0.0.1") as tls:
            tls.sendall(
                (
                    "POST /api/live/sessions HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{port}\r\n"
                    f"Authorization: {header_value}\r\n"
                    "Content-Length: 0\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                ).encode("ascii")
            )
            buffered = bytearray()
            while True:
                chunk = tls.recv(4096)
                if not chunk:
                    break
                buffered.extend(chunk)
    finally:
        raw.close()
    return int(bytes(buffered).split(b"\r\n", 1)[0].decode("ascii").split(" ", 2)[1])


def create_session(port: int, token: str) -> int:
    status, _ = request(port, "POST", "/api/live/sessions", headers={"Authorization": f"Bearer {token}"})
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--state")
    parser.add_argument("--cert")
    parser.add_argument("--key")
    parser.add_argument("--token")
    parser.add_argument("--port-file")
    args = parser.parse_args()

    if args.serve:
        return _serve(args.state, args.cert, args.key, args.token, args.port_file)
    if args.output is None:
        parser.error("--output is required")

    import probe_uvicorn_wire_auth as wire

    checks: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        scratch = Path(tmpdir)
        cert, key = scratch / "live.crt", scratch / "live.key"
        state = scratch / "live-auth.json"
        wire._generate_certificate(cert, key)
        # A device paired the ordinary way, already on disk before any of this runs.
        state.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "devices": {
                        PAIRED_DEVICE_ID: {
                            "token_digest": hashlib.sha256(PAIRED_TOKEN.encode("utf-8")).hexdigest(),
                            "paired_at": 1.0,
                            "revoked": False,
                            "revoked_at": None,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        # --- process 1: the leak is live, the operator revokes it through the real route.
        with LiveProcess(state_path=state, cert=cert, key=key, token=LEAKED_TOKEN, scratch=scratch) as one:
            checks["run1_pid"] = one.pid
            checks["run1_leaked_token_status"] = create_session(one.port, LEAKED_TOKEN)
            checks["run1_padded_header_status"] = raw_authorization_status(
                one.port, f"Bearer   {LEAKED_TOKEN}  "
            )
            checks["run1_already_paired_device_status"] = create_session(one.port, PAIRED_TOKEN)
            # Whitespace-only bearers, byte for byte as h11 receives them. One space was the
            # case ASGI and h11 disagreed on; the rest are the neighbours nobody checked.
            checks["run1_whitespace_bearer_statuses"] = {
                repr(value): raw_authorization_status(one.port, value)
                for value in ("Bearer ", "Bearer    ", "Bearer \t ", "Bearer")
            }
            # Scheme matching is case-insensitive per RFC 7235; padding around it is not authority.
            checks["run1_lowercase_scheme_status"] = raw_authorization_status(
                one.port, f"bearer  {LEAKED_TOKEN} "
            )
            revoke_status, revoke_body = request(one.port, "DELETE", f"/api/live/devices/{SHARED_DEVICE_ID}")
            checks["run1_revoke_status"] = revoke_status
            checks["run1_revoke_body"] = revoke_body
            checks["run1_leaked_token_after_revoke_status"] = create_session(one.port, LEAKED_TOKEN)
        checks["state_after_revoke"] = json.loads(state.read_text(encoding="utf-8"))

        # --- process 2: a real restart, same state dir, same configured token.
        with LiveProcess(state_path=state, cert=cert, key=key, token=LEAKED_TOKEN, scratch=scratch) as two:
            checks["run2_pid"] = two.pid
            checks["run2_leaked_token_status"] = create_session(two.port, LEAKED_TOKEN)
            checks["run2_already_paired_device_status"] = create_session(two.port, PAIRED_TOKEN)

        # --- process 3: the operator rotates the shared token and restarts again.
        with LiveProcess(state_path=state, cert=cert, key=key, token=ROTATED_TOKEN, scratch=scratch) as three:
            checks["run3_pid"] = three.pid
            checks["run3_rotated_token_status"] = create_session(three.port, ROTATED_TOKEN)
            checks["run3_leaked_token_status"] = create_session(three.port, LEAKED_TOKEN)
            checks["run3_padded_rotated_header_status"] = raw_authorization_status(
                three.port, f"Bearer  {ROTATED_TOKEN} "
            )

    # Read the marker defensively: on the code this probe was written to indict there is no
    # record at all, and an artifact that says so is worth more than a traceback that does not.
    marker = checks["state_after_revoke"].get("devices", {}).get(SHARED_DEVICE_ID)
    checks["persisted_marker"] = marker

    expectations = {
        "leaked bearer works before revocation": checks["run1_leaked_token_status"] == 200,
        "padded header authenticates over h11": checks["run1_padded_header_status"] == 200,
        "an already-paired device works": checks["run1_already_paired_device_status"] == 200,
        "no whitespace-only bearer is authority": set(
            checks["run1_whitespace_bearer_statuses"].values()
        ) == {401},
        "a lowercase scheme with padding still authenticates": checks["run1_lowercase_scheme_status"] == 200,
        "the revoke route accepts a loopback caller": checks["run1_revoke_status"] == 200,
        "the leaked bearer dies in process": checks["run1_leaked_token_after_revoke_status"] == 401,
        "the marker is on disk": bool(marker) and marker.get("revoked") is True,
        "the bearer itself is not on disk": LEAKED_TOKEN not in json.dumps(checks["state_after_revoke"]),
        "the leaked bearer stays dead after a real restart": checks["run2_leaked_token_status"] == 401,
        "revocation did not lock out a paired device": checks["run2_already_paired_device_status"] == 200,
        "rotating the shared token recovers the service": checks["run3_rotated_token_status"] == 200,
        "the leaked bearer is still dead after rotation": checks["run3_leaked_token_status"] == 401,
        "the rotated token authenticates padded too": checks["run3_padded_rotated_header_status"] == 200,
        "each run was a distinct OS process": len({checks["run1_pid"], checks["run2_pid"], checks["run3_pid"]}) == 3,
    }

    result = {
        "probe": "scripts/afk3-x5-auth-residual/probe_shared_revocation_process_restart.py",
        "transport": "three successive uvicorn OS processes over TLS on 127.0.0.1",
        "checks": checks,
        "expectations": expectations,
        "failed": sorted(name for name, ok in expectations.items() if not ok),
    }
    result["success"] = not result["failed"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"success": result["success"], "failed": result["failed"]}, sort_keys=True))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
