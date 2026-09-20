"""Owned loopback forward: exact dispatched-call/peak accounting without bodies in logs."""
import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Decoder:
    def __init__(self, port, tunnel_port, budget, log):
        self.sent = self.completed = self.active = self.peak = self.rejected = 0
        self.budget, self.tunnel_port, self.log = budget, tunnel_port, log
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(2)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                with owner.slots:
                    with owner.lock:
                        if owner.sent >= owner.budget:
                            owner.rejected += 1
                            self.send_error(429, 'Local qualification budget exhausted')
                            return
                        owner.sent += 1
                        owner.active += 1
                        owner.peak = max(owner.peak, owner.active)
                        owner.event('start')
                    conn = http.client.HTTPConnection('127.0.0.1', owner.tunnel_port, timeout=1800)
                    try:
                        headers = {k: v for k, v in self.headers.items()
                                   if k.lower() not in ('host', 'connection', 'transfer-encoding')}
                        conn.request('POST', self.path, body, headers)
                        response = conn.getresponse()
                        payload = response.read()
                        self.send_response(response.status)
                        self.send_header('Content-Type', response.getheader('Content-Type', 'application/json'))
                        self.send_header('Content-Length', str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                    except (OSError, http.client.HTTPException):
                        try:
                            self.send_error(502, 'Owned decoder forward failed')
                        except OSError:
                            pass
                    finally:
                        conn.close()
                        with owner.lock:
                            owner.active -= 1
                            owner.completed += 1
                            owner.event('end')

            def do_GET(self):
                conn = http.client.HTTPConnection('127.0.0.1', owner.tunnel_port, timeout=10)
                try:
                    conn.request('GET', self.path)
                    response = conn.getresponse()
                    payload = response.read()
                    self.send_response(response.status)
                    self.send_header('Content-Length', str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                finally:
                    conn.close()

        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def event(self, kind):
        with self.log.open('a') as stream:
            stream.write(json.dumps(dict(kind=kind, time=time.monotonic(), sent=self.sent,
                                         active=self.active, peak=self.peak))+'\n')

    def start(self):
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
