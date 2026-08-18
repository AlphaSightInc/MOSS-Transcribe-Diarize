#!/usr/bin/env python3
"""Bootstrap the real ControlPanel for the G6 browser-reload certification.

Question: can a fresh Chrome profile load the shipped Preact ControlPanel through
the actual Vite development proxy while that proxy reaches an owned deterministic
production-route server?  This is deliberately only the bootstrap measurement;
the following G6 probe steps will create a session, reload it, and inspect its
read-only reattachment state.

Run (after ``cd frontend && npm ci`` when this worktree has no ignored
``node_modules``):

  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
    prototypes/browser-capture-feasibility/probe_g6_browser_reload.py \\
    --output evidence/phase1/y6-browser-reload/iteration-2-vite-bootstrap.json

The backend binds only the fixed loopback proxy target (127.0.0.1:8090) and
refuses to run if it is already occupied.  Vite receives ``--base /`` because
its production ``/static/`` base is itself proxied to that backend; the override
keeps the development document and its source modules on Vite while preserving
the production ``/api`` proxy.  It uses the deterministic production routes from
the G7 probe; no model inference, browser permission prompt, or display capture
occurs here.
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import threading
import time
from pathlib import Path
from urllib.request import urlopen

from probe_recreate_session import _ChromePage, _chrome_binary, _stop_process_group
from production_route_server import build_app


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
FRONTEND_DIR = REPO_ROOT / "frontend"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8090


class _ProbeFailure(RuntimeError):
    """An assertion failure whose details are safe to record in the raw artifact."""

    def __init__(self, message: str, details: dict):
        super().__init__(message)
        self.details = details


def _json(url: str) -> dict:
    with urlopen(url, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((BACKEND_HOST, 0))
        return int(sock.getsockname()[1])


def _require_port_available(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((BACKEND_HOST, port))
        except OSError as error:
            raise RuntimeError(
                f"refusing to reuse {BACKEND_HOST}:{port}; the Vite proxy target must be owned by this probe"
            ) from error


def _start_backend(app):
    import uvicorn

    _require_port_available(BACKEND_PORT)
    base_url = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
    server = uvicorn.Server(
        uvicorn.Config(app, host=BACKEND_HOST, port=BACKEND_PORT, log_level="warning", access_log=False)
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
    raise RuntimeError("deterministic production-route backend did not start")


def _stop_backend(app, server, thread) -> None:
    server.should_exit = True
    thread.join(timeout=5)
    app.state.prototype_scratch.cleanup()


def _vite_binary() -> Path:
    binary = FRONTEND_DIR / "node_modules" / ".bin" / "vite"
    if not binary.is_file():
        raise RuntimeError(
            f"Vite is unavailable at {binary}; install the lockfile dependencies with "
            "(cd frontend && npm ci) before running this probe"
        )
    return binary


def _start_vite() -> tuple[str, subprocess.Popen[str]]:
    port = _free_loopback_port()
    process = subprocess.Popen(
        [
            str(_vite_binary()),
            "--host",
            BACKEND_HOST,
            "--port",
            str(port),
            "--strictPort",
            "--base",
            "/",
        ],
        cwd=FRONTEND_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    base_url = f"http://{BACKEND_HOST}:{port}"
    app_url = f"{base_url}/"
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout is not None else ""
            raise RuntimeError(f"Vite exited before becoming ready ({process.returncode}): {output[-2000:]}")
        try:
            with urlopen(app_url, timeout=1) as response:
                if response.status == 200:
                    return app_url, process
        except Exception:
            time.sleep(0.05)
    _stop_process_group(process)
    raise RuntimeError("Vite did not become ready")


def _wait_for_mount(page: _ChromePage) -> dict:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        state = page.evaluate(
            """(() => {
              const panel = document.querySelector('.capture-supervisor');
              const status = document.querySelector('.capture-status');
              return panel && status ? {
                phase: panel.getAttribute('data-capture-phase'),
                statusLine: status.textContent,
                storageKeys: Object.keys(sessionStorage).sort(),
              } : null;
            })()"""
        )
        if isinstance(state, dict):
            return state
        time.sleep(0.05)
    raise RuntimeError("actual ControlPanel did not mount in Chrome")


def _run(chrome_bin: str) -> dict:
    app = build_app()
    backend_url = None
    backend_server = None
    backend_thread = None
    vite_url = None
    vite = None
    page = None
    try:
        backend_url, backend_server, backend_thread = _start_backend(app)
        vite_url, vite = _start_vite()
        page = _ChromePage(chrome_bin=chrome_bin, url=vite_url)
        mounted = _wait_for_mount(page)
        descriptor = page.evaluate(
            """fetch('/api/live/descriptor?client_min_protocol_version=2&client_max_protocol_version=2')
                .then(async (response) => ({status: response.status, body: await response.json()}))"""
        )
        if not isinstance(descriptor, dict):
            raise _ProbeFailure("descriptor proxy response was not an object", {"descriptor": descriptor})
        body = descriptor.get("body")
        if descriptor.get("status") != 200 or not isinstance(body, dict):
            raise _ProbeFailure("actual frontend could not reach production descriptor route", {"descriptor": descriptor})
        negotiated_descriptor = body.get("descriptor")
        if not isinstance(negotiated_descriptor, dict):
            raise _ProbeFailure("descriptor response lacked negotiated descriptor data", {"descriptor": descriptor})
        if (
            not isinstance(negotiated_descriptor.get("frame_samples"), int)
            or negotiated_descriptor["frame_samples"] <= 0
        ):
            raise _ProbeFailure("descriptor lacked a positive frame_samples geometry", {"descriptor": descriptor})
        if mounted.get("phase") != "idle":
            raise _ProbeFailure("fresh Chrome profile did not mount ControlPanel in idle state", {"mounted": mounted})
        if mounted.get("storageKeys"):
            raise _ProbeFailure("fresh Chrome profile unexpectedly had tab-scoped storage", {"mounted": mounted})
        return {
            "scope": (
                "real Chrome, actual Preact ControlPanel, local Vite proxy, and deterministic "
                "production routes; no model inference, permission prompt, or display capture"
            ),
            "all_checks_passed": True,
            "backend": {"base_url": backend_url, "proxy_target": f"{BACKEND_HOST}:{BACKEND_PORT}"},
            "vite": {
                "base_url": vite_url,
                "dev_base_override": "/",
                "served_actual_control_panel": True,
            },
            "chrome": {"headless": True, "fresh_profile": True},
            "mounted": mounted,
            "descriptor": {
                "status": descriptor["status"],
                "frame_samples": negotiated_descriptor["frame_samples"],
            },
            "does_not_cover": [
                "session creation or reload reattachment",
                "browser media permission prompts",
                "display capture",
                "model inference",
                "a deployed host",
            ],
        }
    finally:
        if page is not None:
            page.close()
        if vite is not None:
            _stop_process_group(vite)
        if backend_server is not None and backend_thread is not None:
            _stop_backend(app, backend_server, backend_thread)
        else:
            app.state.prototype_scratch.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome-bin")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "evidence" / "phase1" / "y6-browser-reload" / "vite-bootstrap.json",
    )
    args = parser.parse_args()
    result = {
        "probe": "prototypes/browser-capture-feasibility/probe_g6_browser_reload.py",
        "started_at_unix_seconds": round(time.time(), 3),
    }
    try:
        result.update(_run(_chrome_binary(args.chrome_bin)))
    except _ProbeFailure as error:
        result.update({"all_checks_passed": False, "error": str(error), "details": error.details})
    except Exception as error:
        result.update({"all_checks_passed": False, "error": f"{type(error).__name__}: {error}"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
