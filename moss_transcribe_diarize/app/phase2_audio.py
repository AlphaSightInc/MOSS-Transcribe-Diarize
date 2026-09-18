"""Terminal owner-private MP3 publication for Phase-2 Meetings."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
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


@dataclass(frozen=True, slots=True)
class LiveMeetingAudioPrefix:
    """The complete PCM16 samples recoverable from one fixed Live stage path."""

    path: Path
    sample_count: int
    complete: bool


class _LiveMeetingAudioStage:
    """One bounded mixed-only PCM stage at the existing Live tape-recorder seam."""

    def __init__(self, path: Path, max_bytes: int, *, create: bool = True) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self.degraded = not create
        self._lock = threading.RLock()
        self._fd: int | None = None
        if not create:
            return
        try:
            self._fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.fchmod(self._fd, 0o600)
            os.fsync(self._fd)
        except BaseException:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            raise

    def append_lane_frame(self, _: Any) -> None:
        """Raw microphone and system lanes are intentionally not retained."""

    def append_mixed(
        self,
        *,
        pcm: bytes,
        start_timestamp_ns: int,
        sample_count: int,
        sample_rate: int,
    ) -> None:
        del start_timestamp_ns
        with self._lock:
            if self.degraded or self._fd is None:
                return
            if (
                sample_rate != 16_000
                or sample_count <= 0
                or len(pcm) != sample_count * 2
            ):
                self.degraded = True
                return
            try:
                if os.fstat(self._fd).st_size + len(pcm) > self.max_bytes:
                    self.degraded = True
                    return
                remaining = memoryview(pcm)
                while remaining:
                    written = os.write(self._fd, remaining)
                    remaining = remaining[written:]
                os.fsync(self._fd)
            except OSError:
                self.degraded = True

    def close(self) -> None:
        with self._lock:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None


class LiveMeetingAudioStages:
    """Owner-derived Live mixed-PCM staging; durable MP3 truth stays in the archive."""

    def __init__(self, archive: "MeetingAudioArchive", *, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise ValueError("Live Meeting audio staging requires a positive byte bound.")
        self.archive = archive
        self.max_bytes = max_bytes
        self._stages: dict[str, _LiveMeetingAudioStage] = {}
        self._owners: dict[str, str] = {}
        self._sealed: dict[str, bool] = {}
        self._lock = threading.RLock()

    def reserve(self, account_id: str, meeting_id: str) -> None:
        with self._lock:
            if meeting_id in self._owners:
                raise ValueError("Live Meeting audio stage already exists.")
            path = self.path(account_id, meeting_id)
            stage: _LiveMeetingAudioStage | None = None
            try:
                for directory in (self.archive.root, path.parent.parent, path.parent):
                    self.archive._ensure_private_directory(directory)
                stage = _LiveMeetingAudioStage(path, self.max_bytes)
                self.archive._fsync_directory(path.parent)
            except OSError as cause:
                if stage is not None:
                    stage.close()
                try:
                    if self.archive._path_exists(path.parent):
                        self.archive._discard_path(path)
                except MeetingAudioCleanupError as cleanup_error:
                    raise cleanup_error from cause
                stage = _LiveMeetingAudioStage(path, self.max_bytes, create=False)
            self._owners[meeting_id] = account_id
            self._stages[meeting_id] = stage

    def create(self, meeting_id: str) -> _LiveMeetingAudioStage:
        with self._lock:
            try:
                return self._stages[meeting_id]
            except KeyError as exc:
                raise KeyError(meeting_id) from exc

    def get(self, meeting_id: str) -> _LiveMeetingAudioStage | None:
        with self._lock:
            return self._stages.get(meeting_id)

    def release(self, meeting_id: str) -> _LiveMeetingAudioStage | None:
        with self._lock:
            stage = self._stages.pop(meeting_id, None)
        if stage is not None:
            stage.close()
            with self._lock:
                self._sealed[meeting_id] = stage.degraded
        return stage

    def reap(self, *, active_session_ids: Any = ()) -> tuple[str, ...]:
        del active_session_ids
        # Startup recovery is driven only by canonical active Live Meeting rows.
        return ()

    def prefix(
        self,
        account_id: str,
        meeting_id: str,
        *,
        expected_samples: int | None,
    ) -> LiveMeetingAudioPrefix | None:
        self.release(meeting_id)
        path = self.path(account_id, meeting_id)
        try:
            byte_count = path.stat().st_size
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise MeetingAudioCleanupError(
                "Live Meeting stage existence cannot be verified."
            ) from exc
        usable_bytes = byte_count - (byte_count % 2)
        if usable_bytes != byte_count:
            try:
                with path.open("r+b") as stage:
                    stage.truncate(usable_bytes)
                    stage.flush()
                    os.fsync(stage.fileno())
            except OSError as exc:
                raise MeetingAudioCleanupError(
                    "Live Meeting torn stage could not be durably truncated."
                ) from exc
        if usable_bytes <= 0:
            return None
        with self._lock:
            degraded = self._sealed.get(meeting_id, expected_samples is None)
        return LiveMeetingAudioPrefix(
            path=path,
            sample_count=usable_bytes // 2,
            complete=(
                expected_samples is not None
                and usable_bytes == expected_samples * 2
                and not degraded
            ),
        )

    def discard(self, account_id: str, meeting_id: str) -> None:
        self.release(meeting_id)
        path = self.path(account_id, meeting_id)
        if self.archive._path_exists(path.parent):
            self.archive._discard_path(path)
        with self._lock:
            self._owners.pop(meeting_id, None)
            self._sealed.pop(meeting_id, None)

    def path(self, account_id: str, meeting_id: str) -> Path:
        return self.archive.root / account_id / meeting_id / ".live-mix.pcm"


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
        *,
        notices: list[str] | None = None,
    ) -> Path:
        """Decode the one transcription mix consumed by both inference and retention."""

        if not self._ffmpeg:
            raise RuntimeError("Meeting audio mixing is unavailable.")
        destination = Path(destination_path)
        destination.unlink(missing_ok=True)
        try:
            completed = subprocess.run(
                [
                    self._ffmpeg,
                    "-nostdin",
                    "-v",
                    "warning",
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
            # FFmpeg can recover a prefix and exit successfully for a truncated MP3.
            # Retain only the measured condition, never raw stderr or source paths.
            if notices is not None and b"filesize and duration do not match" in completed.stderr.lower():
                notices.append(
                    "The media decoder reported incomplete audio. "
                    "This transcript may cover only part of the recording."
                )
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
        return self._publish(
            account_id,
            meeting_id,
            Path(source_path),
            partial=False,
            raw_pcm=False,
        )

    def publish_live_prefix(
        self,
        account_id: str,
        meeting_id: str,
        source_path: str | Path,
        *,
        partial: bool,
    ) -> PublishedMeetingAudio:
        return self._publish(
            account_id,
            meeting_id,
            Path(source_path),
            partial=partial,
            raw_pcm=True,
        )

    def _publish(
        self,
        account_id: str,
        meeting_id: str,
        source_path: Path,
        *,
        partial: bool,
        raw_pcm: bool,
    ) -> PublishedMeetingAudio:
        if not self._ffmpeg or not self._ffprobe:
            raise RuntimeError("Meeting audio encoding is unavailable.")
        meeting_dir = self.root / account_id / meeting_id
        for directory in (self.root, meeting_dir.parent, meeting_dir):
            self._ensure_private_directory(directory)
        # Publication is serialized per Meeting; one fixed stage makes crash cleanup
        # derivable from the canonical owner path instead of a filesystem search.
        staged = meeting_dir / ".audio.staged.mp3"
        final = meeting_dir / ("audio.partial.mp3" if partial else "audio.mp3")
        replaced = False
        try:
            command = [
                self._ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-y",
            ]
            if raw_pcm:
                command.extend(["-f", "s16le", "-ar", "16000", "-ac", "1"])
            command.extend(
                [
                    "-i",
                    str(source_path),
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
                ]
            )
            subprocess.run(
                command,
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

    def discard_unrecorded(self, account_id: str, meeting_id: str) -> None:
        """Remove every canonical MP3 path when no metadata grants retained truth."""

        meeting_dir = self.root / account_id / meeting_id
        if not self._path_exists(meeting_dir):
            # A Meeting that crashed between its SQLite row and stage reservation has no
            # directory entry capable of containing either canonical artifact.
            return
        for path in (
            meeting_dir / ".audio.staged.mp3",
            meeting_dir / "audio.mp3",
            meeting_dir / "audio.partial.mp3",
        ):
            self._discard_path(path)

    def discard_staged(self, account_id: str, meeting_id: str) -> None:
        """Remove the sole deterministic pre-publication artifact after interruption."""

        meeting_dir = self.root / account_id / meeting_id
        if self._path_exists(meeting_dir):
            self._discard_path(meeting_dir / ".audio.staged.mp3")

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
