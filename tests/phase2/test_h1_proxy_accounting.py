"""Pane 3.3's S2 proxy-accounting control, promoted from diagnosis."""

from __future__ import annotations

import http.client
import json
import runpy
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.qualify import decoder as decoder_proxy
from tools.qualify import run as qualify_run


def test_s2_proxy_errors_are_row_owned_and_force_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: dict[str, int] = {}

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            request_id = self.headers.get("X-Request-ID", "")
            attempts[request_id] = attempts.get(request_id, 0) + 1
            if self.path == "/timeout":
                time.sleep(0.15)
            status = 503 if self.path == "/fail" else 200
            try:
                self.send_response(status)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
            except (BrokenPipeError, ConnectionResetError):
                pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()

    real_connection = http.client.HTTPConnection

    def short_upstream_timeout(
        host: str,
        port: int | None = None,
        timeout: float | object = object(),
        **kwargs: object,
    ) -> http.client.HTTPConnection:
        del timeout
        return real_connection(host, port, timeout=0.05, **kwargs)

    monkeypatch.setattr(decoder_proxy.http.client, "HTTPConnection", short_upstream_timeout)
    log = tmp_path / "decoder.jsonl"
    proxy = decoder_proxy.Decoder(0, upstream.server_port, 10, log)
    proxy.start()
    proxy_closed = False
    try:
        requests = (
            ("/fail", "request-503"),
            ("/timeout", "request-timeout"),
            ("/ok", "request-retry"),
            ("/ok", "request-retry"),
        )
        statuses = []
        for path, request_id in requests:
            connection = real_connection("127.0.0.1", proxy.server.server_port, timeout=2)
            connection.request(
                "POST",
                path,
                body=b"private-payload",
                headers={
                    "X-Request-ID": request_id,
                    "X-MOSS-Qualification-Row": "summaries",
                },
            )
            response = connection.getresponse()
            statuses.append(response.status)
            response.read()
            connection.close()

        events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        feature_row = runpy.run_path(
            str(Path(__file__).parents[2] / "prototypes" / "feature-rows" / "run.py")
        )
        after = feature_row["proxy_counters"](log)
        _, summaries_match = feature_row["decoder_accounting"](
            feature_row["ProxyCounters"](),
            after,
            planned_decoder=4,
        )

        bundle = object.__new__(qualify_run.Bundle)
        bundle.processes = []
        bundle.monitor_stop = threading.Event()
        bundle.monitor = None
        bundle.proxy = proxy
        bundle.handles = []
        bundle.out = tmp_path / "bundle"
        bundle.args = SimpleNamespace(budget=10, compare=None)
        bundle.data = {
            "gates": [{"name": "product-row", "status": "PASS", "required": True}]
        }

        def gate(name: str, status: str, **_kwargs: object) -> None:
            bundle.data["gates"].append(
                {"name": name, "status": status, "required": True}
            )

        bundle.gate = gate
        bundle.flush = lambda: None
        bundle.cleanup()
        proxy_closed = True

        observed = {
            "statuses": statuses,
            "completed": proxy.completed,
            "row_owned": all(event.get("row") == "summaries" for event in events),
            "request_ids_present": all("request_id" in event for event in events),
            "summaries_status": "PASS" if summaries_match else "INCOMPLETE",
            "bundle_status": bundle.data["verdict"],
        }
        assert observed == {
            "statuses": [503, 502, 200, 200],
            "completed": 2,
            "row_owned": True,
            "request_ids_present": True,
            "summaries_status": "INCOMPLETE",
            "bundle_status": "INCOMPLETE",
        }
    finally:
        if not proxy_closed:
            proxy.close()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join()
