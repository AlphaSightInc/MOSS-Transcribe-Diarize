"""Local stand-in for an OpenAI-compatible transcription server (stdlib, ephemeral port).

`replies` is a queue consumed one per `POST /audio/transcriptions`; each entry is a JSON
dict (HTTP 200), a `(status, body)` tuple, `("sleep", seconds, entry)`, or a callable
`(form, audio_seconds) -> entry`. When the queue is empty, `default` answers.
"""
from __future__ import annotations

import io
import json
import threading
import time
import wave
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeTranscriptionServer:
    def __init__(self, *, replies=(), default=None, models=("whisper-1",),
                 require_key: str | None = None):
        self.replies = list(replies)
        self.default = default
        self.models = list(models)
        self.require_key = require_key
        self.requests: list[dict] = []
        self._lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, body):
                raw = body if isinstance(body, bytes) else (
                    body.encode() if isinstance(body, str) else json.dumps(body).encode())
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _authorized(self):
                if fake.require_key is None:
                    return True
                return self.headers.get("Authorization") == f"Bearer {fake.require_key}"

            def do_GET(self):
                if self.path != "/v1/models":
                    return self._send(404, {"error": {"message": "not found"}})
                if not self._authorized():
                    return self._send(401, {"error": {"message": "Incorrect API key"}})
                self._send(200, {"object": "list",
                                 "data": [{"id": name, "object": "model"} for name in fake.models]})

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                message = BytesParser(policy=email_policy).parsebytes(
                    b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + body)
                form: dict[str, list[str]] = {}
                seconds = 0.0
                for part in message.iter_parts():
                    name = part.get_param("name", header="content-disposition")
                    payload = part.get_payload(decode=True)
                    if name == "file":
                        with wave.open(io.BytesIO(payload), "rb") as wav:
                            seconds = wav.getnframes() / wav.getframerate()
                            fmt = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
                        form.setdefault("_wav_format", []).append(str(fmt))
                    else:
                        form.setdefault(name, []).append(payload.decode())
                with fake._lock:
                    fake.requests.append({"path": self.path, "form": form, "seconds": seconds,
                                          "authorization": self.headers.get("Authorization")})
                    entry = fake.replies.pop(0) if fake.replies else fake.default
                if self.path != "/v1/audio/transcriptions":
                    return self._send(404, {"error": {"message": "not found"}})
                if not self._authorized():
                    return self._send(401, {"error": {"message": "Incorrect API key"}})
                while True:
                    if callable(entry):
                        entry = entry(form, seconds)
                    elif isinstance(entry, tuple) and entry and entry[0] == "sleep":
                        time.sleep(entry[1])
                        entry = entry[2]
                    else:
                        break
                if isinstance(entry, tuple):
                    return self._send(*entry)
                self._send(200, entry)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, args=(.05,), daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/v1"

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
