"""Qualification proxy accounting controls; loopback upstream only."""

from __future__ import annotations

import http.client
import json
import runpy
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf


HEAD = True
ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- T5 (H, I4)
@pytest.mark.skipif(not HEAD, reason="I4 accounting exists only on HEAD")
def test_t5_proxy_counts_an_upstream_503_as_completed(tmp_path):
    from tools.qualify.decoder import Decoder

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_error(503, "upstream overloaded")

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    log = tmp_path / "decoder.jsonl"
    proxy = Decoder(0, upstream.server_address[1], 5, log)
    proxy.start()
    try:
        for _ in range(3):
            conn = http.client.HTTPConnection("127.0.0.1", proxy.server.server_address[1], timeout=10)
            conn.request("POST", "/v1/audio/transcriptions", b"x", {"Content-Type": "application/octet-stream"})
            response = conn.getresponse()
            response.read()
            status = response.status
            conn.close()
        snapshot = proxy.snapshot()
    finally:
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        thread.join()
    feature_row = runpy.run_path(str(ROOT / "prototypes/feature-rows/run.py"))
    counters = feature_row["proxy_counters"](log)
    receipt, matches = feature_row["decoder_accounting"](
        feature_row["ProxyCounters"](), counters, planned_decoder=3
    )
    print(f"\nT5 upstream status={status} proxy snapshot={snapshot} row counters={counters} "
          f"receipt={receipt} matches_plan_3/3/0={matches}")
    assert matches is False, "three upstream 503s must not reconcile as 3 completed decodes"


def _accounting(log: Path, planned: int) -> tuple[object, bool]:
    feature_row = runpy.run_path(str(ROOT / "prototypes/feature-rows/run.py"))
    after = feature_row["proxy_counters"](log)
    return feature_row["decoder_accounting"](
        feature_row["ProxyCounters"](), after, planned_decoder=planned
    )


def _post(
    proxy: object,
    path: str,
    request_id: str | None,
    *,
    row: str | None = "summaries",
) -> int:
    headers = {}
    if request_id is not None:
        headers["X-Request-ID"] = request_id
    if row is not None:
        headers["X-MOSS-Qualification-Row"] = row
    connection = http.client.HTTPConnection(
        "127.0.0.1", proxy.server.server_address[1], timeout=2
    )
    connection.request("POST", path, b"x", headers)
    response = connection.getresponse()
    status = response.status
    response.read()
    connection.close()
    return status


@pytest.mark.parametrize("upstream_status", [200, 503])
def test_vllm_runner_without_client_request_id_reconciles_by_proxy_attempt(
    tmp_path: Path,
    upstream_status: int,
) -> None:
    """Exercise the request headers built by production, not a test-authored client."""
    from moss_transcribe_diarize.app.transcription_outcome import TransientTranscriptionError
    from moss_transcribe_diarize.app.vllm_runner import VllmRunner
    from tools.qualify.decoder import accounting_incomplete, read_events, summarize_events

    observed_client_request_ids: list[str | None] = []

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            observed_client_request_ids.append(self.headers.get("X-Request-ID"))
            payload = json.dumps(
                {
                    "text": "[0][S01]hello[1.5]",
                    "usage": {"prompt_tokens": 11, "completion_tokens": 7},
                }
            ).encode()
            self.send_response(upstream_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    log = tmp_path / f"decoder-vllm-{upstream_status}.jsonl"
    from tools.qualify.decoder import Decoder

    proxy = Decoder(0, upstream.server_port, 2, log)
    proxy.start()
    proxy.set_row_owner("summaries")
    audio_path = tmp_path / "sample.wav"
    sf.write(audio_path, np.zeros(1600, dtype=np.float32), 16000)
    runner = VllmRunner(
        base_url=f"http://127.0.0.1:{proxy.server.server_port}/v1",
        model="moss-vllm",
        timeout=2,
    )
    try:
        if upstream_status == 200:
            assert runner.transcribe(audio_path).text == "[0][S01]hello[1.5]"
        else:
            with pytest.raises(TransientTranscriptionError):
                runner.transcribe(audio_path)

        events = read_events(log)
        summary = summarize_events(events, expected_row="summaries")
        _, summaries_match = _accounting(log, 1)

        assert observed_client_request_ids == [None]
        assert all(event.get("attempt_id") for event in events)
        assert all(event.get("client_request_id") is None for event in events)
        if upstream_status == 200:
            assert (summary.attempted, summary.completed, summary.upstream_failed) == (1, 1, 0)
            assert accounting_incomplete(summary, planned=1) is False
            assert summaries_match is True
        else:
            assert (summary.attempted, summary.completed, summary.upstream_failed) == (1, 0, 1)
            assert accounting_incomplete(summary, planned=1) is True
            assert summaries_match is False
    finally:
        proxy.clear_row_owner("summaries")
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        thread.join()


@pytest.mark.parametrize("upstream_status", [502, 503])
def test_non_2xx_is_upstream_failed_and_incomplete(tmp_path: Path, upstream_status: int) -> None:
    from tools.qualify.decoder import Decoder

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(upstream_status)
            self.end_headers()

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    log = tmp_path / f"decoder-{upstream_status}.jsonl"
    proxy = Decoder(0, upstream.server_port, 2, log)
    proxy.start()
    try:
        assert _post(proxy, "/failure", f"request-{upstream_status}") == upstream_status
        snapshot = proxy.snapshot()
        _, matches = _accounting(log, 1)
        events = [json.loads(line) for line in log.read_text().splitlines()]

        assert (snapshot.accepted, snapshot.completed, snapshot.upstream_failed) == (1, 0, 1)
        assert [event["kind"] for event in events] == ["start", "upstream_failed"]
        assert matches is False
    finally:
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        thread.join()


def test_connection_reset_is_upstream_failed_and_incomplete(tmp_path: Path) -> None:
    from tools.qualify.decoder import Decoder

    class ResettingUpstream(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.connection.shutdown(2)
            self.connection.close()

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), ResettingUpstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    log = tmp_path / "decoder-reset.jsonl"
    proxy = Decoder(0, upstream.server_port, 2, log)
    proxy.start()
    try:
        assert _post(proxy, "/reset", "request-reset") == 502
        snapshot = proxy.snapshot()
        _, matches = _accounting(log, 1)

        assert (snapshot.completed, snapshot.upstream_failed) == (0, 1)
        assert matches is False
    finally:
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        thread.join()


def test_retry_and_duplicate_ids_cannot_reconcile_as_two_decodes(tmp_path: Path) -> None:
    from tools.qualify.decoder import Decoder

    attempts = 0

    class RetryUpstream(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            nonlocal attempts
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            attempts += 1
            self.send_response(503 if attempts == 1 else 200)
            self.end_headers()

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), RetryUpstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    log = tmp_path / "decoder-retry.jsonl"
    proxy = Decoder(0, upstream.server_port, 3, log)
    proxy.start()
    try:
        assert [_post(proxy, "/retry", "logical-request") for _ in range(2)] == [503, 200]
        snapshot = proxy.snapshot()
        receipt, matches = _accounting(log, 2)
        delta = receipt["decoder_proxy_counter_deltas"]

        assert (snapshot.accepted, snapshot.completed, snapshot.upstream_failed) == (2, 1, 1)
        assert (delta["distinct_client_request_ids"], delta["duplicate_attempts"]) == (1, 1)
        assert matches is False
    finally:
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        thread.join()


def test_unowned_event_is_explicit_and_incomplete(tmp_path: Path) -> None:
    from tools.qualify.decoder import Decoder

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.end_headers()

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    log = tmp_path / "decoder-unowned.jsonl"
    proxy = Decoder(0, upstream.server_port, 2, log)
    proxy.start()
    try:
        assert _post(proxy, "/ok", "request-unowned", row=None) == 200
        receipt, matches = _accounting(log, 1)
        events = [json.loads(line) for line in log.read_text().splitlines()]

        assert all("row" in event and event["row"] is None for event in events)
        assert receipt["decoder_proxy_counter_deltas"]["unowned_events"] == 2
        assert matches is False
    finally:
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        thread.join()


def test_missing_client_request_id_is_informational(tmp_path: Path) -> None:
    from tools.qualify.decoder import Decoder

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.end_headers()

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    log = tmp_path / "decoder-missing-id.jsonl"
    proxy = Decoder(0, upstream.server_port, 2, log)
    proxy.start()
    try:
        assert _post(proxy, "/ok", None) == 200
        receipt, matches = _accounting(log, 1)

        delta = receipt["decoder_proxy_counter_deltas"]
        assert delta["missing_client_request_ids"] == 1
        assert delta["distinct_attempt_ids"] == 1
        assert matches is True
    finally:
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        thread.join()


def test_duplicate_success_id_is_one_logical_decode_and_incomplete(tmp_path: Path) -> None:
    from tools.qualify.decoder import Decoder

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.end_headers()

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    log = tmp_path / "decoder-duplicate.jsonl"
    proxy = Decoder(0, upstream.server_port, 3, log)
    proxy.start()
    try:
        assert [_post(proxy, "/ok", "same-request") for _ in range(2)] == [200, 200]
        receipt, matches = _accounting(log, 2)
        delta = receipt["decoder_proxy_counter_deltas"]

        assert delta["completed"] == 2
        assert delta["distinct_completed_attempt_ids"] == 2
        assert delta["distinct_client_request_ids"] == 1
        assert delta["duplicate_attempts"] == 1
        assert matches is False
    finally:
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        thread.join()


def test_unique_owned_2xx_requests_reconcile_and_can_pass(tmp_path: Path) -> None:
    from tools.qualify.decoder import Decoder

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.end_headers()

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    log = tmp_path / "decoder-healthy.jsonl"
    proxy = Decoder(0, upstream.server_port, 3, log)
    proxy.start()
    try:
        assert [_post(proxy, "/ok", f"request-{index}") for index in range(2)] == [200, 200]
        receipt, matches = _accounting(log, 2)
        delta = receipt["decoder_proxy_counter_deltas"]

        assert delta["completed"] == delta["distinct_completed_attempt_ids"] == 2
        assert delta["upstream_failed"] == delta["duplicate_attempts"] == 0
        assert matches is True
    finally:
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        thread.join()


def test_bundle_row_and_final_verdict_force_incomplete_on_accounting_defect(
    tmp_path: Path,
) -> None:
    from tools.qualify import run as qualify_run
    from tools.qualify.decoder import summarize_events

    event = {
        "kind": "start",
        "row": "row-a",
        "attempt_id": "attempt-1",
        "client_request_id": "request-a",
        "active": 1,
    }
    bundle = object.__new__(qualify_run.Bundle)
    bundle._pending_decoder_summaries = [
        ("row-a", summarize_events([event], expected_row="row-a"))
    ]
    bundle.proxy = None
    bundle.args = SimpleNamespace(budget=2, compare=None)
    bundle.out = tmp_path / "gate"
    bundle.out.mkdir()
    bundle.data = {"gates": []}
    bundle.flush = lambda: None

    row = bundle.gate("row-a", "PASS")
    assert row["status"] == "INCOMPLETE"

    log = tmp_path / "unreconciled.jsonl"
    log.write_text(json.dumps(event) + "\n", encoding="utf-8")

    class FakeProxy:
        sent = completed = 1
        upstream_failed = rejected = active = 0
        peak = 1

        def __init__(self, path: Path):
            self.log = path

        def close(self) -> None:
            pass

    bundle = object.__new__(qualify_run.Bundle)
    bundle.processes = []
    bundle.monitor_stop = threading.Event()
    bundle.monitor = None
    bundle.proxy = FakeProxy(log)
    bundle.handles = []
    bundle.out = tmp_path / "cleanup"
    bundle.args = SimpleNamespace(budget=2, compare=None)
    bundle.data = {"gates": [{"name": "row-a", "status": "PASS", "required": True}]}
    bundle.gate = lambda name, status, **_kwargs: bundle.data["gates"].append(
        {"name": name, "status": status, "required": True}
    )
    bundle.flush = lambda: None

    bundle.cleanup()
    assert bundle.data["decoder"]["counters_reconciled"] is False
    assert bundle.data["verdict"] == "INCOMPLETE"
