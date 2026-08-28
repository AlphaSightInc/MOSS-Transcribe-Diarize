"""Owner-bound File-Meeting inference without a durable job identity."""

from __future__ import annotations

import asyncio
import logging
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moss_transcribe_diarize.subtitle import subtitle_segments_from_transcript

from .phase2 import AccountRevoked
from .phase2_url import validate_http_url


DEFAULT_PHASE2_FILE_WORK_ROOT = (
    Path.home() / ".local" / "share" / "moss-transcribe-diarize" / "file-work"
)
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _OwnedFileTask:
    handle: Any
    task: asyncio.Task[None]


class FileMeetingTasks:
    """The minimal process-owned lifetime for owner-carrying File work.

    The strong-reference set is deliberately not a scheduler or resource registry. Each task
    already owns a MeetingHandle, and the handle is the only route back to persistence.
    """

    def __init__(
        self,
        runner: Any,
        work_root: str | Path,
        *,
        prompt: str | None = None,
        max_length: int | None = None,
        max_new_tokens: int | None = None,
        decoding: str | None = None,
        temperature: float | None = None,
        url_acquirer: Any | None = None,
        audio_archive: Any | None = None,
    ):
        self._runner = runner
        self._work_root = Path(work_root).expanduser()
        if self._work_root.name != "file-work":
            raise ValueError("File work root must be a dedicated directory named file-work.")
        self._prompt = prompt
        self._max_length = max_length
        self._max_new_tokens = max_new_tokens
        self._decoding = decoding
        self._temperature = temperature if decoding == "sample" else None
        self._url_acquirer = url_acquirer
        self._audio_archive = audio_archive
        self._tasks: dict[str, _OwnedFileTask] = {}
        self._fenced_owner_keys: set[tuple[str, int]] = set()

    def clear_transient_work(self) -> None:
        """Remove only children of the dedicated, non-durable File work root."""

        if not self._work_root.exists():
            return
        if not self._work_root.is_dir():
            LOGGER.error("Transient File work cleanup failed.")
            raise RuntimeError("Transient File work cleanup failed.")
        try:
            children = tuple(self._work_root.iterdir())
        except Exception:
            LOGGER.error("Transient File work cleanup failed.")
            raise RuntimeError("Transient File work cleanup failed.") from None
        for child in children:
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except Exception:
                LOGGER.error("Transient File work cleanup failed.")
                raise RuntimeError("Transient File work cleanup failed.") from None

    async def accept(self, workspace: Any, upload: Any) -> Any:
        """Store a complete request body, then create exactly one File Meeting and start work."""

        filename = upload.filename if isinstance(upload.filename, str) else "input.media"
        suffix = Path(filename).suffix or ".media"
        self._work_root.mkdir(parents=True, exist_ok=True)
        staging_dir = self._work_root / secrets.token_urlsafe(18)
        input_path = staging_dir / f"input{suffix}"
        staging_dir.mkdir(parents=True, exist_ok=False)
        try:
            with input_path.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    output.write(chunk)
            handle = await workspace.create_meeting("file")
        except BaseException:
            try:
                self._remove_work_dir(staging_dir)
            except Exception:
                LOGGER.error("File Meeting upload cleanup failed.")
                raise
            raise

        started = asyncio.Event()
        task = asyncio.create_task(self._run(handle, input_path, started))
        self._register(handle, task)
        await started.wait()
        return handle

    async def accept_url(self, workspace: Any, source_url: str) -> Any:
        """Create one File Meeting and retain its bounded URL acquisition server-side."""

        source_url = validate_http_url(source_url)
        if self._url_acquirer is None:
            raise RuntimeError("URL acquisition is unavailable.")
        self._work_root.mkdir(parents=True, exist_ok=True)
        staging_dir = self._work_root / secrets.token_urlsafe(18)
        staging_dir.mkdir(parents=True, exist_ok=False)
        try:
            handle = await workspace.create_meeting("file")
        except BaseException:
            self._remove_work_dir(staging_dir)
            raise

        started = asyncio.Event()
        task = asyncio.create_task(
            self._acquire_and_run(handle, source_url, staging_dir, started)
        )
        self._register(handle, task)
        await started.wait()
        return handle

    async def stop(self) -> None:
        """Fence coroutine commits before the owning SQLite connection closes."""

        tasks = tuple(entry.task for entry in self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def interrupt_account(self, owner_key: tuple[str, int]) -> tuple[str, ...]:
        """Quiesce this Account generation, then durably interrupt its active File rows."""

        entries = self.fence_account(owner_key)
        return await self.settle_fenced(entries)

    def fence_account(self, owner_key: tuple[str, int]) -> tuple[_OwnedFileTask, ...]:
        """Reject every later result before waiting for any one task."""

        self._fenced_owner_keys.add(owner_key)
        entries = tuple(
            entry
            for entry in self._tasks.values()
            if entry.handle.owner_key == owner_key
        )
        for entry in entries:
            entry.task.cancel()
        return entries

    async def settle_fenced(
        self,
        entries: tuple[_OwnedFileTask, ...],
    ) -> tuple[str, ...]:
        if entries:
            results = await asyncio.gather(
                *(entry.task for entry in entries),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, Exception) and not isinstance(
                    result, asyncio.CancelledError
                ):
                    raise RuntimeError("File Meeting could not be quiesced.") from result
        interrupted: list[str] = []
        for entry in entries:
            try:
                snapshot = await entry.handle.snapshot()
            except AccountRevoked:
                continue
            if snapshot.status != "active":
                continue
            if snapshot.audio is None:
                await entry.handle.record_audio_unavailable()
            await entry.handle.finish("interrupted")
            interrupted.append(entry.handle.meeting_id)
        return tuple(interrupted)

    def _register(self, handle: Any, task: asyncio.Task[None]) -> None:
        meeting_id = handle.meeting_id
        self._tasks[meeting_id] = _OwnedFileTask(handle=handle, task=task)
        task.add_done_callback(lambda completed: self._task_done(meeting_id, completed))

    def _task_done(self, meeting_id: str, task: asyncio.Task[None]) -> None:
        entry = self._tasks.get(meeting_id)
        if entry is not None and entry.task is task:
            self._tasks.pop(meeting_id, None)
        if task.cancelled():
            return
        if task.exception() is not None:
            LOGGER.error("File Meeting background task failed.")

    def _remove_work_dir(self, work_dir: Path) -> None:
        if work_dir.parent != self._work_root:
            raise RuntimeError("Refusing cleanup outside the File work root.")
        if work_dir.exists():
            shutil.rmtree(work_dir)

    async def _mark_failed(self, handle: Any) -> None:
        try:
            await handle.finish("failed")
        except AccountRevoked:
            pass

    async def _acquire_and_run(
        self,
        handle: Any,
        source_url: str,
        staging_dir: Path,
        started: asyncio.Event,
    ) -> None:
        started.set()
        try:
            input_path = await self._url_acquirer.acquire(source_url, staging_dir)
        except asyncio.CancelledError:
            self._remove_work_dir(staging_dir)
            raise
        except Exception:
            await self._mark_failed(handle)
            self._remove_work_dir(staging_dir)
            return
        await self._run(handle, input_path, asyncio.Event())

    async def _run(self, handle: Any, input_path: Path, started: asyncio.Event) -> None:
        options = {
            name: value
            for name, value in {
                "prompt": self._prompt,
                "max_length": self._max_length,
                "max_new_tokens": self._max_new_tokens,
                "decoding": self._decoding,
                "temperature": self._temperature,
            }.items()
            if value is not None
        }
        runner_task = asyncio.create_task(
            asyncio.to_thread(self._transcribe_from_one_mix, input_path, options)
        )
        started.set()
        try:
            await self._complete(handle, input_path, runner_task)
        except asyncio.CancelledError:
            try:
                await runner_task
            except Exception:
                LOGGER.error("File Meeting runner failed during shutdown.")
            self._remove_work_dir(input_path.parent)
            raise

    def _transcribe_from_one_mix(
        self,
        input_path: Path,
        options: dict[str, object],
    ) -> tuple[Any, Path | None]:
        mix_path: Path | None = None
        if self._audio_archive is not None:
            candidate = input_path.parent / "transcription-mix.wav"
            try:
                mix_path = self._audio_archive.prepare_mix(input_path, candidate)
            except Exception:
                candidate.unlink(missing_ok=True)
        result = self._runner.transcribe(mix_path or input_path, **options)
        return result, mix_path

    async def _complete(
        self,
        handle: Any,
        input_path: Path,
        runner_task: asyncio.Task[Any],
    ) -> None:
        try:
            result, mix_path = await asyncio.shield(runner_task)
        except Exception:
            await self._mark_failed(handle)
            self._remove_work_dir(input_path.parent)
            return

        if handle.owner_key in self._fenced_owner_keys:
            self._remove_work_dir(input_path.parent)
            return

        try:
            document = {
                "segments": [
                    segment.to_dict()
                    for segment in subtitle_segments_from_transcript(result.text, postprocess=False)
                ]
            }
        except Exception:
            await self._mark_failed(handle)
            self._remove_work_dir(input_path.parent)
            return

        try:
            await handle.commit_transcript(document)
        except AccountRevoked:
            # Revocation/interruption is already the durable terminal authority. A late result
            # must disappear rather than reconstructing a handle from its Meeting identifier.
            self._remove_work_dir(input_path.parent)
            return
        except Exception:
            await self._mark_failed(handle)
            self._remove_work_dir(input_path.parent)
            raise

        if handle.owner_key in self._fenced_owner_keys:
            self._remove_work_dir(input_path.parent)
            return

        if mix_path is None:
            audio_task = asyncio.create_task(handle.record_audio_unavailable())
        else:
            audio_task = asyncio.create_task(
                handle.publish_audio(self._audio_archive, mix_path)
            )
        try:
            await asyncio.shield(audio_task)
        except asyncio.CancelledError:
            try:
                await audio_task
            except AccountRevoked:
                pass
            except Exception:
                LOGGER.error("File Meeting audio publication failed during shutdown.")
            self._remove_work_dir(input_path.parent)
            raise

        except AccountRevoked:
            self._remove_work_dir(input_path.parent)
            return
        except Exception:
            await self._mark_failed(handle)
            self._remove_work_dir(input_path.parent)
            raise

        if handle.owner_key in self._fenced_owner_keys:
            self._remove_work_dir(input_path.parent)
            return

        try:
            self._remove_work_dir(input_path.parent)
        except Exception:
            await self._mark_failed(handle)
            raise
        try:
            await handle.finish("completed")
        except AccountRevoked:
            pass
