from __future__ import annotations

import asyncio
import collections
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from moss_transcribe_diarize.app import phase2_file
from moss_transcribe_diarize.app.phase2 import (
    GoogleIdentity,
    Phase2Store,
    SESSION_COOKIE,
    create_phase2_app,
)
from moss_transcribe_diarize.app.phase2_file import (
    FileUploadRejected,
    FileUploadTimeout,
    admit_file_upload,
)


DiskUsage = collections.namedtuple("usage", "total used free")


class NeverOidc:
    async def begin(self, request):
        del request
        raise AssertionError("OIDC must not run")

    async def complete(self, request):
        del request
        raise AssertionError("OIDC must not run")


class NeverRunner:
    model_path = "upload-admission-test"

    def transcribe(self, input_path, **kwargs):
        del input_path, kwargs
        raise AssertionError("refused upload must not start inference")


async def _provision(database: Path) -> str:
    store = await Phase2Store.open(database)
    try:
        await store.allow_email("owner@example.com")
        admitted = await store.admit(
            GoogleIdentity("upload-owner", "owner@example.com", "Owner")
        )
        assert admitted is not None
        return admitted[1]
    finally:
        await store.close()


class RequestProbe:
    def __init__(self, content_length: str | None, receive=None):
        self.headers = {} if content_length is None else {"content-length": content_length}
        self.receive_calls = 0

        async def default_receive():
            self.receive_calls += 1
            return {"type": "http.request", "body": b"", "more_body": False}

        self._receive = receive or default_receive


@pytest.mark.parametrize("content_length", [None, "not-an-int", "-1"])
def test_account_upload_refuses_unbounded_body_before_receive_or_storage(
    tmp_path: Path,
    content_length: str | None,
):
    request = RequestProbe(content_length)

    with pytest.raises(FileUploadRejected) as refusal:
        admit_file_upload(request, tmp_path / "file-work")

    assert refusal.value.status_code == 411
    assert request.receive_calls == 0
    assert not (tmp_path / "file-work").exists()


def test_account_upload_refuses_insufficient_capacity_before_receive(
    tmp_path: Path,
    monkeypatch,
):
    request = RequestProbe("128")
    required = 2 * 128 + 512 * 1024 * 1024
    monkeypatch.setattr(
        phase2_file.shutil,
        "disk_usage",
        lambda _path: DiskUsage(required * 2, required + 1, required - 1),
    )

    with pytest.raises(FileUploadRejected) as refusal:
        admit_file_upload(request, tmp_path / "file-work")

    assert refusal.value.status_code == 507
    assert request.receive_calls == 0


def test_account_upload_receive_idle_timeout_is_typed_on_python310_and_later(
    tmp_path: Path,
    monkeypatch,
):
    async def stalled_receive():
        await asyncio.sleep(1)
        return {"type": "http.request", "body": b"", "more_body": False}

    request = RequestProbe("128", stalled_receive)
    monkeypatch.setattr(phase2_file, "UPLOAD_RECEIVE_IDLE_TIMEOUT_SECONDS", 0.01)
    admit_file_upload(request, tmp_path / "file-work")

    with pytest.raises(FileUploadTimeout):
        asyncio.run(request._receive())


def test_account_upload_file_read_idle_timeout_is_typed(monkeypatch):
    class Upload:
        async def read(self, _size):
            await asyncio.sleep(1)
            return b""

    monkeypatch.setattr(phase2_file, "UPLOAD_RECEIVE_IDLE_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(FileUploadTimeout):
        asyncio.run(phase2_file._read_upload_chunk(Upload()))


def test_account_file_route_maps_prebody_refusal_without_meeting_or_stage(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    session_id = asyncio.run(_provision(database))
    work_root = tmp_path / "file-work"
    app = create_phase2_app(
        database_path=database,
        oidc=NeverOidc(),
        oauth_cookie_secret="upload-admission-secret",
        file_runner=NeverRunner(),
        file_work_root=work_root,
    )

    with TestClient(app, base_url="https://moss.test") as client:
        client.cookies.set(SESSION_COOKIE, session_id, domain="moss.test", path="/")
        response = client.post(
            "/api/meetings/file",
            content=b"body that must not be parsed",
            headers={"Content-Type": "multipart/form-data", "Content-Length": "invalid"},
        )

        assert response.status_code == 411
        assert client.get("/api/meetings").json() == {"meetings": []}
    assert not work_root.exists()
