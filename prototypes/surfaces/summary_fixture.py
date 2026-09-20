"""PROTOTYPE: local Account app plus OpenAI-compatible HTTPS summary provider.

Question: do the real browser summary worker and verifier distinguish all-current,
one-failed, and unconfigured outcomes without any request leaving loopback?
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import ssl
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace


def transcript_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as stream:
        return stream.getnframes() / stream.getframerate()


class FixtureRunner:
    model_path = "round4-local-summary-fixture"

    def transcribe(self, input_path, **_options):
        duration = transcript_duration(Path(input_path))
        end = max(2.0, duration)
        return SimpleNamespace(text=f"[0][S01]Local summary dry run transcript[{end:.3f}]")


class LocalProvider:
    def __init__(self, *, port: int, origin: str, certificate: Path, key: Path, receipt: Path):
        self.origin = origin
        self.receipt = receipt
        self.lock = threading.Lock()
        self.request_count = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def _cors(self):
                self.send_header("Access-Control-Allow-Origin", owner.origin)
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

            def do_OPTIONS(self):
                self.send_response(204)
                self._cors()
                self.end_headers()

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                request = json.loads(body)
                model = request.get("model")
                segments = json.loads(request["messages"][-1]["content"])["segments"]
                ends = [row.get("end", "00:00:00") for row in segments]
                long_transcript = any(value >= "00:01:00" for value in ends)
                invalid = model == "fixture-one-fail" and long_transcript
                document = {
                    "summary": "Local canned summary.",
                    "topics": [{"title": "Dry run", "description": "Loopback provider response."}],
                    "details": [{"title": "Timestamp", "description": "Valid HH:MM:SS fixture.", "timestamp": "00:00:01"}],
                    "speaker_background": [],
                    "data_references": [],
                }
                content = "not-json" if invalid else json.dumps(document)
                encoded = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
                with owner.lock:
                    owner.request_count += 1
                    row = {"request": owner.request_count, "path": self.path, "model": model,
                           "transcript": "180s" if long_transcript else "50s",
                           "result": "invalid" if invalid else "valid"}
                    with owner.receipt.open("a") as stream:
                        stream.write(json.dumps(row) + "\n")
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


async def seed_completed_meeting(database: Path) -> None:
    from moss_transcribe_diarize.app.phase2 import Phase2Store

    store = await Phase2Store.open(database)
    try:
        account, _session = await store.bootstrap_browser(None, open_workspace=True)
        handle = await store.workspace(account).create_meeting("file")
        await handle.commit_transcript({"segments": [{"start": 0, "end": 2, "speaker": "S01",
                                                        "text": "Preseeded disabled-summary control."}]})
        await handle.finish("completed")
    finally:
        await store.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--app-port", type=int, required=True)
    parser.add_argument("--provider-port", type=int, required=True)
    parser.add_argument("--cert", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--ready", type=Path, required=True)
    args = parser.parse_args()
    args.state.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text("")

    from moss_transcribe_diarize.app import phase2
    from tests.reference_ui_screenshot_diff import _ui_runtime
    # Prototype-only runtime exception. R4-7 owns supported-runtime qualification.
    phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
    database = args.state / "fixture.sqlite3"
    asyncio.run(seed_completed_meeting(database))
    app = phase2.create_phase2_app(
        database_path=database,
        file_runner=FixtureRunner(),
        file_work_root=args.state / "file-work",
        meeting_audio_root=args.state / "meeting-audio",
        open_workspace=True,
        live_runtime_factory=_ui_runtime,
        live_helper_lease_seconds=30,
    )

    import uvicorn
    origin = f"https://127.0.0.1:{args.app_port}"
    provider = LocalProvider(port=args.provider_port, origin=origin,
                             certificate=args.cert, key=args.key, receipt=args.receipt)
    provider.start()
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=args.app_port, log_level="warning", access_log=False,
        ssl_certfile=str(args.cert), ssl_keyfile=str(args.key),
    ))

    def ready_marker():
        deadline = time.monotonic() + 30
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        if server.started:
            args.ready.write_text(json.dumps({"app": origin,
                                               "provider": f"https://127.0.0.1:{args.provider_port}"}) + "\n")

    threading.Thread(target=ready_marker, daemon=True).start()
    try:
        server.run()
    finally:
        provider.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
