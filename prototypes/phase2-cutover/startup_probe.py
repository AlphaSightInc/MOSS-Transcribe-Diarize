"""Throwaway startup question: process active != HTTP ready.

Run: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python prototypes/phase2-cutover/startup_probe.py
Primitives: process liveness, HTTP observation, bounded deadline. Never reopen
before a valid response. Unknown: production startup latency. Falsifier: delayed
healthy HTTP fails, or dead/malformed HTTP passes. Uses the production parser.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from moss_transcribe_diarize.phase2_cutover import RuntimeView, SystemCutoverOps


def measure(case: str) -> dict:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"phase1_creation": {
                "state": "quiesced", "entrants": 0, "active_jobs": 0,
                "queued_jobs": 0, "active_live_sessions": 0,
            }} if case != "malformed" else {}).encode())

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler, bind_and_activate=False)
    server.server_bind()
    address = server.server_address
    server.server_close()
    view = RuntimeView("batch", f"http://127.0.0.1:{address[1]}", None)
    ops = SystemCutoverOps(profile=None, artifacts=None, account_profile={})
    started = time.monotonic()
    attempts = 0
    outcome = "timeout"
    status = None
    listening = threading.Event()
    def start():
        nonlocal server
        time.sleep(0.15)
        server = HTTPServer(address, Handler)
        listening.set()
        server.serve_forever(poll_interval=0.01)
    thread = threading.Thread(target=start, daemon=True)
    thread.start()
    while time.monotonic() - started < 0.5:
        attempts += 1
        if case == "dead":
            outcome = "dead"
            break
        try:
            status = ops._runtime_status(view)
            outcome = "ready"
            break
        except RuntimeError as exc:
            if not isinstance(exc.__cause__, (OSError, urllib.error.URLError)):
                outcome = "malformed"
                break
        time.sleep(0.02)
    thread_started = time.monotonic()
    listening.wait()
    server.shutdown()
    server.server_close()
    return {"case": case, "attempts": attempts, "outcome": outcome,
            "elapsed_ms": round((thread_started - started) * 1000), "status": status,
            "would_reopen": outcome == "ready"}


rows = [measure(case) for case in ("delayed", "dead", "malformed")]
print(json.dumps(rows, indent=2))
assert [row["outcome"] for row in rows] == ["ready", "dead", "malformed"]
