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

from _browser_workspace_fixtures import seed_workspace

from fastapi.testclient import TestClient
import numpy as np
import pytest

from moss_transcribe_diarize.app.phase2 import (
    Phase2Store,
    SESSION_COOKIE,
    create_phase2_app,
)
from moss_transcribe_diarize.app.phase2_audio import (
    MeetingAudioArtifactSurvives,
    MeetingAudioArchive,
    PublishedMeetingAudio,
)
from moss_transcribe_diarize.app.phase2_admin import execute as execute_admin



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

    def prepare_mix(self, source: Path, destination: Path, *, notices=None) -> Path:
        destination.write_bytes(source.read_bytes())
        return destination

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

    def discard(self, publication: PublishedMeetingAudio) -> None:
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
        for subject, email in (("sub-a", "sub-a"), ("sub-b", "sub-b")):
            _, sessions[subject] = await seed_workspace(store, subject)
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
        # These tests assert a decoder transcript and publication lifecycle. Give
        # dispatch a signal; exact-zero files now correctly complete speechless.
        writer.writeframes(b"\1\0\1\0" * 48_000)
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


def dominant_frequency(path: Path, *, stream: str | None = None) -> int:
    command = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-ss",
        "1",
        "-t",
        "1",
        "-i",
        str(path),
    ]
    if stream is not None:
        command.extend(["-map", stream])
    command.extend(["-ac", "1", "-ar", "16000", "-f", "s16le", "-"])
    pcm = subprocess.run(command, check=True, capture_output=True).stdout
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
    frequencies = np.fft.rfftfreq(len(samples), 1 / 16_000)
    return round(float(frequencies[int(np.argmax(spectrum))]))


class WindowMixProbeRunner:
    model_path = "window-mix-probe"

    def __init__(self) -> None:
        self.input_name: str | None = None
        self.input_hz: int | None = None
        self.window_hz: int | None = None

    def transcribe(self, input_path: str | Path, **_: object):
        source = Path(input_path)
        window = source.parent / "observed-window.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                "0.000000",
                "-t",
                "150.000000",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "wav",
                str(window),
            ],
            check=True,
            capture_output=True,
        )
        self.input_name = source.name
        self.input_hz = dominant_frequency(source)
        self.window_hz = dominant_frequency(window)
        return SimpleNamespace(text="[0][S01]shared transcription mix[1]")


def make_app(
    database: Path,
    work_root: Path,
    audio_root: Path,
    *,
    archive: object | None = None,
    runner: object | None = None,
    control_socket: Path | None = None,
):
    return create_phase2_app(
        database_path=database,
        file_runner=runner or ImmediateRunner(),
        file_work_root=work_root,
        meeting_audio_root=audio_root,
        file_audio_archive=archive,
        control_socket_path=control_socket,
    )


def test_revoke_between_file_audio_and_finish_preserves_bytes_as_partial(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    work_root = tmp_path / "file-work"
    audio_root = tmp_path / "meetings"
    socket = Path("/tmp") / f"moss-i18-file-audio-{time.time_ns()}.sock"
    app = make_app(
        database,
        work_root,
        audio_root,
        control_socket=socket,
    )

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        finish_entered = threading.Event()
        release_finish = threading.Event()
        original_finish = app.state.phase2_store._finish_meeting

        async def held_completed_finish(*args, **kwargs):
            status = args[-1]
            if status == "completed":
                finish_entered.set()
                assert await asyncio.to_thread(release_finish.wait, 5)
            return await original_finish(*args, **kwargs)

        app.state.phase2_store._finish_meeting = held_completed_finish
        accepted = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", stereo_wav(), "audio/wav")},
        )
        assert accepted.status_code == 201
        meeting_id = accepted.json()["id"]
        assert finish_entered.wait(timeout=5)
        active = client.get(f"/api/meetings/{meeting_id}").json()
        assert active["status"] == "active"
        assert active["audio"]["state"] == "available"
        original_audio = dict(active["audio"])
        retained = audio_root / original_audio["relative_path"]
        original_bytes = retained.read_bytes()

        outcome: dict[str, object] = {}

        def revoke() -> None:
            outcome["result"] = asyncio.run(
                execute_admin(socket, "revoke", "sub-a")
            )

        worker = threading.Thread(target=revoke)
        worker.start()
        worker.join(timeout=5)
        release_finish.set()
        assert not worker.is_alive()
        assert outcome == {
            "result": {"account_id": "sub-a", "revoked": True}
        }

    connection = sqlite3.connect(database)
    try:
        row = connection.execute(
            """
            SELECT m.status, ma.state, ma.relative_path, ma.byte_count,
                   ma.duration_ms, ma.format, ma.sample_rate_hz, ma.channels,
                   ma.bit_rate_bps
            FROM meetings m JOIN meeting_audio ma
              ON ma.account_id = m.account_id AND ma.meeting_id = m.meeting_id
            WHERE m.meeting_id = ?
            """,
            (meeting_id,),
        ).fetchone()
    finally:
        connection.close()
    assert row == (
        "interrupted",
        "partial",
        original_audio["relative_path"],
        original_audio["byte_count"],
        original_audio["duration_ms"],
        original_audio["format"],
        original_audio["sample_rate_hz"],
        original_audio["channels"],
        original_audio["bit_rate_bps"],
    )
    assert retained.read_bytes() == original_bytes


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
        path = audio_root / audio["relative_path"]
        observed = probe_mp3(path)
        assert audio == {
            "state": "available",
            "relative_path": f"sub-a/{meeting_id}/audio.mp3",
            "byte_count": audio["byte_count"],
            "duration_ms": observed["duration_ms"],
            "format": "mp3",
            "sample_rate_hz": 16000,
            "channels": 1,
            "bit_rate_bps": 48000,
        }
        assert meeting["transcript"]["segments"][0]["text"] == "durable transcript"

        # FFprobe versions differ on whether MP3 container duration includes
        # encoder padding. The playback samples must still contain exactly the
        # one-second source; do not weaken this to an arbitrary time tolerance.
        decoded = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", "16000", "pipe:1"],
            check=True, capture_output=True,
        ).stdout
        assert len(decoded) == 16000 * 2
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
                assert await store.revoke_account("sub-a") is True
            finally:
                await store.close()

        asyncio.run(revoke())
        assert client.get(f"/api/meetings/{meeting_id}/audio/download").status_code == 401


def test_multi_stream_file_uses_one_mix_for_window_inference_and_retained_mp3(
    tmp_path: Path,
):
    fixture = tmp_path / "two-track-151s.mka"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=151:sample_rate=16000",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=151:sample_rate=16000",
            "-map",
            "0:a:0",
            "-map",
            "1:a:0",
            "-c:a",
            "pcm_s16le",
            "-disposition:a:0",
            "0",
            "-disposition:a:1",
            "default",
            str(fixture),
        ],
        check=True,
        capture_output=True,
    )
    assert dominant_frequency(fixture, stream="0:a:0") == 440
    assert dominant_frequency(fixture) == 880

    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    audio_root = tmp_path / "meetings"
    runner = WindowMixProbeRunner()
    app = make_app(
        database,
        tmp_path / "file-work",
        audio_root,
        runner=runner,
    )

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        accepted = client.post(
            "/api/meetings/file",
            files={"file": (fixture.name, fixture.read_bytes(), "audio/x-matroska")},
        )
        meeting_id = accepted.json()["id"]
        meeting = await_terminal(client, meeting_id, "completed")

    retained = audio_root / meeting["audio"]["relative_path"]
    assert runner.input_name == "transcription-mix.wav"
    assert runner.input_hz == 880
    assert runner.window_hz == 880
    assert dominant_frequency(retained) == 880
    assert meeting["transcript"]["segments"][0]["text"] == "shared transcription mix"
    assert list((tmp_path / "file-work").glob("**/*")) == []


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
        retained_input = (
            app.state.phase2_file_tasks.retained_root
            / "sub-a"
            / meeting_id
            / "input.wav"
        )
        assert retained_input.exists()
        assert list(work_root.glob("**/*")) == []

        archive.release.set()
        completed = await_terminal(client, meeting_id, "completed")
        assert completed["audio"]["state"] == "available"
        assert not retained_input.exists()
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


def test_available_metadata_commit_failure_removes_mp3_and_commits_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    work_root = tmp_path / "file-work"
    audio_root = tmp_path / "meetings"
    app = make_app(database, work_root, audio_root)

    with TestClient(app, base_url="https://moss.test") as client:
        real_commit = app.state.phase2_store._commit_meeting_audio
        available_attempts = 0

        async def reject_available_once(*args: object, **kwargs: object) -> None:
            nonlocal available_attempts
            audio = args[-1]
            if audio.state == "available" and available_attempts == 0:
                available_attempts += 1
                raise RuntimeError("forced available metadata failure")
            await real_commit(*args, **kwargs)

        monkeypatch.setattr(
            app.state.phase2_store,
            "_commit_meeting_audio",
            reject_available_once,
        )
        session(client, sessions["sub-a"])
        meeting_id = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", stereo_wav(), "audio/wav")},
        ).json()["id"]
        meeting = await_terminal(client, meeting_id, "completed")
        assert meeting["transcript"]["segments"][0]["text"] == "durable transcript"
        assert meeting["audio"] == {
            "state": "unavailable",
            "relative_path": None,
            "byte_count": None,
            "duration_ms": None,
            "format": None,
            "sample_rate_hz": None,
            "channels": None,
            "bit_rate_bps": None,
        }
        assert available_attempts == 1
        assert list(work_root.glob("**/*")) == []
        assert list(audio_root.glob("**/*.mp3")) == []

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT state, relative_path, byte_count FROM meeting_audio WHERE meeting_id = ?",
            (meeting_id,),
        ).fetchone() == ("unavailable", None, None)
    finally:
        connection.close()


@pytest.mark.parametrize("retry_available_succeeds", [True, False])
def test_metadata_and_removal_failure_never_marks_surviving_mp3_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    retry_available_succeeds: bool,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    work_root = tmp_path / "file-work"
    audio_root = tmp_path / "meetings"
    app = make_app(database, work_root, audio_root)

    with TestClient(app, base_url="https://moss.test") as client:
        archive = app.state.phase2_audio_archive

        def fail_removal(publication: PublishedMeetingAudio) -> None:
            assert publication.path.exists()
            raise MeetingAudioArtifactSurvives("forced surviving MP3")

        monkeypatch.setattr(archive, "discard", fail_removal)
        real_commit = app.state.phase2_store._commit_meeting_audio
        commit_attempts: list[str] = []

        async def fail_available_as_configured(*args: object, **kwargs: object) -> None:
            audio = args[-1]
            commit_attempts.append(audio.state)
            if audio.state == "available" and (
                len(commit_attempts) == 1 or not retry_available_succeeds
            ):
                raise RuntimeError("forced available metadata failure")
            await real_commit(*args, **kwargs)

        monkeypatch.setattr(
            app.state.phase2_store,
            "_commit_meeting_audio",
            fail_available_as_configured,
        )
        session(client, sessions["sub-a"])
        meeting_id = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", stereo_wav(), "audio/wav")},
        ).json()["id"]
        expected_status = "completed" if retry_available_succeeds else "failed"
        meeting = await_terminal(client, meeting_id, expected_status)

        assert meeting["transcript"]["segments"][0]["text"] == "durable transcript"
        assert commit_attempts == ["available", "available"]
        assert "unavailable" not in commit_attempts
        if retry_available_succeeds:
            assert meeting["audio"]["state"] == "available"
        else:
            assert meeting["audio"] is None
        assert len(list(audio_root.glob("**/*.mp3"))) == 1
        assert list(work_root.glob("**/*")) == []


def test_post_replace_failure_and_failed_discard_never_commits_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    work_root = tmp_path / "file-work"
    audio_root = tmp_path / "meetings"
    archive = MeetingAudioArchive(audio_root)
    app = make_app(database, work_root, audio_root, archive=archive)
    real_fsync = archive._fsync_directory
    fsync_calls = 0

    def fail_final_publish_fsync(path: Path) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 4:
            raise OSError("forced final publication fsync failure")
        real_fsync(path)

    real_unlink = Path.unlink

    def fail_canonical_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.name == "audio.mp3":
            raise OSError("forced canonical MP3 unlink failure")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(archive, "_fsync_directory", fail_final_publish_fsync)
    monkeypatch.setattr(Path, "unlink", fail_canonical_unlink)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        meeting_id = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", stereo_wav(), "audio/wav")},
        ).json()["id"]
        meeting = await_terminal(client, meeting_id, "failed")

    assert meeting["transcript"]["segments"][0]["text"] == "durable transcript"
    assert meeting["audio"] is None
    assert len(list(audio_root.glob("**/audio.mp3"))) == 1
    assert list(work_root.glob("**/*")) == []
    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM meeting_audio WHERE meeting_id = ?",
            (meeting_id,),
        ).fetchone() == (0,)
    finally:
        connection.close()


@pytest.mark.parametrize("discard_fails", [False, True])
def test_size_mismatch_reconciliation_never_marks_surviving_mp3_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    discard_fails: bool,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    work_root = tmp_path / "file-work"
    audio_root = tmp_path / "meetings"
    app = make_app(database, work_root, audio_root)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        meeting_id = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", stereo_wav(), "audio/wav")},
        ).json()["id"]
        meeting = await_terminal(client, meeting_id, "completed")
        path = audio_root / meeting["audio"]["relative_path"]
        path.write_bytes(path.read_bytes() + b"size mismatch")
        if discard_fails:
            real_unlink = Path.unlink

            def fail_canonical_unlink(
                candidate: Path,
                *args: object,
                **kwargs: object,
            ) -> None:
                if candidate == path:
                    raise OSError("forced mismatched MP3 unlink failure")
                real_unlink(candidate, *args, **kwargs)

            monkeypatch.setattr(Path, "unlink", fail_canonical_unlink)

        response = client.get(f"/api/meetings/{meeting_id}/audio/download")
        reconciled = client.get(f"/api/meetings/{meeting_id}").json()

    if discard_fails:
        assert response.status_code == 503
        assert reconciled["audio"]["state"] == "available"
        assert path.exists()
    else:
        assert response.status_code == 404
        assert reconciled["audio"]["state"] == "unavailable"
        assert not path.exists()


def test_unobservable_size_mismatch_returns_controlled_503_without_state_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    audio_root = tmp_path / "meetings"
    app = make_app(database, tmp_path / "file-work", audio_root)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        meeting_id = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", stereo_wav(), "audio/wav")},
        ).json()["id"]
        meeting = await_terminal(client, meeting_id, "completed")
        path = audio_root / meeting["audio"]["relative_path"]
        path.write_bytes(path.read_bytes() + b"size mismatch")
        real_unlink = Path.unlink
        real_stat = Path.stat

        def fail_canonical_unlink(
            candidate: Path,
            *args: object,
            **kwargs: object,
        ) -> None:
            if candidate == path:
                raise OSError("forced mismatched MP3 unlink failure")
            real_unlink(candidate, *args, **kwargs)

        def fail_canonical_stat(candidate: Path, *args: object, **kwargs: object):
            if candidate == path:
                raise OSError("forced existence uncertainty")
            return real_stat(candidate, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fail_canonical_unlink)
        monkeypatch.setattr(Path, "stat", fail_canonical_stat)
        response = client.get(f"/api/meetings/{meeting_id}/audio/download")
        reconciled = client.get(f"/api/meetings/{meeting_id}").json()

    monkeypatch.undo()
    assert response.status_code == 503
    assert reconciled["audio"]["state"] == "available"
    assert path.exists()


def test_new_archive_hierarchy_is_fsynced_before_available_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    work_root = tmp_path / "file-work"
    audio_root = tmp_path / "meetings"
    archive = MeetingAudioArchive(audio_root)
    app = make_app(database, work_root, audio_root, archive=archive)
    fsynced: list[Path] = []
    observed_at_available: list[Path] = []
    real_fsync = archive._fsync_directory

    def trace_fsync(path: Path) -> None:
        fsynced.append(path)
        real_fsync(path)

    monkeypatch.setattr(archive, "_fsync_directory", trace_fsync)
    with TestClient(app, base_url="https://moss.test") as client:
        real_commit = app.state.phase2_store._commit_meeting_audio

        async def trace_available(*args: object, **kwargs: object) -> None:
            audio = args[-1]
            if audio.state == "available":
                observed_at_available.extend(fsynced)
            await real_commit(*args, **kwargs)

        monkeypatch.setattr(
            app.state.phase2_store,
            "_commit_meeting_audio",
            trace_available,
        )
        session(client, sessions["sub-a"])
        meeting_id = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", stereo_wav(), "audio/wav")},
        ).json()["id"]
        await_terminal(client, meeting_id, "completed")

    assert observed_at_available == [
        audio_root.parent,
        audio_root,
        audio_root / "sub-a",
        audio_root / "sub-a" / meeting_id,
    ]


def test_post_replace_storage_failure_removes_uncommitted_mp3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "input.wav"
    source.write_bytes(stereo_wav())
    root = tmp_path / "meetings"
    archive = MeetingAudioArchive(root)
    real_fsync = archive._fsync_directory
    fsync_calls = 0

    def fail_final_fsync(path: Path) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 4:
            raise OSError("forced directory fsync failure")
        real_fsync(path)

    monkeypatch.setattr(archive, "_fsync_directory", fail_final_fsync)
    with pytest.raises(OSError, match="forced directory fsync failure"):
        archive.publish("sub-a", "meeting-a", source)
    assert list(root.glob("**/*.mp3")) == []
