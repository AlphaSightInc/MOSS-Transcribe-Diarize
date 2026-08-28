"""Terminal owner-private MP3 publication for Phase-2 Meetings."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_PHASE2_MEETING_AUDIO_ROOT = (
    Path.home() / ".local" / "share" / "moss-transcribe-diarize" / "meetings"
)


@dataclass(frozen=True, slots=True)
class PublishedMeetingAudio:
    path: Path
    relative_path: str
    byte_count: int
    duration_ms: int
    format: str = "mp3"
    sample_rate_hz: int = 16_000
    channels: int = 1
    bit_rate_bps: int = 48_000


class MeetingAudioCleanupError(RuntimeError):
    """The archive could not prove an artifact absent and durably seal that fact."""


class MeetingAudioArtifactSurvives(MeetingAudioCleanupError):
    """The canonical MP3 still exists after a discard attempt."""


class MeetingAudioArchive:
    """Prepare one transcription mix, then validate and publish its Meeting MP3."""

    def __init__(
        self,
        root: str | Path = DEFAULT_PHASE2_MEETING_AUDIO_ROOT,
        *,
        ffmpeg: str | None = None,
        ffprobe: str | None = None,
    ) -> None:
        self.root = Path(root).expanduser()
        self._ffmpeg = ffmpeg if ffmpeg is not None else shutil.which("ffmpeg")
        self._ffprobe = ffprobe if ffprobe is not None else shutil.which("ffprobe")

    def prepare_mix(
        self,
        source_path: str | Path,
        destination_path: str | Path,
    ) -> Path:
        """Decode the one transcription mix consumed by both inference and retention."""

        if not self._ffmpeg:
            raise RuntimeError("Meeting audio mixing is unavailable.")
        destination = Path(destination_path)
        destination.unlink(missing_ok=True)
        try:
            subprocess.run(
                [
                    self._ffmpeg,
                    "-nostdin",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(Path(source_path)),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "pcm_s16le",
                    "-f",
                    "wav",
                    str(destination),
                ],
                check=True,
                capture_output=True,
            )
            with wave.open(str(destination), "rb") as mixed:
                if (
                    mixed.getnchannels() != 1
                    or mixed.getframerate() != 16_000
                    or mixed.getsampwidth() != 2
                    or mixed.getnframes() <= 0
                ):
                    raise RuntimeError("Meeting transcription mix violates the PCM contract.")
            return destination
        except BaseException:
            destination.unlink(missing_ok=True)
            raise

    def publish(
        self,
        account_id: str,
        meeting_id: str,
        source_path: str | Path,
    ) -> PublishedMeetingAudio:
        if not self._ffmpeg or not self._ffprobe:
            raise RuntimeError("Meeting audio encoding is unavailable.")
        meeting_dir = self.root / account_id / meeting_id
        for directory in (self.root, meeting_dir.parent, meeting_dir):
            self._ensure_private_directory(directory)
        staged = meeting_dir / f".audio-{secrets.token_urlsafe(12)}.mp3"
        final = meeting_dir / "audio.mp3"
        replaced = False
        try:
            subprocess.run(
                [
                    self._ffmpeg,
                    "-nostdin",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(Path(source_path)),
                    "-map",
                    "0:a:0",
                    "-vn",
                    "-map_metadata",
                    "-1",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    "48k",
                    "-f",
                    "mp3",
                    str(staged),
                ],
                check=True,
                capture_output=True,
            )
            metadata = self._probe(staged)
            staged.chmod(0o600)
            with staged.open("rb") as output:
                os.fsync(output.fileno())
            os.replace(staged, final)
            replaced = True
            self._fsync_directory(meeting_dir)
            return PublishedMeetingAudio(
                path=final,
                relative_path=final.relative_to(self.root).as_posix(),
                byte_count=final.stat().st_size,
                duration_ms=metadata["duration_ms"],
            )
        except BaseException as cause:
            cleanup_target = final if replaced else staged
            try:
                self._discard_path(cleanup_target)
            except MeetingAudioCleanupError as cleanup_error:
                raise cleanup_error from cause
            raise

    def discard(self, publication: PublishedMeetingAudio) -> None:
        self._discard_path(publication.path)

    def discard_stored(
        self,
        account_id: str,
        meeting_id: str,
        relative_path: str,
    ) -> None:
        path = self._stored_path(account_id, meeting_id, relative_path)
        if path is None:
            raise MeetingAudioCleanupError("Meeting audio path is not canonical.")
        self._discard_path(path)

    def resolve(
        self,
        account_id: str,
        meeting_id: str,
        relative_path: str,
        byte_count: int,
    ) -> Path | None:
        expected = self._stored_path(account_id, meeting_id, relative_path)
        if expected is None:
            return None
        try:
            file_stat = expected.stat()
        except OSError:
            return None
        if not expected.is_file() or file_stat.st_size != byte_count:
            return None
        return expected

    def _stored_path(
        self,
        account_id: str,
        meeting_id: str,
        relative_path: str,
    ) -> Path | None:
        meeting_dir = self.root / account_id / meeting_id
        candidates = (meeting_dir / "audio.mp3", meeting_dir / "audio.partial.mp3")
        return next(
            (
                path
                for path in candidates
                if relative_path == path.relative_to(self.root).as_posix()
            ),
            None,
        )

    def _discard_path(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            if self._path_exists(path):
                raise MeetingAudioArtifactSurvives(
                    "Meeting audio artifact survives cleanup."
                ) from exc
            raise MeetingAudioCleanupError(
                "Meeting audio cleanup outcome is unknown."
            ) from exc
        if self._path_exists(path):
            raise MeetingAudioArtifactSurvives("Meeting audio artifact survives cleanup.")
        try:
            self._fsync_directory(path.parent)
        except OSError as exc:
            raise MeetingAudioCleanupError(
                "Meeting audio cleanup is not durably sealed."
            ) from exc
        if self._path_exists(path):
            raise MeetingAudioArtifactSurvives("Meeting audio artifact survives cleanup.")

    @staticmethod
    def _path_exists(path: Path) -> bool:
        try:
            path.stat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise MeetingAudioCleanupError(
                "Meeting audio artifact existence cannot be verified."
            ) from exc
        return True

    def _probe(self, path: Path) -> dict[str, int]:
        assert self._ffprobe is not None
        completed = subprocess.run(
            [
                self._ffprobe,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name,sample_rate,channels,bit_rate:format=format_name,duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload: dict[str, Any] = json.loads(completed.stdout)
        streams = payload.get("streams")
        if not isinstance(streams, list) or len(streams) != 1:
            raise RuntimeError("Meeting audio output has no single audio stream.")
        stream = streams[0]
        container = payload.get("format")
        if not isinstance(stream, dict) or not isinstance(container, dict):
            raise RuntimeError("Meeting audio metadata is unavailable.")
        if (
            stream.get("codec_name") != "mp3"
            or container.get("format_name") != "mp3"
            or int(stream.get("sample_rate") or 0) != 16_000
            or int(stream.get("channels") or 0) != 1
            or int(stream.get("bit_rate") or 0) != 48_000
        ):
            raise RuntimeError("Meeting audio output violates the MP3 contract.")
        duration_ms = round(float(container.get("duration") or 0) * 1000)
        if duration_ms <= 0:
            raise RuntimeError("Meeting audio output has no positive duration.")
        return {"duration_ms": duration_ms}

    def _ensure_private_directory(self, path: Path) -> None:
        created = False
        try:
            path.mkdir()
        except FileExistsError:
            if not path.is_dir():
                raise
        else:
            created = True
        path.chmod(0o700)
        if created:
            self._fsync_directory(path.parent)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
