"""Owner-bound File-Meeting inference without a durable job identity."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import shutil
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moss_transcribe_diarize.subtitle import subtitle_segments_from_transcript

from .live_silence import is_digital_silence
from .model_runner import TranscriptionResult
from .phase2 import AccountRevoked
from .phase2_url import UrlAcquisitionRejected, validate_http_url
from .windowed_transcription import _accepted_speechless


DEFAULT_PHASE2_FILE_WORK_ROOT = (
    Path.home() / ".local" / "share" / "moss-transcribe-diarize" / "file-work"
)
LOGGER = logging.getLogger(__name__)
UPLOAD_RECEIVE_IDLE_TIMEOUT_SECONDS = 30.0
UPLOAD_CAPACITY_RESERVE_BYTES = 512 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
RETAINED_FILE_WORK_ROOT_NAME = "file-retained"
RETAINED_FILE_WORK_CONTRACT_VERSION = 1


class FileProcessingError(RuntimeError):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


class FileUploadRejected(RuntimeError):
    """A typed ingress refusal made before an Account Meeting is created."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class FileUploadTimeout(TimeoutError):
    pass


def admit_file_upload(request: Any, work_root: Path) -> int:
    """Refuse unbounded or unstoreable bodies before consuming request bytes."""

    raw_length = request.headers.get("content-length")
    if raw_length is None or not raw_length.isdecimal():
        raise FileUploadRejected(411, "Content-Length is required.")
    content_length = int(raw_length)
    require_upload_capacity(content_length, work_root)
    receive = request._receive

    async def receive_with_idle_timeout():
        try:
            return await asyncio.wait_for(
                receive(), timeout=UPLOAD_RECEIVE_IDLE_TIMEOUT_SECONDS
            )
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise FileUploadTimeout("Upload receive timed out.") from exc

    request._receive = receive_with_idle_timeout
    return content_length


def require_upload_capacity(content_length: int, work_root: Path) -> None:
    """Shared size-only preflight and authoritative body admission policy."""
    required_free = 2 * content_length + UPLOAD_CAPACITY_RESERVE_BYTES
    work_root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(work_root).free < required_free:
        raise FileUploadRejected(507, "Insufficient storage for upload.")


async def _read_upload_chunk(upload: Any) -> bytes:
    try:
        return await asyncio.wait_for(
            upload.read(UPLOAD_CHUNK_BYTES),
            timeout=UPLOAD_RECEIVE_IDLE_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, TimeoutError) as exc:
        raise FileUploadTimeout("Upload receive timed out.") from exc


@dataclass(slots=True)
class _OwnedFileTask:
    handle: Any
    task: asyncio.Task[None]
    phase: str = "queued"


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
        inference_scheduler: Any | None = None,
    ):
        self._runner = runner
        self._work_root = Path(work_root).expanduser()
        if self._work_root.name != "file-work":
            raise ValueError("File work root must be a dedicated directory named file-work.")
        self._retained_root = self._work_root.parent / RETAINED_FILE_WORK_ROOT_NAME
        self._prompt = prompt
        self._max_length = max_length
        self._max_new_tokens = max_new_tokens
        self._decoding = decoding
        self._temperature = temperature if decoding == "sample" else None
        self._url_acquirer = url_acquirer
        self._audio_archive = audio_archive
        self._inference_scheduler = inference_scheduler
        self._tasks: dict[str, _OwnedFileTask] = {}
        self._fenced_owner_keys: set[tuple[str, int]] = set()
        self._fenced_meeting_ids: set[str] = set()

    @property
    def work_root(self) -> Path:
        return self._work_root

    @property
    def retained_root(self) -> Path:
        """Meeting-owned File work that survives process-owned transient cleanup."""

        return self._retained_root

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
                while chunk := await _read_upload_chunk(upload):
                    output.write(chunk)
        except BaseException:
            try:
                self._remove_work_dir(staging_dir)
            except Exception:
                LOGGER.error("File Meeting upload cleanup failed.")
                raise
            raise

        handle = await workspace.create_meeting("file")
        try:
            input_path = self._retain_new_work(handle, staging_dir, input_path, ingress="file")
        except BaseException:
            await self._mark_failed(handle)
            self._remove_terminal_work_dir(self._owner_dir(handle))
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
            staging_dir = self._retain_new_directory(handle, staging_dir)
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
        for meeting_id, entry in tuple(self._tasks.items()):
            self._cancel_queued_inference(meeting_id)
            entry.task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def operator_snapshot(self) -> dict[str, str]:
        """Return only process-owned File phases; Meeting ownership stays in SQLite."""

        return {
            meeting_id: entry.phase
            for meeting_id, entry in self._tasks.items()
            if entry.phase in {"queued", "running"}
        }

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
            self._cancel_queued_inference(entry.handle.meeting_id)
            entry.task.cancel()
        return entries

    def fence_meeting(self, meeting_id: str) -> _OwnedFileTask | None:
        """Synchronously claim one active File task without fencing its Account peers."""

        entry = self._tasks.get(meeting_id)
        if entry is None:
            return None
        self._fenced_meeting_ids.add(meeting_id)
        self._cancel_queued_inference(meeting_id)
        entry.task.cancel()
        return entry

    async def settle_meeting(self, entry: _OwnedFileTask) -> bool:
        """Join one claimed task, then make only its durable Meeting interrupted."""

        try:
            interrupted = await self._settle_entries((entry,))
            return bool(interrupted)
        finally:
            self._fenced_meeting_ids.discard(entry.handle.meeting_id)

    async def settle_fenced(
        self,
        entries: tuple[_OwnedFileTask, ...],
    ) -> tuple[str, ...]:
        return await self._settle_entries(entries)

    async def _settle_entries(
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
            if self._audio_archive is None:
                raise RuntimeError("File Meeting audio archive is unavailable.")
            await entry.handle.recover_interrupted_file_audio(self._audio_archive)
            await entry.handle.finish("interrupted")
            self._remove_terminal_work_dir(self._owner_dir(entry.handle))
            interrupted.append(entry.handle.meeting_id)
        return tuple(interrupted)

    def _register(self, handle: Any, task: asyncio.Task[None]) -> None:
        meeting_id = handle.meeting_id
        self._tasks[meeting_id] = _OwnedFileTask(handle=handle, task=task)
        task.add_done_callback(lambda completed: self._task_done(meeting_id, completed))

    def _set_phase(self, meeting_id: str, phase: str) -> None:
        if phase not in {"queued", "running"}:
            raise ValueError("File task phase must be queued or running.")
        entry = self._tasks.get(meeting_id)
        if entry is not None:
            entry.phase = phase

    def _task_done(self, meeting_id: str, task: asyncio.Task[None]) -> None:
        entry = self._tasks.get(meeting_id)
        if entry is not None and entry.task is task:
            self._tasks.pop(meeting_id, None)
        if task.cancelled():
            return
        if task.exception() is not None:
            LOGGER.error("File Meeting background task failed.")

    def _cancel_queued_inference(self, meeting_id: str) -> None:
        if self._inference_scheduler is not None:
            self._inference_scheduler.cancel_background(meeting_id)

    def _remove_work_dir(self, work_dir: Path) -> None:
        if work_dir.parent != self._work_root:
            raise RuntimeError("Refusing cleanup outside the File work root.")
        if work_dir.exists():
            shutil.rmtree(work_dir)

    def _owner_dir(self, handle: Any) -> Path:
        account_id, _ = handle.owner_key
        return self._retained_root / account_id / handle.meeting_id

    def _retain_new_directory(self, handle: Any, staging_dir: Path) -> Path:
        """Move newly accepted work beneath its Meeting before background inference."""

        owner_dir = self._owner_dir(handle)
        if owner_dir.exists():
            raise RuntimeError("Retained File Meeting work already exists.")
        owner_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging_dir), str(owner_dir))
        return owner_dir

    def _retain_new_work(
        self,
        handle: Any,
        staging_dir: Path,
        input_path: Path,
        *,
        ingress: str,
    ) -> Path:
        owner_dir = self._retain_new_directory(handle, staging_dir)
        retained_input = owner_dir / input_path.name
        self._record_retained_source(handle, retained_input, ingress=ingress)
        return retained_input

    def _record_retained_source(self, handle: Any, input_path: Path, *, ingress: str) -> None:
        owner_dir = self._owner_dir(handle)
        if ingress not in {"file", "url"} or input_path.parent != owner_dir:
            raise RuntimeError("Retained File Meeting source is invalid.")
        if not input_path.is_file():
            raise RuntimeError("Retained File Meeting source is unavailable.")
        (owner_dir / "checkpoint").mkdir(exist_ok=True)
        (owner_dir / "owner.json").write_text(
            json.dumps(
                {
                    "account_id": handle.owner_key[0],
                    "meeting_id": handle.meeting_id,
                    "ingress": ingress,
                    "source": input_path.name,
                    "checkpoint": "checkpoint",
                    "contract_version": RETAINED_FILE_WORK_CONTRACT_VERSION,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def _remove_retained_work_dir(self, owner_dir: Path) -> None:
        if owner_dir.parent.parent != self._retained_root:
            raise RuntimeError("Refusing cleanup outside retained File Meeting work.")
        if owner_dir.exists():
            shutil.rmtree(owner_dir)

    def _is_retained_work_dir(self, work_dir: Path) -> bool:
        return work_dir.parent.parent == self._retained_root

    def _remove_terminal_work_dir(self, work_dir: Path) -> None:
        if self._is_retained_work_dir(work_dir):
            self._remove_retained_work_dir(work_dir)
        else:
            self._remove_work_dir(work_dir)

    async def _mark_failed(self, handle: Any, code: str = "storage_failed",
                           reason: str = "The meeting could not be saved.") -> None:
        LOGGER.warning("File Meeting failed: %s", code)
        try:
            await handle.finish("failed", failure_code=code, failure_reason=reason)
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
            raise
        except Exception as exc:
            code = exc.failure_code if isinstance(exc, UrlAcquisitionRejected) else "acquisition_failed"
            reason = str(exc) if isinstance(exc, UrlAcquisitionRejected) else "The media could not be downloaded."
            await self._mark_failed(handle, code, reason)
            self._remove_terminal_work_dir(staging_dir)
            return
        self._record_retained_source(handle, input_path, ingress="url")
        await self._run(handle, input_path, asyncio.Event())

    async def _run(self, handle: Any, input_path: Path, started: asyncio.Event) -> None:
        loop = asyncio.get_running_loop()
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
        if self._inference_scheduler is not None:
            options.update(
                _dispatch_key=handle.meeting_id,
                _dispatch_on_wait=lambda: loop.call_soon_threadsafe(
                    self._set_phase, handle.meeting_id, "queued"
                ),
                _dispatch_on_start=lambda: loop.call_soon_threadsafe(
                    self._set_phase, handle.meeting_id, "running"
                ),
            )
        runner_task = asyncio.create_task(
            asyncio.to_thread(self._transcribe_from_one_mix, input_path, options)
        )
        if self._inference_scheduler is None:
            self._set_phase(handle.meeting_id, "running")
        started.set()
        try:
            await self._complete(handle, input_path, runner_task)
        except asyncio.CancelledError:
            try:
                await runner_task
            except Exception:
                LOGGER.error("File Meeting runner failed during shutdown.")
            raise

    def _transcribe_from_one_mix(
        self,
        input_path: Path,
        options: dict[str, object],
    ) -> tuple[Any, Path | None, list[str]]:
        notices: list[str] = []
        transcribe_options = {
            **options,
            "checkpoint_dir": (
                input_path.parent / "checkpoint"
                if self._is_retained_work_dir(input_path.parent)
                else None
            ),
        }
        mix_path: Path | None = None
        mix_failed = False
        if self._audio_archive is not None:
            candidate = input_path.parent / "transcription-mix.wav"
            try:
                mix_path = self._audio_archive.prepare_mix(input_path, candidate, notices=notices)
            except Exception:
                mix_failed = True
                candidate.unlink(missing_ok=True)
                LOGGER.warning("File Meeting audio: transcode_failed; trying runner input")
        # Decide whether to dispatch from the normalized File PCM, before asking
        # a decoder that may invent speech for digital zeros. Any signal still decodes.
        if mix_path is not None and _is_silent_mix(mix_path):
            return TranscriptionResult(
                text="", prompt_len=0, generated_tokens=0, elapsed_sec=0.0,
                model=str(getattr(self._runner, "model_path", "")), audio=str(mix_path),
                decoding=str(options.get("decoding") or "greedy"), temperature=None,
                window_diagnostics=[{
                    "condition": "speechless_window_empty", "detector": "digital_zero",
                }],
            ), mix_path, notices
        try:
            result = self._runner.transcribe(mix_path or input_path, **transcribe_options)
        except Exception as exc:
            if mix_failed or getattr(exc, "condition", None) == "extraction_exception":
                raise FileProcessingError("transcode_failed", "Media could not be decoded. The format may be unsupported or damaged.") from exc
            raise FileProcessingError("decode_failed", "The speech decoder could not transcribe this media.") from exc
        return result, mix_path, notices

    async def _complete(
        self,
        handle: Any,
        input_path: Path,
        runner_task: asyncio.Task[Any],
    ) -> None:
        try:
            result, mix_path, notices = await asyncio.shield(runner_task)
        except Exception as exc:
            code = exc.code if isinstance(exc, FileProcessingError) else "decode_failed"
            reason = exc.reason if isinstance(exc, FileProcessingError) else "The speech decoder could not transcribe this media."
            await self._mark_failed(handle, code, reason)
            self._remove_terminal_work_dir(input_path.parent)
            return

        if self._is_fenced(handle):
            return

        try:
            document = {
                "segments": [
                    segment.to_dict()
                    for segment in subtitle_segments_from_transcript(result.text, postprocess=False)
                ]
            }
            if not document["segments"] and not _accepted_speechless(result):
                raise ValueError("Empty decoder output without speechless evidence")
        except Exception:
            await self._mark_failed(handle, "decode_invalid", "The speech decoder returned no usable transcript.")
            self._remove_terminal_work_dir(input_path.parent)
            return

        try:
            await handle.commit_transcript(document)
        except AccountRevoked:
            # Revocation/interruption is already the durable terminal authority. A late result
            # must disappear rather than reconstructing a handle from its Meeting identifier.
            self._remove_terminal_work_dir(input_path.parent)
            return
        except Exception:
            await self._mark_failed(handle)
            self._remove_terminal_work_dir(input_path.parent)
            raise

        if self._is_fenced(handle):
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
            raise

        except AccountRevoked:
            self._remove_terminal_work_dir(input_path.parent)
            return
        except Exception:
            await self._mark_failed(handle)
            self._remove_terminal_work_dir(input_path.parent)
            raise

        if self._is_fenced(handle):
            return

        try:
            if getattr(result, "possibly_truncated", False):
                notices.append("The speech decoder reached its output limit. This transcript may be incomplete.")
            if not document["segments"]:
                notices.append("No speech detected.")
            await handle.finish("completed", notice=" ".join(notices) or None)
        except AccountRevoked:
            self._remove_terminal_work_dir(input_path.parent)
            return
        try:
            self._remove_terminal_work_dir(input_path.parent)
        except Exception:
            LOGGER.error("Retained File Meeting cleanup failed after terminal completion.")
            raise

    def _is_fenced(self, handle: Any) -> bool:
        return (
            handle.owner_key in self._fenced_owner_keys
            or handle.meeting_id in self._fenced_meeting_ids
        )


def _is_silent_mix(path: Path) -> bool:
    """Only nonempty normalized PCM16 zeros justify File speechless completion."""
    try:
        with wave.open(str(path), "rb") as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
                return False
            if not audio.getnframes():
                return False
            while pcm := audio.readframes(UPLOAD_CHUNK_BYTES // 2):
                if not is_digital_silence(pcm):
                    return False
            return True
    except (OSError, EOFError, wave.Error):
        return False
