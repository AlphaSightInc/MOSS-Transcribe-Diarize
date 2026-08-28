"""Terminal owner-private MP3 publication for Phase-2 Meetings."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
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


class MeetingAudioArchive:
    """Encode, validate, and atomically publish one Meeting MP3."""

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
        except BaseException:
            staged.unlink(missing_ok=True)
            if replaced:
                final.unlink(missing_ok=True)
            raise

    def remove(self, publication: PublishedMeetingAudio) -> None:
        publication.path.unlink(missing_ok=True)
        if publication.path.parent.exists():
            self._fsync_directory(publication.path.parent)

    def resolve(
        self,
        account_id: str,
        meeting_id: str,
        relative_path: str,
        byte_count: int,
    ) -> Path | None:
        meeting_dir = self.root / account_id / meeting_id
        candidates = (meeting_dir / "audio.mp3", meeting_dir / "audio.partial.mp3")
        expected = next(
            (
                path
                for path in candidates
                if relative_path == path.relative_to(self.root).as_posix()
            ),
            None,
        )
        if expected is None:
            return None
        try:
            file_stat = expected.stat()
        except OSError:
            return None
        if not expected.is_file() or file_stat.st_size != byte_count:
            return None
        return expected

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

    @staticmethod
    def _ensure_private_directory(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
