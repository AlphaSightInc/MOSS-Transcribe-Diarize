from __future__ import annotations

import asyncio
import collections
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest


FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
pytestmark = pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi is not installed")
DiskUsage = collections.namedtuple("usage", "total used free")


class NoopRunner:
    model_path = "fake-model"
    device_name = "cpu"
    dtype_name = "float32"

    def transcribe(self, audio_path, **kwargs):  # pragma: no cover - upload-only tests must not infer
        raise AssertionError(f"unexpected inference for {audio_path}")


class RecordingQueue:
    def __init__(self, manager):
        self.manager = manager
        self.puts: list[dict] = []

    def put(self, job_id: str) -> None:
        job = self.manager.get_job(job_id)
        job_json = Path(job.job_dir) / "job.json"
        self.puts.append(
            {
                "job_id": job_id,
                "source_sha256": job.source_sha256,
                "checkpoint_state": job.checkpoint_state,
                "input_exists": Path(job.input_path).is_file(),
                "job_json_exists": job_json.is_file(),
                "job_json": json.loads(job_json.read_text(encoding="utf-8")) if job_json.exists() else None,
            }
        )


def make_app(runs_dir: Path):
    from moss_transcribe_diarize.app.server import create_app

    app = create_app(model_path="fake-model", runs_dir=runs_dir, max_new_tokens=5)
    app.state.manager.model_runner = NoopRunner()
    app.state.manager._queue = RecordingQueue(app.state.manager)
    return app


def multipart_headers(content_length: str | None) -> list[tuple[bytes, bytes]]:
    headers = [(b"content-type", b"multipart/form-data; boundary=upload-boundary")]
    if content_length is not None:
        headers.append((b"content-length", content_length.encode("ascii")))
    return headers


async def call_asgi_without_body_receive(app, headers: list[tuple[bytes, bytes]]) -> tuple[int, bytes]:
    sent = []

    async def receive():
        raise AssertionError("request body was consumed before upload admission")

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/jobs",
        "raw_path": b"/api/jobs",
        "query_string": b"",
        "headers": headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    await app(scope, receive, send)

    status = next(message["status"] for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return status, body


@pytest.mark.parametrize("content_length", [None, "not-an-int", "-1"])
def test_upload_rejects_missing_malformed_and_negative_content_length_before_body(tmp_path, content_length):
    app = make_app(tmp_path)

    status, _body = asyncio.run(call_asgi_without_body_receive(app, multipart_headers(content_length)))

    assert status == 411
    assert app.state.manager.list_jobs() == []
    assert list(tmp_path.iterdir()) == []


def test_upload_rejects_insufficient_capacity_before_body_and_job_creation(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    content_length = 128
    required = 2 * content_length + 512 * 1024 * 1024
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: DiskUsage(required * 2, required + 1, required - 1))

    status, _body = asyncio.run(call_asgi_without_body_receive(app, multipart_headers(str(content_length))))

    assert status == 507
    assert app.state.manager.list_jobs() == []
    assert list(tmp_path.iterdir()) == []


def test_success_publishes_complete_metadata_before_exactly_one_enqueue(tmp_path):
    from fastapi.testclient import TestClient

    app = make_app(tmp_path)
    payload = b"large-upload-contract"
    response = TestClient(app).post(
        "/api/jobs",
        files={"file": ("sample.wav", payload, "audio/wav")},
    )

    assert response.status_code == 200
    job = response.json()
    queue = app.state.manager._queue
    assert [put["job_id"] for put in queue.puts] == [job["id"]]
    assert queue.puts[0]["input_exists"] is True
    assert queue.puts[0]["job_json_exists"] is True
    assert queue.puts[0]["source_sha256"] == hashlib.sha256(payload).hexdigest()
    assert queue.puts[0]["checkpoint_state"] == "ready"
    assert queue.puts[0]["job_json"]["source_sha256"] == hashlib.sha256(payload).hexdigest()


def test_upload_read_failure_removes_job_record_and_directory(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from starlette.datastructures import UploadFile

    app = make_app(tmp_path)

    async def fail_read(self, size=-1):
        raise TimeoutError("simulated receive idle timeout")

    monkeypatch.setattr(UploadFile, "read", fail_read)
    response = TestClient(app).post(
        "/api/jobs",
        files={"file": ("sample.wav", b"partial", "audio/wav")},
    )

    assert response.status_code == 408
    assert app.state.manager.list_jobs() == []
    assert app.state.manager._queue.puts == []
    assert list(tmp_path.iterdir()) == []
