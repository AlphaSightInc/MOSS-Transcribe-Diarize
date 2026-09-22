#!/usr/bin/env python3
"""Content-free loopback vLLM-shape decoder stub for the D34 prototype."""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


MODEL = "OpenMOSS-Team/MOSS-Transcribe-Diarize"


def _audio_bytes(content_type: str, body: bytes) -> bytes:
    message = BytesParser(policy=default).parsebytes(
        b"Content-Type: " + content_type.encode("ascii") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    )
    for part in message.iter_parts():
        if part.get_param("name", header="content-disposition") == "file":
            return part.get_payload(decode=True) or b""
    raise ValueError("multipart request lacks file")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    events = args.out / "requests.jsonl"
    lock = threading.Lock()
    state = {"requests": 0, "slots": {}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def _send(self, status: int, payload: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            if self.path == "/metrics":
                self._send(200, b'vllm:num_requests_running{model_name="dryrun"} 0\n', "text/plain; version=0.0.4")
            elif self.path == "/version":
                self._send(200, b'{"version":"dryrun-loopback-stub"}\n', "application/json")
            elif self.path == "/v1/models":
                self._send(200, json.dumps({"object": "list", "data": [{"id": MODEL, "object": "model"}]}).encode(), "application/json")
            else:
                self._send(404, b'{"error":"not found"}\n', "application/json")

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            if self.path != "/v1/audio/transcriptions":
                self._send(404, b'{"error":"not found"}\n', "application/json")
                return
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            try:
                audio = _audio_bytes(self.headers.get("Content-Type", ""), body)
            except (UnicodeEncodeError, ValueError):
                self._send(400, b'{"error":"invalid multipart"}\n', "application/json")
                return
            digest = hashlib.sha256(audio).hexdigest()
            with lock:
                slot = state["slots"].setdefault(digest, len(state["slots"]))
                state["requests"] += 1
                with events.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"kind": "transcription", "ordinal": state["requests"], "window_slot": slot, "audio_bytes": len(audio)}, sort_keys=True) + "\n")
            text = f"[1][S01]dry run window {slot}[2]"
            split = max(1, len(text) // 2)
            chunks = (
                {"choices": [{"index": 0, "delta": {"content": text[:split]}}]},
                {"choices": [{"index": 0, "delta": {"content": text[split:]}}]},
            )
            payload = b"".join(b"data: " + json.dumps(chunk, separators=(",", ":")).encode() + b"\n\n" for chunk in chunks) + b"data: [DONE]\n\n"
            self._send(200, payload, "text/event-stream")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    (args.out / "server.json").write_text(json.dumps({"bind": "127.0.0.1", "port": server.server_port, "model": MODEL}, sort_keys=True) + "\n")
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
