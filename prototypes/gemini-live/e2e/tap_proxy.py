"""THROWAWAY loopback decoder tap. Its JSONL output is private content."""
from __future__ import annotations

import base64
import io
import json
import threading
import time
import wave
from email.parser import BytesParser
from email.policy import default
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


class TapProxy:
    def __init__(self, *, port: int, upstream_port: int, budget: int, out: Path):
        self.upstream_port, self.budget, self.out = upstream_port, budget, out
        self.count = self.completed = self.failed = self.active = self.peak = 0
        self.lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                pass

            def _send(self, status: int, payload: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:  # noqa: N802
                connection = HTTPConnection('127.0.0.1', owner.upstream_port, timeout=30)
                try:
                    connection.request('GET', self.path)
                    response = connection.getresponse()
                    self._send(response.status, response.read(), response.getheader('Content-Type', 'application/json'))
                finally:
                    connection.close()

            def do_POST(self) -> None:  # noqa: N802
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                parsed = urlsplit(self.path)
                with owner.lock:
                    if owner.count >= owner.budget:
                        self._send(429, b'{"error":"DX budget exhausted"}', 'application/json')
                        return
                    owner.count += 1
                    ordinal = owner.count
                    owner.active += 1
                    owner.peak = max(owner.peak, owner.active)
                request_time = time.monotonic_ns()
                context = {}
                encoded = parse_qs(parsed.query).get('dx', [''])[0]
                if encoded:
                    context = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
                message = BytesParser(policy=default).parsebytes(
                    b'Content-Type: ' + self.headers['Content-Type'].encode() + b'\r\nMIME-Version: 1.0\r\n\r\n' + body
                )
                fields = {}
                audio = b''
                for part in message.iter_parts():
                    name = part.get_param('name', header='content-disposition')
                    value = part.get_payload(decode=True) or b''
                    if name == 'file':
                        audio = value
                    elif name:
                        fields[name] = value.decode('utf-8', errors='replace')
                try:
                    with wave.open(io.BytesIO(audio), 'rb') as source:
                        audio_seconds = source.getnframes() / source.getframerate()
                        audio_rate = source.getframerate()
                except (wave.Error, EOFError, ZeroDivisionError):
                    audio_seconds = None
                    audio_rate = None
                connection = HTTPConnection('127.0.0.1', owner.upstream_port, timeout=1800)
                response_bytes = b''
                status = 0
                response_type = 'application/json'
                error = None
                try:
                    headers = {'Content-Type': self.headers['Content-Type']}
                    if self.headers.get('Authorization'):
                        headers['Authorization'] = self.headers['Authorization']
                    connection.request('POST', parsed.path, body, headers)
                    response = connection.getresponse()
                    status = response.status
                    response_type = response.getheader('Content-Type', 'application/json')
                    response_bytes = response.read()
                    self._send(status, response_bytes, response_type)
                except Exception as exc:
                    error = type(exc).__name__
                    try:
                        self._send(502, b'{"error":"DX upstream failure"}', 'application/json')
                    except OSError:
                        pass
                finally:
                    connection.close()
                    record = {
                        'ordinal': ordinal, 'request_monotonic_ns': request_time,
                        'response_monotonic_ns': time.monotonic_ns(),
                        'context': context, 'audio_seconds': audio_seconds,
                        'audio_sample_rate': audio_rate,
                        'audio_bytes': len(audio), 'sampling_fields': fields,
                        'status': status, 'response_content_type': response_type,
                        'raw_response_text': response_bytes.decode('utf-8', errors='replace'),
                        'error_type': error,
                    }
                    with owner.lock:
                        owner.active -= 1
                        owner.completed += error is None
                        owner.failed += error is not None
                        with owner.out.open('a', encoding='utf-8') as stream:
                            stream.write(json.dumps(record, ensure_ascii=False) + '\n')

        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def counters(self) -> dict[str, int]:
        with self.lock:
            return {key: getattr(self, key) for key in ('count', 'completed', 'failed', 'active', 'peak')}
