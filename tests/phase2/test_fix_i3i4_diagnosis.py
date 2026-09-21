"""Strict violating controls for the post-I3/I4 diagnosis signals."""

from __future__ import annotations

import asyncio
import http.client
import json
import runpy
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from _browser_workspace_fixtures import seed_workspace

from moss_transcribe_diarize.app.phase2 import MeetingHandle, Phase2Store, create_phase2_app
from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks
from tools.qualify import decoder as decoder_proxy
from tools.qualify import run as qualify_run


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="S1: one stalled retained validation starves every later owner",
)
def test_s1_stalled_validation_does_not_starve_later_retained_owners(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        tasks = FileMeetingTasks(object(), tmp_path / "file-work")
        handles = tuple(
            SimpleNamespace(owner_key=("account-a", 1), meeting_id=meeting_id)
            for meeting_id in ("owner-1", "owner-2")
        )
        for handle in handles:
            owner_dir = tasks.retained_root / handle.owner_key[0] / handle.meeting_id
            owner_dir.mkdir(parents=True)
            (owner_dir / "owner.json").write_text("{}\n", encoding="utf-8")

        first_entered = threading.Event()
        release_first = threading.Event()
        second_validated = threading.Event()
        second_resumed = asyncio.Event()

        def validate(handle: object, owner_dir: Path) -> Path:
            if handle.meeting_id == "owner-1":  # type: ignore[attr-defined]
                first_entered.set()
                release_first.wait()
            else:
                second_validated.set()
            return owner_dir / "input.wav"

        async def run(
            handle: object,
            _input_path: Path,
            started: asyncio.Event,
            *,
            resumed: bool,
        ) -> None:
            assert resumed is True
            started.set()
            if handle.meeting_id == "owner-2":  # type: ignore[attr-defined]
                second_resumed.set()

        tasks._verified_retained_input = validate  # type: ignore[method-assign]
        tasks._run = run  # type: ignore[method-assign]

        class Store:
            async def active_file_meetings(self) -> tuple[object, ...]:
                return handles

        claimed = await tasks.resume_retained_work(Store())
        assert claimed == frozenset(
            (("account-a", "owner-1"), ("account-a", "owner-2"))
        )
        assert await asyncio.to_thread(first_entered.wait, 1)
        try:
            validated = await asyncio.to_thread(second_validated.wait, 0.2)
            try:
                await asyncio.wait_for(second_resumed.wait(), timeout=0.2)
                resumed = True
            except TimeoutError:
                resumed = False
            assert (validated, resumed) == (True, True)
        finally:
            release_first.set()
            coordinator = tasks._retained_resume_task
            if coordinator is not None:
                await coordinator
            await tasks.stop()

    asyncio.run(exercise())


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="S2: upstream failures count completed and cannot make rows INCOMPLETE",
)
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


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="S3: fallback-terminalized retained owner is reclaimed only next boot",
)
def test_s3_lifespan_reclaims_fallback_interrupted_owner_in_same_boot(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        database = tmp_path / "state.sqlite3"
        work_root = tmp_path / "file-work"
        store = await Phase2Store.open(database)
        try:
            account, _ = await seed_workspace(store, "account-a")
            handle = await store.workspace(account).create_meeting("file")
        finally:
            await store.close()

        owner_dir = tmp_path / "file-retained" / account.account_id / handle.meeting_id
        owner_dir.mkdir(parents=True)
        (owner_dir / "retained-prefix").write_bytes(b"retained work")
        first = create_phase2_app(
            database_path=database,
            file_runner=object(),
            file_work_root=work_root,
            meeting_audio_root=tmp_path / "meeting-audio",
        )
        async with first.router.lifespan_context(first):
            reopened = MeetingHandle(
                first.state.phase2_store,
                account.account_id,
                account.authority_generation,
                handle.meeting_id,
            )
            assert (await reopened.snapshot()).status == "interrupted"
            remained_after_fallback = owner_dir.exists()

        second = create_phase2_app(
            database_path=database,
            file_runner=object(),
            file_work_root=work_root,
            meeting_audio_root=tmp_path / "meeting-audio",
        )
        async with second.router.lifespan_context(second):
            reclaimed_on_next_boot = not owner_dir.exists()

        assert (remained_after_fallback, reclaimed_on_next_boot) == (False, True)

    asyncio.run(exercise())
