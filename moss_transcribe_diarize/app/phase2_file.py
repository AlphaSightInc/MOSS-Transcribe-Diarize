"""Owner-bound File-Meeting inference without a durable job identity."""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
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
from .windowed_transcription import accepted_speechless


DEFAULT_PHASE2_FILE_WORK_ROOT = (
    Path.home() / ".local" / "share" / "moss-transcribe-diarize" / "file-work"
)
LOGGER = logging.getLogger(__name__)
UPLOAD_RECEIVE_IDLE_TIMEOUT_SECONDS = 30.0
UPLOAD_CAPACITY_RESERVE_BYTES = 512 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
RETAINED_FILE_WORK_ROOT_NAME = "file-retained"
RETAINED_FILE_WORK_CONTRACT_VERSION = 1
RETAINED_VALIDATION_CONCURRENCY = 4
RETAINED_VALIDATION_ATTEMPTS = 3
RETAINED_VALIDATION_BACKOFF_SECONDS = 0.5


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


class RetainedFileWorkBusy(RuntimeError):
    """Another startup already owns this retained File Meeting."""


class _RetainedValidationError(RuntimeError):
    """Checkpoint validation could not complete; it did not refuse the contract."""


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
    retained_lock: Any | None = None
    resumed: bool = False
    interrupted_by_meeting: bool = False
    settlement: asyncio.Task[tuple[str, ...]] | None = None


@dataclass(slots=True)
class _RetainedReservation:
    handle: Any
    owner_dir: Path
    retained_lock: Any
    interrupted: bool = False
    settlement: asyncio.Task[tuple[str, ...]] | None = None
    claim_settlement: asyncio.Task[tuple[str, ...]] | None = None
    resumed: bool = True
    terminal_settled: bool = False
    validation_finished: bool = False


@dataclass(slots=True)
class _RetainedClaim:
    owner: "FileMeetingTasks"
    reservation: _RetainedReservation | None
    background: bool = False
    consumed: bool = False

    @property
    def owner_key(self) -> tuple[str, str] | None:
        if self.reservation is None:
            return None
        handle = self.reservation.handle
        return (handle.owner_key[0], handle.meeting_id)

    def __await__(self):
        if self.consumed:
            raise RuntimeError("Retained File claim was already consumed.")
        self.consumed = True
        return self.owner._complete_retained_claim(self).__await__()


@dataclass(frozen=True, slots=True)
class _RetainedResumeSource:
    """Validated source identity carried intact into retained execution."""

    input_path: Path
    source: Path
    checkpoint_bound: bool
    mix_path: Path | None


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
        self._reservations: dict[str, _RetainedReservation] = {}
        self._fenced_owner_keys: set[tuple[str, int]] = set()
        self._fenced_meeting_ids: set[str] = set()
        self._refused_retained_work: dict[str, tuple[Any, Path]] = {}
        self._retained_resume_task: asyncio.Task[None] | None = None
        self._retained_claim_tasks: set[asyncio.Task[None]] = set()
        self._reservation_settlements: set[asyncio.Task[tuple[str, ...]]] = set()

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

    def claim_retained_work(self, handle: Any) -> _RetainedClaim:
        """Reserve retained work now; validate it only when the returned claim is awaited."""

        owner_dir = self._owner_dir(handle)
        retained_lock = self._claim_retained_lock(owner_dir)
        if retained_lock is None:
            return _RetainedClaim(self, None)
        try:
            owner_manifest_exists = (owner_dir / "owner.json").is_file()
        except OSError:
            owner_manifest_exists = False
        if not owner_manifest_exists:
            self._release_retained_lock(retained_lock)
            return _RetainedClaim(self, None)
        reservation = _RetainedReservation(handle, owner_dir, retained_lock)
        self._reservations[handle.meeting_id] = reservation
        LOGGER.info("Retained File owner reserved: %s", handle.meeting_id)
        return _RetainedClaim(self, reservation)

    async def _complete_retained_claim(self, claim: _RetainedClaim) -> bool:
        reservation = claim.reservation
        if reservation is None:
            return False
        handle = reservation.handle
        try:
            validated_source = None
            for attempt in range(RETAINED_VALIDATION_ATTEMPTS):
                if reservation.interrupted:
                    return False
                LOGGER.info("Retained File validation started: %s", handle.meeting_id)
                validation = asyncio.create_task(
                    asyncio.to_thread(
                        self._verified_retained_resume_source,
                        handle,
                        reservation.owner_dir,
                    )
                )
                try:
                    validated_source = await asyncio.shield(validation)
                except asyncio.CancelledError:
                    await asyncio.shield(validation)
                    raise
                except Exception as exc:
                    if reservation.interrupted:
                        return False
                    if attempt + 1 == RETAINED_VALIDATION_ATTEMPTS:
                        raise _RetainedValidationError(str(exc)) from exc
                    LOGGER.warning(
                        "Retained File validation error; retrying: %s",
                        handle.meeting_id,
                    )
                    await asyncio.sleep(
                        RETAINED_VALIDATION_BACKOFF_SECONDS * (2**attempt)
                    )
                    if reservation.interrupted:
                        return False
                    continue
                break
            if reservation.interrupted:
                return False
            if validated_source is None:
                if not claim.background:
                    self._refused_retained_work[handle.meeting_id] = (
                        handle,
                        reservation.owner_dir,
                    )
                return False
            started = asyncio.Event()
            task = asyncio.create_task(
                self._run(
                    handle,
                    validated_source.source,
                    started,
                    resumed=True,
                    resume_source=validated_source,
                )
            )
            self._register(
                handle,
                task,
                retained_lock=reservation.retained_lock,
                resumed=True,
            )
            self._reservations.pop(handle.meeting_id, None)
            reservation.retained_lock = None
            started_wait = asyncio.create_task(started.wait())
            try:
                await asyncio.wait(
                    (started_wait, task),
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                if not started_wait.done():
                    started_wait.cancel()
                    await asyncio.gather(started_wait, return_exceptions=True)
            return True
        finally:
            reservation.validation_finished = True
            if not claim.background:
                self._reservations.pop(handle.meeting_id, None)
                self._release_retained_lock(reservation.retained_lock)
                reservation.retained_lock = None

    async def resume_retained_work(self, store: Any) -> frozenset[tuple[str, str]]:
        """Reserve owners for fallback exclusion, then validate them after readiness."""

        current = getattr(self, "_retained_resume_task", None)
        if current is not None and not current.done():
            raise RetainedFileWorkBusy("Retained File startup is already in progress.")
        claims = tuple(
            self.claim_retained_work(handle)
            for handle in await store.active_file_meetings()
        )
        claimed = frozenset(
            claim.owner_key
            for claim in claims
            if isinstance(claim, _RetainedClaim) and claim.owner_key is not None
        )
        if claims:
            for claim in claims:
                if isinstance(claim, _RetainedClaim):
                    claim.background = True
            coordinator = asyncio.create_task(self._resume_retained_claims(claims))
            self._retained_resume_task = coordinator
            coordinator.add_done_callback(self._retained_resume_done)
        return claimed

    async def _resume_retained_claims(self, claims: tuple[Any, ...]) -> None:
        bound = asyncio.Semaphore(RETAINED_VALIDATION_CONCURRENCY)
        tasks = tuple(
            asyncio.create_task(self._resume_one_retained_claim(claim, bound))
            for claim in claims
        )
        self._retained_claim_tasks.update(tasks)
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            self._retained_claim_tasks.difference_update(tasks)
        for result in results:
            if isinstance(result, BaseException) and not isinstance(
                result, asyncio.CancelledError
            ):
                LOGGER.error("Retained File startup owner remained unsettled.")

    async def _resume_one_retained_claim(
        self,
        claim: Any,
        bound: asyncio.Semaphore,
    ) -> None:
        reservation = claim.reservation if isinstance(claim, _RetainedClaim) else None
        try:
            async with bound:
                if reservation is not None and reservation.interrupted:
                    accepted = False
                else:
                    accepted = await claim
            if reservation is None:
                return
            if reservation.interrupted:
                await self._remove_settled_reservation(reservation)
            elif not accepted:
                await self._interrupt_refused_reservation(reservation)
        except asyncio.CancelledError:
            raise
        except Exception:
            if reservation is None:
                LOGGER.error("Retained File startup claim failed.")
                return
            try:
                await self._fail_retained_reservation(reservation)
            except Exception:
                LOGGER.error(
                    "Retained File startup owner remained unsettled: %s",
                    reservation.handle.meeting_id,
                )
        finally:
            if reservation is not None and reservation.retained_lock is not None:
                self._reservations.pop(reservation.handle.meeting_id, None)
                self._release_retained_lock(reservation.retained_lock)
                reservation.retained_lock = None
                LOGGER.info(
                    "Retained File reservation settled: %s",
                    reservation.handle.meeting_id,
                )

    async def _remove_settled_reservation(
        self,
        reservation: _RetainedReservation,
    ) -> None:
        if not reservation.validation_finished:
            return
        if not reservation.terminal_settled and (
            await reservation.handle.snapshot()
        ).status == "active":
            return
        if reservation.owner_dir.exists():
            self._remove_reservation_work(reservation)

    def _remove_reservation_work(
        self,
        reservation: _RetainedReservation,
    ) -> None:
        try:
            self._remove_terminal_work_dir(reservation.owner_dir)
        except OSError:
            LOGGER.warning(
                "Retained File reservation cleanup failed: %s",
                reservation.handle.meeting_id,
            )

    def _record_reservation_settled(
        self,
        reservation: _RetainedReservation,
    ) -> None:
        reservation.terminal_settled = True
        if reservation.validation_finished:
            self._remove_reservation_work(reservation)

    def _track_reservation_settlement(
        self,
        settlement: asyncio.Task[tuple[str, ...]],
    ) -> asyncio.Task[tuple[str, ...]]:
        self._reservation_settlements.add(settlement)
        settlement.add_done_callback(self._reservation_settlements.discard)
        return settlement

    async def _interrupt_refused_reservation(
        self,
        reservation: _RetainedReservation,
    ) -> None:
        if reservation.claim_settlement is None or reservation.claim_settlement.done():
            reservation.claim_settlement = self._track_reservation_settlement(
                asyncio.create_task(self._settle_entries((reservation,)))
            )
        await asyncio.shield(reservation.claim_settlement)
        await self._remove_settled_reservation(reservation)
        self._refused_retained_work.pop(reservation.handle.meeting_id, None)

    async def _fail_retained_reservation(
        self,
        reservation: _RetainedReservation,
    ) -> None:
        if reservation.claim_settlement is None or reservation.claim_settlement.done():
            reservation.claim_settlement = self._track_reservation_settlement(
                asyncio.create_task(self._settle_failed_reservation(reservation))
            )
        await asyncio.shield(reservation.claim_settlement)
        await self._remove_settled_reservation(reservation)
        self._refused_retained_work.pop(reservation.handle.meeting_id, None)

    async def _settle_failed_reservation(
        self,
        reservation: _RetainedReservation,
    ) -> tuple[str, ...]:
        handle = reservation.handle
        if self._audio_archive is None:
            raise RuntimeError("File Meeting audio archive is unavailable.")
        await handle.recover_interrupted_file_audio(self._audio_archive)
        recorded = await self._mark_failed(
            handle,
            "resume_failed",
            "Retained File restart could not finish.",
        )
        if not recorded:
            return await self._settle_entries((reservation,))
        self._record_reservation_settled(reservation)
        return (handle.meeting_id,)

    @staticmethod
    def _retained_resume_done(task: asyncio.Task[None]) -> None:
        if not task.cancelled() and task.exception() is not None:
            LOGGER.error("Retained File startup coordinator failed.")

    async def reclaim_refused_retained_work(self) -> None:
        """Remove only retained owners that fallback has already made terminal."""

        for meeting_id, (handle, owner_dir) in tuple(self._refused_retained_work.items()):
            if (await handle.snapshot()).status == "active":
                continue
            self._remove_terminal_work_dir(owner_dir)
            self._refused_retained_work.pop(meeting_id, None)

    def reclaim_terminal_retained_work(
        self,
        owners: tuple[tuple[str, str], ...],
    ) -> None:
        """Remove only Meeting directories named by durable terminal File owners."""

        for account_id, meeting_id in owners:
            if meeting_id in self._reservations:
                continue
            try:
                self._remove_retained_work_dir(
                    self._retained_root / account_id / meeting_id
                )
            except OSError:
                LOGGER.warning(
                    "Retained File owner cleanup failed; account=%s meeting=%s; "
                    "retrying next boot.",
                    account_id,
                    meeting_id,
                )

    def retained_work_owners(self) -> tuple[tuple[str, str], ...]:
        """Return exact two-level owner directories that currently exist on disk."""

        if not self._retained_root.is_dir():
            return ()
        owners: list[tuple[str, str]] = []
        for account_dir in self._retained_root.iterdir():
            try:
                if account_dir.is_symlink() or not account_dir.is_dir():
                    continue
                owner_dirs = tuple(account_dir.iterdir())
            except OSError:
                LOGGER.warning("Retained File account directory unreadable; skipping.")
                continue
            for owner_dir in owner_dirs:
                try:
                    if owner_dir.is_symlink() or not owner_dir.is_dir():
                        continue
                except OSError:
                    LOGGER.warning("Retained File owner entry unreadable; skipping.")
                    continue
                owners.append((account_dir.name, owner_dir.name))
        return tuple(sorted(owners))

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

        handle = None
        task = None
        try:
            handle = await workspace.create_meeting("file")
            input_path = self._retain_new_work(handle, staging_dir, input_path, ingress="file")
            started = asyncio.Event()
            run = self._run(handle, input_path, started)
            try:
                task = asyncio.create_task(run)
            except BaseException:
                run.close()
                raise
            self._register(handle, task)
        except BaseException:
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if handle is not None:
                await self._mark_failed(handle)
            self._remove_terminal_work_dir(staging_dir)
            if handle is not None:
                self._remove_terminal_work_dir(self._owner_dir(handle))
            raise

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
        handle = None
        task = None
        try:
            handle = await workspace.create_meeting("file")
            staging_dir = self._retain_new_directory(handle, staging_dir)
            started = asyncio.Event()
            run = self._acquire_and_run(handle, source_url, staging_dir, started)
            try:
                task = asyncio.create_task(run)
            except BaseException:
                run.close()
                raise
            self._register(handle, task)
        except BaseException:
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if handle is not None:
                await self._mark_failed(handle)
            self._remove_terminal_work_dir(staging_dir)
            if handle is not None:
                self._remove_terminal_work_dir(self._owner_dir(handle))
            raise

        await started.wait()
        return handle

    async def stop(self) -> None:
        """Fence coroutine commits before the owning SQLite connection closes."""

        retained_resume_task = self._retained_resume_task
        if retained_resume_task is not None and not retained_resume_task.done():
            retained_resume_task.cancel()
        claim_tasks = tuple(self._retained_claim_tasks)
        settlements = tuple(self._reservation_settlements)
        for task in (*claim_tasks, *settlements):
            task.cancel()
        pending = tuple(
            task
            for task in (retained_resume_task, *claim_tasks, *settlements)
            if task is not None
        )
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for meeting_id, reservation in tuple(self._reservations.items()):
            self._reservations.pop(meeting_id, None)
            self._release_retained_lock(reservation.retained_lock)
            reservation.retained_lock = None
        tasks = tuple(entry.task for entry in self._tasks.values())
        for meeting_id, entry in tuple(self._tasks.items()):
            self._cancel_queued_inference(meeting_id)
            entry.task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def operator_snapshot(self) -> dict[str, str]:
        """Return only process-owned File phases; Meeting ownership stays in SQLite."""

        snapshot = {
            meeting_id: entry.phase
            for meeting_id, entry in self._tasks.items()
            if entry.phase in {"queued", "running"}
        }
        snapshot.update(
            (meeting_id, "validating") for meeting_id in self._reservations
        )
        return snapshot

    async def interrupt_account(self, owner_key: tuple[str, int]) -> tuple[str, ...]:
        """Quiesce this Account generation, then durably interrupt its active File rows."""

        entries = self.fence_account(owner_key)
        return await self.settle_fenced(entries)

    def fence_account(
        self,
        owner_key: tuple[str, int],
    ) -> tuple[_OwnedFileTask | _RetainedReservation, ...]:
        """Reject every later result before waiting for any one task."""

        self._fenced_owner_keys.add(owner_key)
        entries: tuple[_OwnedFileTask | _RetainedReservation, ...] = tuple(
            entry
            for entry in self._tasks.values()
            if entry.handle.owner_key == owner_key
        ) + tuple(
            reservation
            for reservation in self._reservations.values()
            if reservation.handle.owner_key == owner_key
        )
        for entry in entries:
            if isinstance(entry, _RetainedReservation):
                entry.interrupted = True
            else:
                self._cancel_queued_inference(entry.handle.meeting_id)
                entry.task.cancel()
        return entries

    def fence_meeting(
        self,
        meeting_id: str,
    ) -> _OwnedFileTask | _RetainedReservation | None:
        """Synchronously claim one active File task without fencing its Account peers."""

        entry = self._tasks.get(meeting_id)
        if entry is None:
            reservation = self._reservations.get(meeting_id)
            if reservation is None:
                return None
            reservation.interrupted = True
            entry = reservation
        elif isinstance(entry, _OwnedFileTask):
            entry.interrupted_by_meeting = True
        self._fenced_meeting_ids.add(meeting_id)
        if isinstance(entry, _OwnedFileTask):
            self._cancel_queued_inference(meeting_id)
            entry.task.cancel()
        return entry

    async def settle_meeting(
        self,
        entry: _OwnedFileTask | _RetainedReservation,
    ) -> bool:
        """Join one claimed task, then make only its durable Meeting interrupted."""

        settlement = self._settlement_task(
            entry,
            failure_code="cancelled" if entry.resumed else None,
        )
        try:
            interrupted = await asyncio.shield(settlement)
            return bool(interrupted)
        finally:
            self._fenced_meeting_ids.discard(entry.handle.meeting_id)

    async def settle_fenced(
        self,
        entries: tuple[_OwnedFileTask | _RetainedReservation, ...],
    ) -> tuple[str, ...]:
        results = await asyncio.gather(
            *(
                asyncio.shield(self._settlement_task(entry))
                for entry in entries
            )
        )
        return tuple(meeting_id for result in results for meeting_id in result)

    def _settlement_task(
        self,
        entry: _OwnedFileTask | _RetainedReservation,
        *,
        failure_code: str | None = None,
    ) -> asyncio.Task[tuple[str, ...]]:
        if entry.settlement is None or entry.settlement.done():
            settlement = asyncio.create_task(
                self._settle_entries((entry,), failure_code=failure_code)
            )
            entry.settlement = (
                self._track_reservation_settlement(settlement)
                if isinstance(entry, _RetainedReservation)
                else settlement
            )
        return entry.settlement

    async def _settle_entries(
        self,
        entries: tuple[_OwnedFileTask | _RetainedReservation, ...],
        *,
        failure_code: str | None = None,
    ) -> tuple[str, ...]:
        running = tuple(
            entry for entry in entries if isinstance(entry, _OwnedFileTask)
        )
        if running:
            results = await asyncio.gather(
                *(entry.task for entry in running),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, Exception) and not isinstance(
                    result, asyncio.CancelledError
                ):
                    raise RuntimeError("File Meeting could not be quiesced.") from result
        interrupted: list[str] = []
        for entry in entries:
            if isinstance(entry, _RetainedReservation):
                claim_settlement = entry.claim_settlement
                if (
                    claim_settlement is not None
                    and claim_settlement is not asyncio.current_task()
                ):
                    if claim_settlement.done() and (
                        claim_settlement.cancelled()
                        or claim_settlement.exception() is not None
                    ):
                        if entry.claim_settlement is claim_settlement:
                            entry.claim_settlement = None
                    else:
                        await asyncio.shield(claim_settlement)
                        continue
            try:
                snapshot = await entry.handle.snapshot()
            except (AccountRevoked, KeyError):
                if isinstance(entry, _RetainedReservation):
                    self._record_reservation_settled(entry)
                continue
            if snapshot.status != "active":
                if isinstance(entry, _RetainedReservation):
                    self._record_reservation_settled(entry)
                continue
            if self._audio_archive is None:
                raise RuntimeError("File Meeting audio archive is unavailable.")
            try:
                await entry.handle.recover_interrupted_file_audio(self._audio_archive)
                await entry.handle.finish("interrupted", failure_code=failure_code)
            except AccountRevoked:
                if isinstance(entry, _RetainedReservation):
                    self._record_reservation_settled(entry)
                    continue
                raise
            if isinstance(entry, _OwnedFileTask):
                self._remove_terminal_work_dir(self._owner_dir(entry.handle))
            else:
                self._record_reservation_settled(entry)
                LOGGER.info(
                    "Retained File reservation durably interrupted: %s",
                    entry.handle.meeting_id,
                )
            interrupted.append(entry.handle.meeting_id)
        return tuple(interrupted)

    def _register(
        self,
        handle: Any,
        task: asyncio.Task[None],
        *,
        retained_lock: Any | None = None,
        resumed: bool = False,
    ) -> None:
        meeting_id = handle.meeting_id
        if self._is_fenced(handle):
            task.cancel()
            raise RuntimeError("Fenced File Meeting cannot be registered.")
        self._tasks[meeting_id] = _OwnedFileTask(
            handle=handle,
            task=task,
            retained_lock=retained_lock,
            resumed=resumed,
        )
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
            self._release_retained_lock(entry.retained_lock)
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

    def _claim_retained_lock(self, owner_dir: Path) -> Any | None:
        try:
            if not owner_dir.is_dir():
                return None
            retained_lock = (owner_dir / "resume.lock").open("a+")
        except OSError:
            return None
        try:
            fcntl.flock(retained_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            retained_lock.close()
            raise RetainedFileWorkBusy(
                "Retained File Meeting already has a startup owner."
            ) from exc
        except OSError:
            retained_lock.close()
            return None
        return retained_lock

    @staticmethod
    def _release_retained_lock(retained_lock: Any | None) -> None:
        if retained_lock is None:
            return
        try:
            fcntl.flock(retained_lock.fileno(), fcntl.LOCK_UN)
        finally:
            retained_lock.close()

    def _verified_retained_input(self, handle: Any, owner_dir: Path) -> Path | None:
        verified = self._verified_retained_resume_source(handle, owner_dir)
        return None if verified is None else verified.input_path

    def _verified_retained_resume_source(
        self,
        handle: Any,
        owner_dir: Path,
    ) -> _RetainedResumeSource | None:
        try:
            manifest = json.loads((owner_dir / "owner.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        except OSError as exc:
            raise _RetainedValidationError("owner manifest unavailable") from exc
        if not isinstance(manifest, dict) or set(manifest) != {
            "account_id",
            "meeting_id",
            "ingress",
            "source",
            "checkpoint",
            "contract_version",
        }:
            return None
        account_id, _ = handle.owner_key
        source_name = manifest.get("source")
        if (
            manifest.get("account_id") != account_id
            or manifest.get("meeting_id") != handle.meeting_id
            or manifest.get("ingress") not in {"file", "url"}
            or manifest.get("checkpoint") != "checkpoint"
            or manifest.get("contract_version") != RETAINED_FILE_WORK_CONTRACT_VERSION
            or not isinstance(source_name, str)
            or Path(source_name).name != source_name
        ):
            return None
        input_path = owner_dir / source_name
        checkpoint_dir = owner_dir / "checkpoint"
        if not input_path.is_file() or not checkpoint_dir.is_dir():
            return None
        resume_source = self._retained_resume_source(input_path, checkpoint_dir)
        if resume_source is None:
            return None
        if not resume_source.checkpoint_bound:
            return resume_source
        verdict = self._checkpoint_verdict(resume_source.source, checkpoint_dir)
        if getattr(verdict, "status", None) == "error":
            raise _RetainedValidationError(str(verdict.reason))
        if not bool(getattr(verdict, "accepted", False)):
            return None
        return resume_source

    def _retained_resume_source(
        self,
        input_path: Path,
        checkpoint_dir: Path,
    ) -> _RetainedResumeSource | None:
        """Resolve the retained file named by an existing checkpoint manifest."""

        manifest_path = checkpoint_dir / "manifest.json"
        if not manifest_path.exists():
            if any((checkpoint_dir / "windows").glob("w*.json")):
                return None
            return _RetainedResumeSource(
                input_path=input_path,
                source=input_path,
                checkpoint_bound=False,
                mix_path=None,
            )
        try:
            checkpoint_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        except OSError as exc:
            raise _RetainedValidationError("checkpoint manifest unavailable") from exc
        if not isinstance(checkpoint_manifest, dict):
            return None
        source_sha256 = checkpoint_manifest.get("source_sha256")
        if not isinstance(source_sha256, str):
            return None
        mix_path = input_path.parent / "transcription-mix.wav"
        for candidate in (mix_path, input_path):
            if not candidate.is_file():
                continue
            try:
                digest = hashlib.sha256()
                with candidate.open("rb") as source:
                    while chunk := source.read(1024 * 1024):
                        digest.update(chunk)
            except OSError as exc:
                raise _RetainedValidationError("checkpoint source unavailable") from exc
            if digest.hexdigest() == source_sha256:
                return _RetainedResumeSource(
                    input_path=input_path,
                    source=candidate,
                    checkpoint_bound=True,
                    mix_path=candidate if candidate == mix_path else None,
                )
        return None

    def _checkpoint_is_valid(self, input_path: Path, checkpoint_dir: Path) -> bool:
        """Reuse the deployed runner's checkpoint contract before dispatching a decoder."""

        validate_resume = getattr(self._runner, "validate_resume", None)
        if not callable(validate_resume):
            return False
        try:
            verdict = validate_resume(
                input_path,
                checkpoint_dir,
                inference=self._inference_options(),
            )
        except Exception:
            return False
        return bool(getattr(verdict, "accepted", False))

    def _checkpoint_verdict(self, input_path: Path, checkpoint_dir: Path) -> Any:
        validate_resume = getattr(self._runner, "validate_resume", None)
        if not callable(validate_resume):
            return None
        try:
            return validate_resume(
                input_path,
                checkpoint_dir,
                inference=self._inference_options(),
            )
        except Exception as exc:
            raise _RetainedValidationError("checkpoint validator unavailable") from exc

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
                           reason: str = "The meeting could not be saved.") -> bool:
        LOGGER.warning("File Meeting failed: %s", code)
        try:
            await handle.finish("failed", failure_code=code, failure_reason=reason)
        except AccountRevoked:
            return False
        except Exception:
            LOGGER.error("File Meeting outcome write failed; retrying.")
            try:
                await handle.finish("failed", failure_code=code, failure_reason=reason)
            except AccountRevoked:
                return False
        return True

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
        try:
            self._record_retained_source(handle, input_path, ingress="url")
        except Exception:
            await self._mark_failed(handle)
            self._remove_terminal_work_dir(staging_dir)
            return
        await self._run(handle, input_path, asyncio.Event())

    async def _run(
        self,
        handle: Any,
        input_path: Path,
        started: asyncio.Event,
        *,
        resumed: bool = False,
        resume_source: _RetainedResumeSource | None = None,
    ) -> None:
        loop = asyncio.get_running_loop()
        options = self._inference_options()
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
            asyncio.to_thread(
                self._transcribe_from_one_mix,
                input_path,
                options,
                resume_source=resume_source,
            )
        )
        if self._inference_scheduler is None:
            self._set_phase(handle.meeting_id, "running")
        started.set()
        try:
            await self._complete(handle, input_path, runner_task, resumed=resumed)
        except asyncio.CancelledError:
            try:
                await runner_task
            except Exception:
                LOGGER.error("File Meeting runner failed during shutdown.")
            raise
        except Exception:
            if not resumed:
                raise
            if await self._mark_failed(
                handle,
                "resume_failed",
                "Retained File restart could not finish.",
            ):
                self._remove_terminal_work_dir(input_path.parent)

    def _inference_options(self) -> dict[str, object]:
        return {
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

    def _transcribe_from_one_mix(
        self,
        input_path: Path,
        options: dict[str, object],
        *,
        resume_source: _RetainedResumeSource | None = None,
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
        checkpoint_bound = bool(
            resume_source is not None and resume_source.checkpoint_bound
        )
        mix_path = resume_source.mix_path if checkpoint_bound else None
        mix_failed = bool(
            checkpoint_bound
            and resume_source is not None
            and resume_source.mix_path is None
        )
        if self._audio_archive is not None and not checkpoint_bound:
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
        *,
        resumed: bool = False,
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
            if not document["segments"] and not accepted_speechless(result):
                raise ValueError("Empty decoder output without speechless evidence")
        except Exception:
            await self._mark_failed(handle, "decode_invalid", "The speech decoder returned no usable transcript.")
            self._remove_terminal_work_dir(input_path.parent)
            return

        try:
            if not resumed or (await handle.snapshot()).transcript != document:
                await handle.commit_transcript(document)
        except AccountRevoked:
            # Revocation/interruption is already the durable terminal authority. A late result
            # must disappear rather than reconstructing a handle from its Meeting identifier.
            self._remove_terminal_work_dir(input_path.parent)
            return
        except Exception:
            if resumed:
                await self._mark_failed(
                    handle,
                    "resume_failed",
                    "Retained File restart could not finish.",
                )
            else:
                await self._mark_failed(handle)
            self._remove_terminal_work_dir(input_path.parent)
            if not resumed:
                raise
            return

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
            if resumed:
                await self._mark_failed(
                    handle,
                    "resume_failed",
                    "Retained File restart could not finish.",
                )
            else:
                await self._mark_failed(handle)
            self._remove_terminal_work_dir(input_path.parent)
            if not resumed:
                raise
            return

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
            if resumed:
                await handle.record_terminal_failure(
                    "resume_failed",
                    "Retained File restart could not finish.",
                )
                return
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
