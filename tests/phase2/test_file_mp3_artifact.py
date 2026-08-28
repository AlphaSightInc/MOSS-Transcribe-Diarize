from __future__ import annotations

import asyncio
import io
import json
import sqlite3
import stat
import subprocess
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from moss_transcribe_diarize.app.phase2 import (
    GoogleIdentity,
    Phase2Store,
    SESSION_COOKIE,
    create_phase2_app,
)
from moss_transcribe_diarize.app.phase2_audio import (
    MeetingAudioArchive,
    PublishedMeetingAudio,
)


class NeverOidc:
    async def begin(self, request):  # pragma: no cover - stored sessions only.
        raise AssertionError("OIDC must not run")

    async def complete(self, request):  # pragma: no cover - stored sessions only.
        raise AssertionError("OIDC must not run")


class ImmediateRunner:
    model_path = "file-mp3-fixture"

    def __init__(self) -> None:
        self.inputs: list[bytes] = []

    def transcribe(self, input_path: str | Path, **_: object):
        self.inputs.append(Path(input_path).read_bytes())
        return SimpleNamespace(text="[0][S01]durable transcript[1]")


class BlockingArchive:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.started = threading.Event()
        self.release = threading.Event()

    def publish(self, account_id: str, meeting_id: str, _: Path) -> PublishedMeetingAudio:
        self.started.set()
        assert self.release.wait(timeout=5), "test did not release audio publication"
        path = self.root / account_id / meeting_id / "audio.mp3"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"published")
        return PublishedMeetingAudio(
            path=path,
            relative_path=path.relative_to(self.root).as_posix(),
            byte_count=path.stat().st_size,
            duration_ms=1000,
        )

    def remove(self, publication: PublishedMeetingAudio) -> None:
        publication.path.unlink(missing_ok=True)

    def resolve(
        self,
        account_id: str,
        meeting_id: str,
        relative_path: str,
        byte_count: int,
    ) -> Path | None:
        path = self.root / account_id / meeting_id / "audio.mp3"
        return path if path.exists() and path.stat().st_size == byte_count else None


async def provision(database: Path) -> dict[str, str]:
    store = await Phase2Store.open(database)
    try:
        sessions: dict[str, str] = {}
        for subject, email in (("sub-a", "a@example.com"), ("sub-b", "b@example.com")):
            await store.allow_email(email)
            _, sessions[subject] = await store.admit(GoogleIdentity(subject, email, subject))
        return sessions
    finally:
        await store.close()


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


def stereo_wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(48_000)
        writer.writeframes(b"\0\0\0\0" * 48_000)
    return output.getvalue()


def probe_mp3(path: Path) -> dict[str, object]:
    metadata = json.loads(
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name,sample_rate,channels,bit_rate:format=format_name,duration,size",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    packets = json.loads(
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_packets",
                "-show_entries",
                "packet=size,duration_time",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    stream = metadata["streams"][0]
    container = metadata["format"]
    return {
        "codec": stream["codec_name"],
        "format": container["format_name"],
        "sample_rate_hz": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
        "bit_rate_bps": int(stream["bit_rate"]),
        "duration_ms": round(float(container["duration"]) * 1000),
        "byte_count": int(container["size"]),
        "packet_bitrates_bps": sorted(
            {
                round(int(packet["size"]) * 8 / float(packet["duration_time"]))
                for packet in packets["packets"]
                if float(packet.get("duration_time") or 0) > 0
            }
        ),
    }


def make_app(
    database: Path,
    work_root: Path,
    audio_root: Path,
    *,
    archive: object | None = None,
):
    return create_phase2_app(
        database_path=database,
        oidc=NeverOidc(),
        oauth_cookie_secret="test-cookie-secret",
        file_runner=ImmediateRunner(),
        file_work_root=work_root,
        meeting_audio_root=audio_root,
        file_audio_archive=archive,
    )


def test_file_completion_publishes_private_exact_mp3_and_owner_whole_download(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    work_root = tmp_path / "file-work"
    audio_root = tmp_path / "meetings"
    app = make_app(database, work_root, audio_root)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        accepted = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", stereo_wav(), "audio/wav")},
        )
        assert accepted.status_code == 201
        meeting_id = accepted.json()["id"]
        meeting = await_terminal(client, meeting_id, "completed")
        audio = meeting["audio"]
        assert audio == {
            "state": "available",
            "relative_path": f"sub-a/{meeting_id}/audio.mp3",
            "byte_count": audio["byte_count"],
            "duration_ms": 1000,
            "format": "mp3",
            "sample_rate_hz": 16000,
            "channels": 1,
            "bit_rate_bps": 48000,
        }
        assert meeting["transcript"]["segments"][0]["text"] == "durable transcript"

        path = audio_root / audio["relative_path"]
        encoded = path.read_bytes()
        assert probe_mp3(path) == {
            "codec": "mp3",
            "format": "mp3",
            "sample_rate_hz": 16000,
            "channels": 1,
            "bit_rate_bps": 48000,
            "duration_ms": audio["duration_ms"],
            "byte_count": audio["byte_count"],
            "packet_bitrates_bps": [48000],
        }
        assert stat.S_IMODE(audio_root.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.parent.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert [item for item in tmp_path.rglob("*") if item.is_file() and item.suffix == ".mp3"] == [path]
        assert list(work_root.glob("**/*")) == []
        assert 'data-audio-download' in client.get("/").text

        download = client.get(
            f"/api/meetings/{meeting_id}/audio/download",
            headers={"Range": "bytes=0-3"},
        )
        assert download.status_code == 200
        assert download.content == encoded
        assert download.headers["content-type"] == "audio/mpeg"
        assert download.headers["content-length"] == str(len(encoded))
        assert download.headers["content-disposition"] == (
            f'attachment; filename="meeting-{meeting_id}.mp3"'
        )
        assert "accept-ranges" not in download.headers

        session(client, sessions["sub-b"])
        assert client.get(f"/api/meetings/{meeting_id}/audio/download").status_code == 404
        session(client, None)
        assert client.get(f"/api/meetings/{meeting_id}/audio/download").status_code == 401

    restarted = make_app(database, tmp_path / "restart" / "file-work", audio_root)
    with TestClient(restarted, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        persisted = client.get(f"/api/meetings/{meeting_id}/audio/download")
        assert persisted.status_code == 200
        assert persisted.content == encoded

        path.unlink()
        assert client.get(f"/api/meetings/{meeting_id}/audio/download").status_code == 404
        unavailable = client.get(f"/api/meetings/{meeting_id}").json()["audio"]
        assert unavailable == {
            "state": "unavailable",
            "relative_path": None,
            "byte_count": None,
            "duration_ms": None,
            "format": None,
            "sample_rate_hz": None,
            "channels": None,
            "bit_rate_bps": None,
        }

        async def revoke() -> None:
            store = await Phase2Store.open(database)
            try:
                assert await store.revoke_email("a@example.com") is True
            finally:
                await store.close()

        asyncio.run(revoke())
        assert client.get(f"/api/meetings/{meeting_id}/audio/download").status_code == 401


def test_meeting_stays_active_until_audio_metadata_is_durable(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    work_root = tmp_path / "file-work"
    archive = BlockingArchive(tmp_path / "meetings")
    app = make_app(database, work_root, archive.root, archive=archive)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        meeting_id = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", stereo_wav(), "audio/wav")},
        ).json()["id"]
        assert archive.started.wait(timeout=2)
        active = client.get(f"/api/meetings/{meeting_id}").json()
        assert active["status"] == "active"
        assert active["transcript"]["segments"][0]["text"] == "durable transcript"
        assert active["audio"] is None
        assert next(work_root.glob("*/input.wav")).exists()

        archive.release.set()
        completed = await_terminal(client, meeting_id, "completed")
        assert completed["audio"]["state"] == "available"
        assert list(work_root.glob("**/*")) == []


@pytest.mark.parametrize("failure", ["encoder", "storage"])
def test_audio_publication_failure_is_unavailable_and_preserves_transcript(
    tmp_path: Path,
    failure: str,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    work_root = tmp_path / "file-work"
    audio_root = tmp_path / "meetings"
    archive = None
    if failure == "encoder":
        archive = MeetingAudioArchive(audio_root, ffmpeg="", ffprobe="")
    else:
        audio_root.write_bytes(b"storage path is not a directory")
    app = make_app(database, work_root, audio_root, archive=archive)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        meeting_id = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", stereo_wav(), "audio/wav")},
        ).json()["id"]
        meeting = await_terminal(client, meeting_id, "completed")
        assert meeting["transcript"]["segments"][0]["text"] == "durable transcript"
        assert meeting["audio"]["state"] == "unavailable"
        assert meeting["audio"]["relative_path"] is None
        assert list(work_root.glob("**/*")) == []
        assert client.get(f"/api/meetings/{meeting_id}/audio/download").status_code == 404
        assert "Audio unavailable" in client.get("/").text

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            """
            SELECT state, relative_path, byte_count, duration_ms, format,
                   sample_rate_hz, channels, bit_rate_bps
            FROM meeting_audio WHERE meeting_id = ?
            """,
            (meeting_id,),
        ).fetchone() == ("unavailable", None, None, None, None, None, None, None)
    finally:
        connection.close()


def test_metadata_commit_failure_removes_published_mp3_but_keeps_transcript(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    work_root = tmp_path / "file-work"
    audio_root = tmp_path / "meetings"
    app = make_app(database, work_root, audio_root)

    with TestClient(app, base_url="https://moss.test") as client:
        async def reject_metadata(*_: object, **__: object) -> None:
            raise RuntimeError("forced metadata failure")

        monkeypatch.setattr(app.state.phase2_store, "_commit_meeting_audio", reject_metadata)
        session(client, sessions["sub-a"])
        meeting_id = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", stereo_wav(), "audio/wav")},
        ).json()["id"]
        meeting = await_terminal(client, meeting_id, "failed")
        assert meeting["transcript"]["segments"][0]["text"] == "durable transcript"
        assert meeting["audio"] is None
        assert list(work_root.glob("**/*")) == []
        assert list(audio_root.glob("**/*.mp3")) == []

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM meeting_audio WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == (0,)
    finally:
        connection.close()


def test_post_replace_storage_failure_removes_uncommitted_mp3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "input.wav"
    source.write_bytes(stereo_wav())
    root = tmp_path / "meetings"
    archive = MeetingAudioArchive(root)

    def fail_fsync(_: Path) -> None:
        raise OSError("forced directory fsync failure")

    monkeypatch.setattr(archive, "_fsync_directory", fail_fsync)
    with pytest.raises(OSError, match="forced directory fsync failure"):
        archive.publish("sub-a", "meeting-a", source)
    assert list(root.glob("**/*.mp3")) == []
