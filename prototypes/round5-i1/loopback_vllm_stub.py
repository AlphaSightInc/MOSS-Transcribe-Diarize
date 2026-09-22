#!/usr/bin/env python3
"""THROWAWAY: answer whether F3r/F3s reach the vLLM SSE boundary correctly.

One command::

    python prototypes/f3-dryrun/loopback_vllm_stub.py --port 19400 --out /private/tmp/f3-stub

The server binds only loopback. It retains request counts and response slots, never
audio, prompts, authorization headers, or multipart bodies.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import threading
import wave
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


MODEL = "OpenMOSS-Team/MOSS-Transcribe-Diarize"


def _duration_seconds(audio: bytes) -> float:
    with wave.open(io.BytesIO(audio)) as source:
        return source.getnframes() / source.getframerate()


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
                payload = (
                    'vllm:num_requests_running{model_name="dryrun"} 0\n'
                    'vllm:num_requests_waiting{model_name="dryrun"} 0\n'
                ).encode("ascii")
                self._send(200, payload, "text/plain; version=0.0.4")
                return
            if self.path == "/version":
                self._send(200, b'{"version":"dryrun-loopback-stub"}\n', "application/json")
                return
            if self.path == "/v1/models":
                payload = json.dumps(
                    {"object": "list", "data": [{"id": MODEL, "object": "model"}]}
                ).encode("utf-8")
                self._send(200, payload, "application/json")
                return
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
            duration_seconds = _duration_seconds(audio)
            with lock:
                slots = state["slots"]
                slot = slots.setdefault(digest, len(slots))
                state["requests"] += 1
                ordinal = state["requests"]
                with events.open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(
                            {
                                "kind": "transcription",
                                "ordinal": ordinal,
                                "window_slot": slot,
                                "audio_bytes": len(audio),
                                "window_duration_seconds": duration_seconds,
                            },
                            sort_keys=True,
                        )
                        + "\n"
                    )
            # Production placement maps these offsets onto the frozen span.  Full-span
            # coordinates let the P1b pre-surface control observe tail coverage.
            text = f"[0][S01]dry run window {slot}[{duration_seconds:g}]"
            split = max(1, len(text) // 2)
            chunks = (
                {"choices": [{"index": 0, "delta": {"content": text[:split]}}]},
                {
                    "choices": [{"index": 0, "delta": {"content": text[split:]}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 8, "total_tokens": 9},
                },
            )
            payload = b"".join(
                b"data: " + json.dumps(chunk, separators=(",", ":")).encode("utf-8") + b"\n\n"
                for chunk in chunks
            ) + b"data: [DONE]\n\n"
            self._send(200, payload, "text/event-stream")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    (args.out / "server.json").write_text(
        json.dumps({"bind": "127.0.0.1", "port": server.server_port, "model": MODEL}, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
