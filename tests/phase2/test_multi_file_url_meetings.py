from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
from _browser_workspace_fixtures import seed_workspace

from fastapi.testclient import TestClient
import pytest

from moss_transcribe_diarize.app.phase2 import (
    Phase2Store,
    SESSION_COOKIE,
    create_phase2_app,
)
from moss_transcribe_diarize.app.phase2_url import UrlAcquisitionRejected, UrlMediaAcquirer



class RecordingRunner:
    model_path = "recording-file-runner"

    def __init__(self) -> None:
        self.inputs: list[tuple[str, bytes]] = []

    def transcribe(self, input_path: str | Path, **_: object):
        path = Path(input_path)
        data = path.read_bytes()
        self.inputs.append((path.name, data))
        label = data.decode("ascii")
        return SimpleNamespace(text=f"[0][S01]{label}[1]")


class FixtureAcquirer:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def acquire(self, source_url: str, directory: Path) -> Path:
        self.urls.append(source_url)
        if source_url.endswith("/fails"):
            raise UrlAcquisitionRejected("fixture acquisition failed")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "input.wav"
        path.write_bytes(source_url.rsplit("/", 1)[-1].encode("ascii"))
        return path


class ControlledAcquirer:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    async def acquire(self, source_url: str, directory: Path) -> Path:
        self.started.set()
        assert await asyncio.to_thread(self.release.wait, 5), "test did not release acquisition"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "input.wav"
        path.write_bytes(b"detached-url")
        return path


async def provision(database: Path) -> dict[str, str]:
    store = await Phase2Store.open(database)
    try:
        sessions: dict[str, str] = {}
        for subject, email in (("sub-a", "sub-a"), ("sub-b", "sub-b")):
            _, sessions[subject] = await seed_workspace(store, subject)
        _, sessions["sub-a-second"] = await seed_workspace(store, "sub-a")
        return sessions
    finally:
        await store.close()


def make_app(database: Path, runner: object, work_root: Path, acquirer: object):
    return create_phase2_app(
        database_path=database,
        file_runner=runner,
        file_work_root=work_root,
        url_acquirer=acquirer,
    )


def session(client: TestClient, session_id: str | None) -> None:
    client.cookies.clear()
    if session_id is not None:
        client.cookies.set(SESSION_COOKIE, session_id, domain="moss.test", path="/")


def await_terminal(client: TestClient, meeting_id: str, status: str) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/meetings/{meeting_id}")
        if response.status_code == 200 and response.json()["status"] == status:
            return response.json()
        time.sleep(0.01)
    raise AssertionError(f"Meeting {meeting_id} did not reach {status}")


def execute_submission_script(workspace_html: str) -> dict[str, object]:
    match = re.search(r"<script>(.*)</script>", workspace_html, flags=re.DOTALL)
    assert match is not None
    harness = r"""
const fs = require('node:fs');
const vm = require('node:vm');
let submitListener = null;
let reloads = 0;
const calls = [];
const created = [];
const statusFixture = {textContent: ''};
const formFixture = {
  elements: {
    file: {files: [{name: 'one.wav'}, {name: 'two.wav'}]},
    urls: {value: 'https://media.test/http-failure\nhttps://media.test/good'},
  },
  addEventListener: (_name, listener) => { submitListener = listener; },
};
globalThis.document = {
  querySelector: (selector) => selector.includes('form') ? formFixture
    : selector.includes('status') ? statusFixture : null,
  querySelectorAll: () => [],
  dispatchEvent: (event) => { if (event.type === 'moss:meeting-created') created.push(event.detail.meeting_id); },
};
globalThis.CustomEvent = class { constructor(type, options) { this.type = type; this.detail = options.detail; } };
globalThis.FormData = class { append() {} };
globalThis.fetch = async (path) => {
  calls.push(path);
  if (calls.length === 2) throw new Error('network failure');
  return {ok: calls.length !== 3, json: async () => ({id: `accepted-${calls.length}`})};
};
globalThis.location = {reload: () => { reloads += 1; }};
vm.runInThisContext(fs.readFileSync(0, 'utf8'));
(async () => {
  await submitListener({preventDefault() {}});
  process.stdout.write(JSON.stringify({calls, created, status: statusFixture.textContent, reloads}));
})().catch((error) => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        ["node", "-e", harness],
        input=match.group(1),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_mixed_serial_items_are_independent_and_owner_bound(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    runner = RecordingRunner()
    acquirer = FixtureAcquirer()
    app = make_app(database, runner, tmp_path / "file-work", acquirer)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        workspace = client.get("/").text
        assert 'aria-label="Workspace"' in workspace
        for section in ("file", "history", "voiceprints"):
            assert f'href="#workspace-{section}"' in workspace
            assert f'id="workspace-{section}"' in workspace
        assert 'id="voiceprint-bank-app"' in workspace
        assert 'type="file" multiple' in workspace
        assert '<textarea name="urls">' in workspace
        assert "async function submitItem" in workspace
        assert "catch" in workspace
        assert "for (const file of files)" in workspace
        assert "for (const url of urls)" in workspace
        assert execute_submission_script(workspace) == {
            "calls": [
                "/api/meetings/file",
                "/api/meetings/file",
                "/api/meetings/url",
                "/api/meetings/url",
            ],
            "status": "2 accepted; 2 rejected. Accepted work continues on the server.",
            "reloads": 1,
            "created": ["accepted-1", "accepted-4"],
        }

        accepted = [
            client.post(
                "/api/meetings/file",
                files={"file": ("first.wav", b"first-file", "audio/wav")},
            ),
            client.post("/api/meetings/url", json={"url": "https://media.test/fails"}),
        ]
        rejected = client.post("/api/meetings/url", json={"url": "ftp://media.test/nope"})
        accepted.extend(
            [
                client.post("/api/meetings/url", json={"url": "https://media.test/good-url"}),
                client.post(
                    "/api/meetings/file",
                    files={"file": ("last.mp3", b"last-file", "audio/mpeg")},
                ),
            ]
        )

        assert [response.status_code for response in accepted] == [201, 201, 201, 201]
        assert rejected.status_code == 400
        meeting_ids = [response.json()["id"] for response in accepted]
        await_terminal(client, meeting_ids[0], "completed")
        await_terminal(client, meeting_ids[1], "failed")
        await_terminal(client, meeting_ids[2], "completed")
        await_terminal(client, meeting_ids[3], "completed")
        owner_meetings = client.get("/api/meetings").json()["meetings"]
        assert {meeting["id"] for meeting in owner_meetings} == set(meeting_ids)

        session(client, sessions["sub-b"])
        assert client.get("/api/meetings").json() == {"meetings": []}
        assert all(client.get(f"/api/meetings/{meeting_id}").status_code == 404 for meeting_id in meeting_ids)
        session(client, None)
        assert client.post("/api/meetings/url", json={"url": "https://media.test/nope"}).status_code == 401
        assert all(client.get(f"/api/meetings/{meeting_id}").status_code == 401 for meeting_id in meeting_ids)

    assert acquirer.urls == ["https://media.test/fails", "https://media.test/good-url"]
    assert {data for _, data in runner.inputs} == {b"first-file", b"good-url", b"last-file"}
    assert list((tmp_path / "file-work").glob("**/*")) == []
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM meetings").fetchone() == (4,)
        assert "batch" not in {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        connection.close()


def test_accepted_url_continues_after_submitting_browser_leaves(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    runner = RecordingRunner()
    acquirer = ControlledAcquirer()
    app = make_app(database, runner, tmp_path / "file-work", acquirer)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        accepted = client.post(
            "/api/meetings/url", json={"url": "https://media.test/detached"}
        )
        assert accepted.status_code == 201
        meeting_id = accepted.json()["id"]
        assert acquirer.started.wait(timeout=2)

        session(client, None)
        acquirer.release.set()
        session(client, sessions["sub-a-second"])
        meeting = await_terminal(client, meeting_id, "completed")
        assert meeting["transcript"]["segments"][0]["text"] == "detached-url"

        session(client, sessions["sub-b"])
        assert client.get(f"/api/meetings/{meeting_id}").status_code == 404


def test_direct_http_acquisition_checks_declared_and_streamed_bytes(tmp_path: Path):
    def transport(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/declared":
            return httpx.Response(
                200,
                headers={"Content-Type": "audio/wav", "Content-Length": "9"},
                content=b"",
            )
        if path == "/streamed":
            return httpx.Response(
                200,
                headers={"Content-Type": "audio/wav"},
                content=b"123456789",
            )
        if path == "/html":
            return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"page")
        return httpx.Response(200, headers={"Content-Type": "audio/wav"}, content=b"media")

    async def exercise() -> None:
        acquirer = UrlMediaAcquirer(max_bytes=8, http_transport=httpx.MockTransport(transport))
        accepted = await acquirer.acquire("https://media.test/good", tmp_path / "good")
        assert accepted.read_bytes() == b"media"
        for path in ("declared", "streamed", "html"):
            with pytest.raises(UrlAcquisitionRejected):
                await acquirer.acquire(f"https://media.test/{path}", tmp_path / path)
            assert list((tmp_path / path).iterdir()) == []

    asyncio.run(exercise())


def test_direct_http_cancel_removes_partial_output(tmp_path: Path):
    class HangingStream(httpx.AsyncByteStream):
        def __init__(self, started: asyncio.Event) -> None:
            self._started = started

        async def __aiter__(self):
            yield b"partial"
            self._started.set()
            await asyncio.Event().wait()

    async def exercise() -> None:
        started = asyncio.Event()

        async def transport(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"Content-Type": "audio/wav"},
                stream=HangingStream(started),
            )

        output_root = tmp_path / "direct-cancel"
        acquirer = UrlMediaAcquirer(http_transport=httpx.MockTransport(transport))
        task = asyncio.create_task(acquirer.acquire("https://media.test/cancel", output_root))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert list(output_root.iterdir()) == []

    asyncio.run(exercise())


def test_redirect_bodies_are_closed_unread_and_locations_are_revalidated(tmp_path: Path):
    state = {"bytes_consumed": 0, "closed": False}

    class CountingRedirectStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            state["bytes_consumed"] += 9
            yield b"123456789"

        async def aclose(self) -> None:
            state["closed"] = True

    async def transport(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/redirect-body":
            return httpx.Response(
                302,
                headers={
                    "Content-Length": "9",
                    "Location": "https://media.test/final.wav",
                },
                stream=CountingRedirectStream(),
            )
        if request.url.path == "/bad-scheme":
            return httpx.Response(302, headers={"Location": "file:///tmp/media.wav"})
        if request.url.path.startswith("/loop/"):
            step = int(request.url.path.rsplit("/", 1)[1])
            return httpx.Response(302, headers={"Location": f"/loop/{step + 1}"})
        return httpx.Response(
            200,
            headers={"Content-Type": "audio/wav"},
            content=b"media",
        )

    async def exercise() -> None:
        acquirer = UrlMediaAcquirer(
            max_bytes=8,
            max_redirects=1,
            http_transport=httpx.MockTransport(transport),
        )
        output = await acquirer.acquire(
            "https://media.test/redirect-body", tmp_path / "redirect-body"
        )
        assert output.read_bytes() == b"media"
        assert state == {"bytes_consumed": 0, "closed": True}
        for path in ("bad-scheme", "loop/0"):
            with pytest.raises(UrlAcquisitionRejected):
                await acquirer.acquire(
                    f"https://media.test/{path}", tmp_path / path.replace("/", "-")
                )

    asyncio.run(exercise())


def test_url_acquisition_does_not_require_asyncio_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fake_yt_dlp = tmp_path / "compatible_yt_dlp.py"
    fake_yt_dlp.write_text("import sys\nsys.stdout.buffer.write(b'youtube')\n", encoding="utf-8")
    monkeypatch.delattr(asyncio, "timeout", raising=False)

    async def exercise() -> None:
        direct = UrlMediaAcquirer(
            http_transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    headers={"Content-Type": "audio/wav"},
                    content=b"media",
                )
            )
        )
        assert (await direct.acquire("https://media.test/audio", tmp_path / "direct")).exists()
        youtube = UrlMediaAcquirer(
            yt_dlp_command=(sys.executable, str(fake_yt_dlp)),
        )
        assert (
            await youtube.acquire("https://youtu.be/fixture", tmp_path / "youtube")
        ).exists()

    asyncio.run(exercise())


def test_youtube_uses_one_item_yt_dlp_without_false_exit_101(tmp_path: Path):
    fake_yt_dlp = tmp_path / "fake_yt_dlp.py"
    recorded_args = tmp_path / "arguments.txt"
    fake_yt_dlp.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        f"Path({str(recorded_args)!r}).write_text('\\n'.join(sys.argv[1:]), encoding='utf-8')\n"
        "if '--max-downloads' in sys.argv:\n"
        "    raise SystemExit(101)\n"
        "if sys.argv[sys.argv.index('-o') + 1] != '-':\n"
        "    raise SystemExit(102)\n"
        "sys.stdout.buffer.write(b'youtube')\n",
        encoding="utf-8",
    )
    acquirer = UrlMediaAcquirer(
        max_bytes=8,
        yt_dlp_command=(sys.executable, str(fake_yt_dlp)),
    )
    output = asyncio.run(
        acquirer.acquire("https://www.youtube.com/watch?v=fixture", tmp_path / "youtube")
    )
    arguments = recorded_args.read_text(encoding="utf-8").splitlines()
    assert output.read_bytes() == b"youtube"
    assert "--no-playlist" in arguments
    assert "--max-downloads" not in arguments
    assert arguments[arguments.index("-o") + 1] == "-"
    assert arguments[-1] == "https://www.youtube.com/watch?v=fixture"


def test_youtube_stream_bound_removes_partial_output(tmp_path: Path):
    fake_yt_dlp = tmp_path / "oversize_yt_dlp.py"
    fake_yt_dlp.write_text(
        "import sys, time\n"
        "sys.stdout.buffer.write(b'123456789')\n"
        "sys.stdout.buffer.flush()\n"
        "time.sleep(1)\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "youtube"
    acquirer = UrlMediaAcquirer(
        max_bytes=8,
        total_timeout_seconds=1,
        yt_dlp_command=(sys.executable, str(fake_yt_dlp)),
    )
    with pytest.raises(UrlAcquisitionRejected, match="size limit"):
        asyncio.run(acquirer.acquire("https://youtu.be/fixture", output_root))
    assert list(output_root.iterdir()) == []


def test_youtube_timeout_kills_descendant_process_group(tmp_path: Path):
    descendant_marker = tmp_path / "descendant-survived"
    fake_yt_dlp = tmp_path / "slow_yt_dlp.py"
    fake_yt_dlp.write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', "
        f"\"import time; from pathlib import Path; time.sleep(.3); Path({str(descendant_marker)!r}).write_text('alive')\""
        "])\n"
        "time.sleep(1)\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "youtube"
    acquirer = UrlMediaAcquirer(
        max_bytes=8,
        total_timeout_seconds=0.05,
        yt_dlp_command=(sys.executable, str(fake_yt_dlp)),
    )
    with pytest.raises(UrlAcquisitionRejected, match="timed out"):
        asyncio.run(acquirer.acquire("https://youtu.be/fixture", output_root))
    time.sleep(0.4)
    assert not descendant_marker.exists()
    assert list(output_root.iterdir()) == []


def test_youtube_cancel_kills_descendant_and_removes_partial(tmp_path: Path):
    descendant_marker = tmp_path / "descendant-survived"
    fake_yt_dlp = tmp_path / "cancel_yt_dlp.py"
    fake_yt_dlp.write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', "
        f"\"import time; from pathlib import Path; time.sleep(.3); Path({str(descendant_marker)!r}).write_text('alive')\""
        "])\n"
        "sys.stdout.buffer.write(b'partial')\n"
        "sys.stdout.buffer.flush()\n"
        "time.sleep(1)\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "youtube"
    acquirer = UrlMediaAcquirer(
        max_bytes=8,
        total_timeout_seconds=1,
        yt_dlp_command=(sys.executable, str(fake_yt_dlp)),
    )

    async def cancel() -> None:
        task = asyncio.create_task(
            acquirer.acquire("https://youtu.be/fixture", output_root)
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel())
    time.sleep(0.4)
    assert not descendant_marker.exists()
    assert list(output_root.iterdir()) == []


def test_repeated_cancel_waits_for_downloader_cleanup_quiescence(tmp_path: Path):
    pid_file = tmp_path / "downloader.pid"
    fake_yt_dlp = tmp_path / "shutdown_race_yt_dlp.py"
    fake_yt_dlp.write_text(
        "import os, signal, sys, time\n"
        "from pathlib import Path\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
        "sys.stdout.buffer.write(b'partial')\n"
        "sys.stdout.buffer.flush()\n"
        "time.sleep(10)\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "youtube"
    acquirer = UrlMediaAcquirer(
        total_timeout_seconds=10,
        yt_dlp_command=(sys.executable, str(fake_yt_dlp)),
    )

    async def cancel_twice() -> int:
        task = asyncio.create_task(
            acquirer.acquire("https://youtu.be/fixture", output_root)
        )
        while not pid_file.exists():
            await asyncio.sleep(0.005)
        task.cancel()
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
        pending_cleanup = [
            pending
            for pending in asyncio.all_tasks()
            if not pending.done()
            and "_stop_process_group"
            in getattr(pending.get_coro(), "__qualname__", "")
        ]
        assert pending_cleanup == []
        return int(pid_file.read_text())

    pid = asyncio.run(cancel_twice())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert list(output_root.iterdir()) == []
