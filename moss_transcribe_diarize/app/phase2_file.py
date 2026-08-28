"""Owner-bound File-Meeting inference without a durable job identity."""

from __future__ import annotations

import asyncio
import logging
import secrets
import shutil
from pathlib import Path
from typing import Any

from moss_transcribe_diarize.subtitle import subtitle_segments_from_transcript

from .phase2 import AccountRevoked


DEFAULT_PHASE2_FILE_WORK_ROOT = (
    Path.home() / ".local" / "share" / "moss-transcribe-diarize" / "file-work"
)
LOGGER = logging.getLogger(__name__)


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
        self._tasks: set[asyncio.Task[None]] = set()

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
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        await started.wait()
        return handle

    async def stop(self) -> None:
        """Fence coroutine commits before the owning SQLite connection closes."""

        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _task_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
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
            asyncio.to_thread(self._runner.transcribe, input_path, **options)
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

    async def _complete(
        self,
        handle: Any,
        input_path: Path,
        runner_task: asyncio.Task[Any],
    ) -> None:
        try:
            result = await asyncio.shield(runner_task)
        except Exception:
            await self._mark_failed(handle)
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
            self._remove_work_dir(input_path.parent)
        except Exception:
            await self._mark_failed(handle)
            raise
        try:
            await handle.commit_transcript(document, terminal=True)
        except AccountRevoked:
            # Revocation/interruption is already the durable terminal authority. A late result
            # must disappear rather than reconstructing a handle from its Meeting identifier.
            pass
        except Exception:
            await self._mark_failed(handle)
            raise
