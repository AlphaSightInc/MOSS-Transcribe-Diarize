#!/usr/bin/env python3
"""PROTOTYPE: force a 409 while a peer FIFO POST is still resolving.

Question: does the actual browser FIFO sender wait for every old-session response before
resetting lane sequence state, then let an operator retry a failed session recreation and
resume at sequence zero on the fresh strict-v2 session?

Run:
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
    prototypes/browser-capture-feasibility/probe_recreate_session.py \
    --output evidence/phase1/x1-frame-drop/iteration-4-recreate-session.json

The probe uses a local production-route app with deterministic runtime data.  Its only
faults are a real out-of-order strict-v2 frame (HTTP 409), a delayed peer response that
was already accepted by the old session, and one synthetic 503 on the first recreate
request.  Chrome drives the page's real FIFO and its real recovery button through CDP.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT))

from production_route_server import build_app


class _ProbeFailure(RuntimeError):
    def __init__(self, message: str, details: dict):
        super().__init__(message)
        self.details = details


def _test_live_api_module():
    import importlib.util

    path = REPO_ROOT / "tests" / "test_live_api.py"
    spec = importlib.util.spec_from_file_location("x1_recreate_test_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load deterministic runtime helpers from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _json(url: str) -> dict:
    with urlopen(url, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def _chrome_binary(explicit: str | None) -> str:
    if explicit:
        return explicit
    if path := shutil.which("google-chrome"):
        return path
    macos = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if macos.is_file():
        return str(macos)
    raise RuntimeError("Google Chrome not found; supply --chrome-bin")


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def _start_server(app):
    import uvicorn

    port = _free_loopback_port()
    base_url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    server.install_signal_handlers = lambda: None
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            _json(f"{base_url}/prototype/verdict")
            return base_url, server, thread
        except Exception:
            time.sleep(0.05)
    server.should_exit = True
    thread.join(timeout=5)
    raise RuntimeError("production-route server did not start")


def _stop_server(app, server, thread) -> None:
    server.should_exit = True
    thread.join(timeout=5)
    app.state.prototype_scratch.cleanup()


class _DevToolsSocket:
    """Tiny dependency-free CDP client; the probe must not rely on a browser plugin."""

    def __init__(self, url: str):
        parsed = urlparse(url)
        if parsed.scheme != "ws" or not parsed.hostname or not parsed.port:
            raise RuntimeError(f"unsupported DevTools websocket URL: {url}")
        self._socket = socket.create_connection((parsed.hostname, parsed.port), timeout=5)
        self._socket.settimeout(10)
        target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        self._socket.sendall(
            (
                f"GET {target} HTTP/1.1\r\nHost: {parsed.hostname}:{parsed.port}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
        )
        response = self._read_until(b"\r\n\r\n")
        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if not response.startswith(b"HTTP/1.1 101") or (
            f"sec-websocket-accept: {expected}".encode("ascii").lower() not in response.lower()
        ):
            raise RuntimeError("DevTools websocket upgrade failed")
        self._next_id = 1

    def _read_until(self, delimiter: bytes) -> bytes:
        chunks = bytearray()
        while delimiter not in chunks:
            chunk = self._socket.recv(4096)
            if not chunk:
                raise RuntimeError("DevTools websocket closed during HTTP upgrade")
            chunks.extend(chunk)
        return bytes(chunks)

    def _read_exact(self, length: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < length:
            chunk = self._socket.recv(length - len(chunks))
            if not chunk:
                raise RuntimeError("DevTools websocket closed")
            chunks.extend(chunk)
        return bytes(chunks)

    def _send_json(self, payload: dict) -> None:
        message = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(message) < 126:
            header = bytes((0x81, 0x80 | len(message)))
        elif len(message) <= 0xFFFF:
            header = bytes((0x81, 0x80 | 126)) + struct.pack("!H", len(message))
        else:
            header = bytes((0x81, 0x80 | 127)) + struct.pack("!Q", len(message))
        mask = secrets.token_bytes(4)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(message))
        self._socket.sendall(header + mask + masked)

    def _read_json(self) -> dict:
        while True:
            first, second = self._read_exact(2)
            opcode, length = first & 0x0F, second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if second & 0x80 else None
            payload = self._read_exact(length)
            if mask is not None:
                payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
            if opcode == 0x9:
                self._socket.sendall(bytes((0x8A, len(payload))) + payload)
                continue
            if opcode == 0x8:
                raise RuntimeError("DevTools websocket closed")
            if opcode != 0x1:
                raise RuntimeError(f"unexpected DevTools websocket opcode: {opcode}")
            return json.loads(payload.decode("utf-8"))

    def evaluate(self, expression: str) -> object:
        request_id = self._next_id
        self._next_id += 1
        self._send_json(
            {
                "id": request_id,
                "method": "Runtime.evaluate",
                "params": {"expression": expression, "awaitPromise": True, "returnByValue": True},
            }
        )
        while True:
            message = self._read_json()
            if message.get("id") != request_id:
                continue
            result = message.get("result", {})
            if "error" in message or "exceptionDetails" in result:
                raise RuntimeError(f"page expression failed: {message}")
            value = result.get("result", {})
            return None if value.get("type") == "undefined" else value.get("value")

    def close(self) -> None:
        self._socket.close()


class _ChromePage:
    def __init__(self, *, chrome_bin: str, url: str):
        self._profile = tempfile.TemporaryDirectory(prefix="moss-x1-recreate-")
        self._process = subprocess.Popen(
            [
                chrome_bin,
                "--headless=new",
                "--no-first-run",
                "--no-default-browser-check",
                "--remote-debugging-port=0",
                f"--user-data-dir={self._profile.name}",
                url,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._socket = self._connect()

    def _connect(self) -> _DevToolsSocket:
        active_port = Path(self._profile.name) / "DevToolsActivePort"
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise RuntimeError(f"Chrome exited before DevTools was ready ({self._process.returncode})")
            if active_port.is_file():
                lines = active_port.read_text(encoding="utf-8").splitlines()
                if lines:
                    try:
                        targets = _json(f"http://127.0.0.1:{int(lines[0])}/json/list")
                        page = next(target for target in targets if target.get("type") == "page")
                        return _DevToolsSocket(page["webSocketDebuggerUrl"])
                    except Exception:
                        pass
            time.sleep(0.05)
        raise RuntimeError("Chrome DevTools did not become available")

    def evaluate(self, expression: str) -> object:
        return self._socket.evaluate(expression)

    def close(self) -> None:
        try:
            self._socket.close()
        finally:
            _stop_process_group(self._process)
            self._profile.cleanup()


def _wait_for(page: _ChromePage, predicate: str, *, timeout_seconds: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last = None
    while time.monotonic() < deadline:
        if page.evaluate(predicate):
            last = page.evaluate("window.__mossX1RecreateProbe.state()")
            if not isinstance(last, dict):
                raise RuntimeError(f"probe state is not an object: {last!r}")
            return last
        if page.evaluate("Boolean(window.__mossX1RecreateProbe)"):
            last = page.evaluate("window.__mossX1RecreateProbe.state()")
        time.sleep(0.025)
    raise RuntimeError(f"page did not reach state {predicate}; last={last!r}")


def _attach_faults(app, response_delay_seconds: float) -> dict:
    from fastapi.responses import JSONResponse

    metrics = {
        "response_delay_ms": round(response_delay_seconds * 1_000),
        "session_create_attempts": 0,
        "forced_recreate_create_failures": 0,
        "microphone_old_response_started_monotonic_ns": None,
        "microphone_old_response_completed_monotonic_ns": None,
    }
    lock = threading.Lock()

    @app.middleware("http")
    async def recreate_faults(request, call_next):
        if request.method == "POST" and request.url.path == "/api/live/sessions":
            with lock:
                metrics["session_create_attempts"] += 1
                attempt = metrics["session_create_attempts"]
            if attempt == 2:
                with lock:
                    metrics["forced_recreate_create_failures"] += 1
                return JSONResponse({"detail": "forced recreate create failure"}, status_code=503)
            return await call_next(request)

        is_frame = request.method == "POST" and request.url.path.endswith("/frames")
        lane = request.headers.get("x-prototype-lane") if is_frame else None
        response = await call_next(request)
        if lane == "microphone" and response.status_code == 200:
            with lock:
                if metrics["microphone_old_response_started_monotonic_ns"] is None:
                    metrics["microphone_old_response_started_monotonic_ns"] = time.monotonic_ns()
                    should_delay = True
                else:
                    should_delay = False
            if should_delay:
                import asyncio

                await asyncio.sleep(response_delay_seconds)
                with lock:
                    metrics["microphone_old_response_completed_monotonic_ns"] = time.monotonic_ns()
        return response

    return metrics


def _recovery_phases(app) -> list[dict]:
    with app.state.prototype_lock:
        return [
            phase
            for phase in app.state.prototype_telemetry["phases"]
            if phase.get("phase") == "session-recovery"
        ]


def _run(chrome_bin: str, response_delay_seconds: float) -> dict:
    helpers = _test_live_api_module()
    runtime = helpers.make_live_runtime(
        max_retained_samples=320_000,
        max_frame_samples=6_400,
        session_ids=("old-session", "new-session"),
    )
    app = build_app(runtime_factory_override=lambda: runtime)
    faults = _attach_faults(app, response_delay_seconds)
    base_url, server, thread = _start_server(app)
    page = _ChromePage(chrome_bin=chrome_bin, url=f"{base_url}/capture-harness?x1_recreate_probe=1")
    try:
        ready = _wait_for(page, "Boolean(window.__mossX1RecreateProbe)")
        initial = page.evaluate("window.__mossX1RecreateProbe.initialize()")
        if not isinstance(initial, dict) or initial.get("live_session_id") != "old-session":
            raise RuntimeError(f"page did not create old session: {initial!r}")

        page.evaluate('window.__mossX1RecreateProbe.enqueue("microphone")')
        _wait_for(page, "window.__mossX1RecreateProbe.state().lanes.microphone.send_in_flight")
        page.evaluate('window.__mossX1RecreateProbe.enqueue("system", 1)')
        after_409 = _wait_for(
            page,
            "window.__mossX1RecreateProbe.state().session_recreate_required",
        )
        begun = page.evaluate("window.__mossX1RecreateProbe.beginRecreate()")
        time.sleep(response_delay_seconds / 3)
        while_peer_response_is_held = page.evaluate("window.__mossX1RecreateProbe.state()")
        failed_recreate = page.evaluate("window.__mossX1RecreateProbe.finishRecreate()")

        page.evaluate("window.__mossX1RecreateProbe.beginRecreate()")
        recovered = page.evaluate("window.__mossX1RecreateProbe.finishRecreate()")
        _wait_for(page, "window.__mossX1RecreateProbe.state().lanes.system.sent >= 1")
        page.evaluate('window.__mossX1RecreateProbe.enqueue("microphone")')
        resumed = _wait_for(page, "window.__mossX1RecreateProbe.state().lanes.microphone.sent >= 2")

        old_v2 = app.state.live_v2_sessions.get("old-session").snapshot().to_dict()
        new_v2 = app.state.live_v2_sessions.get("new-session").snapshot().to_dict()
        phases = _recovery_phases(app)
        actions = [phase.get("action") for phase in phases]
        assertions = {
            "actual_strict_v2_conflict_requires_recreate": (
                after_409["lanes"]["system"]["http"].get("409") == 1
                and after_409["session_recreate_required"]
                and not after_409["recreate_disabled"]
            ),
            "recreate_does_not_reset_while_peer_post_is_in_flight": (
                begun["session_recreate_in_progress"]
                and while_peer_response_is_held["live_session_id"] == "old-session"
                and while_peer_response_is_held["lanes"]["microphone"]["send_in_flight"]
                and while_peer_response_is_held["lanes"]["microphone"]["seq"] == 0
            ),
            "old_peer_response_drained_before_new_sequence_reset": (
                old_v2["lanes"]["microphone"]["next_sequence"] == 1
                and failed_recreate["lanes"]["microphone"]["seq"] == 0
                and faults["microphone_old_response_completed_monotonic_ns"] is not None
                and actions.count("drained") == 2
            ),
            "failed_recreate_leaves_control_usable": (
                failed_recreate["live_session_id"] is None
                and failed_recreate["session_recreate_required"]
                and not failed_recreate["recreate_disabled"]
                and faults["forced_recreate_create_failures"] == 1
            ),
            "fresh_session_resumes_at_zero_without_sequence_poisoning": (
                recovered["live_session_id"] == "new-session"
                and not recovered["session_recreate_required"]
                and resumed["lanes"]["system"]["seq"] == 1
                and resumed["lanes"]["microphone"]["seq"] == 1
                and new_v2["lanes"]["system"]["next_sequence"] == 1
                and new_v2["lanes"]["microphone"]["next_sequence"] == 1
            ),
        }
        if not all(assertions.values()):
            raise _ProbeFailure("recreate assertions failed", {
                "initial": initial,
                "after_409": after_409,
                "recreate_begun": begun,
                "while_peer_response_is_held": while_peer_response_is_held,
                "failed_recreate": failed_recreate,
                "recovered": recovered,
                "resumed": resumed,
                "faults": faults,
                "old_v2_session": old_v2,
                "new_v2_session": new_v2,
                "recovery_phases": phases,
                "assertions": assertions,
            })
        return {
            "ready": ready,
            "initial": initial,
            "after_409": after_409,
            "recreate_begun": begun,
            "while_peer_response_is_held": while_peer_response_is_held,
            "failed_recreate": failed_recreate,
            "recovered": recovered,
            "resumed": resumed,
            "faults": faults,
            "old_v2_session": old_v2,
            "new_v2_session": new_v2,
            "recovery_phases": phases,
            "assertions": assertions,
        }
    finally:
        page.close()
        _stop_server(app, server, thread)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--response-delay-ms", type=float, default=600.0)
    parser.add_argument("--chrome-bin")
    args = parser.parse_args()
    if args.response_delay_ms <= 100:
        parser.error("--response-delay-ms must exceed the probe's midpoint observation")

    result: dict = {
        "probe": "prototypes/browser-capture-feasibility/probe_recreate_session.py",
        "question": (
            "does a forced strict-v2 409 drain an already-accepted peer POST before sequence reset, "
            "survive one failed recreate click, and resume its fresh session at zero"
        ),
        "scope": (
            "local production HTTP routes and real headless Chrome FIFO/recovery-button code; "
            "deterministic provider; no model inference, microphone, or display capture"
        ),
        "requested_response_delay_ms": args.response_delay_ms,
        "passed": False,
    }
    try:
        result.update(
            _run(
                chrome_bin=_chrome_binary(args.chrome_bin),
                response_delay_seconds=args.response_delay_ms / 1_000,
            )
        )
        result["passed"] = True
    except _ProbeFailure as exc:
        result.update(exc.details)
        result["error"] = str(exc)
    except Exception as exc:
        result["error"] = str(exc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
