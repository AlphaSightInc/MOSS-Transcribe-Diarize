#!/usr/bin/env python3
"""Measure whether VllmRunner returns at the SSE terminal marker or TCP EOF."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import soundfile as sf

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.vllm_runner import VllmRunner  # noqa: E402


HOLD_SECONDS = 2.0


class _SseHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(content_length)
        events = (
            b'data: {"choices":[{"delta":{"content":"[0][S01]hello[1]"}}]}\n\n'
            b'data: {"usage":{"prompt_tokens":11,"completion_tokens":7},"choices":[]}\n\n'
            b"data: [DONE]\n\n"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        self.wfile.write(f"{len(events):X}\r\n".encode("ascii") + events + b"\r\n")
        self.wfile.flush()
        time.sleep(HOLD_SECONDS)
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SseHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "sample.wav"
            sf.write(audio_path, np.zeros(1600, dtype=np.float32), 16000)
            runner = VllmRunner(
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
                model="probe",
                timeout=10.0,
            )
            started = time.monotonic()
            result = runner.transcribe(audio_path)
            elapsed = time.monotonic() - started
    finally:
        server.server_close()
        thread.join(timeout=HOLD_SECONDS + 1.0)

    outcome = {
        "question": "Does VllmRunner return on data: [DONE] before the SSE socket closes?",
        "hold_open_seconds_after_done": HOLD_SECONDS,
        "elapsed_seconds": round(elapsed, 3),
        "returned_before_eof": elapsed < HOLD_SECONDS * 0.75,
        "text": result.text,
        "completion_tokens": result.generated_tokens,
    }
    print(json.dumps(outcome, indent=2, sort_keys=True))
    return 0 if outcome["returned_before_eof"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
