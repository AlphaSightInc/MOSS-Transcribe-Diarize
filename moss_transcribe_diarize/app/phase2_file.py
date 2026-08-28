"""Owner-bound File-Meeting inference without a durable job identity."""

from __future__ import annotations

import asyncio
import secrets
import shutil
from pathlib import Path
from typing import Any

from moss_transcribe_diarize.subtitle import subtitle_segments_from_transcript

from .phase2 import AccountRevoked


DEFAULT_PHASE2_FILE_WORK_ROOT = (
    Path.home() / ".local" / "share" / "moss-transcribe-diarize" / "file-work"
)


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
        self._work_root = Path(work_root)
        self._prompt = prompt
        self._max_length = max_length
        self._max_new_tokens = max_new_tokens
        self._decoding = decoding
        self._temperature = temperature if decoding == "sample" else None
        self._tasks: set[asyncio.Task[None]] = set()

    async def accept(self, workspace: Any, upload: Any) -> Any:
        """Store a complete request body, then create exactly one File Meeting and start work."""

        filename = upload.filename if isinstance(upload.filename, str) else "input.media"
        suffix = Path(filename).suffix or ".media"
        staging_dir = self._work_root / secrets.token_urlsafe(18)
        input_path = staging_dir / f"input{suffix}"
        staging_dir.mkdir(parents=True, exist_ok=False)
        try:
            with input_path.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    output.write(chunk)
            handle = await workspace.create_meeting("file")
        except BaseException:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

        task = asyncio.create_task(self._run(handle, input_path))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return handle

    async def stop(self) -> None:
        """Fence coroutine commits before the owning SQLite connection closes."""

        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, handle: Any, input_path: Path) -> None:
        try:
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
            result = await asyncio.to_thread(self._runner.transcribe, input_path, **options)
            document = {
                "segments": [
                    segment.to_dict()
                    for segment in subtitle_segments_from_transcript(result.text, postprocess=False)
                ]
            }
            await handle.commit_transcript(document, terminal=True)
        except asyncio.CancelledError:
            raise
        except AccountRevoked:
            # Revocation/interruption is already the durable terminal authority. A late result
            # must disappear rather than reconstructing a handle from its Meeting identifier.
            pass
        except Exception:
            try:
                await handle.finish("failed")
            except AccountRevoked:
                pass
        finally:
            shutil.rmtree(input_path.parent, ignore_errors=True)
