"""Lead-review controls for retained restart source binding."""

from __future__ import annotations

import asyncio
import io
import json
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from _browser_workspace_fixtures import seed_workspace

from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.phase2 import Phase2Store
from moss_transcribe_diarize.app.phase2_audio import PublishedMeetingAudio
from moss_transcribe_diarize.app.phase2_file import (
    RETAINED_FILE_WORK_CONTRACT_VERSION,
    FileMeetingTasks,
)
from moss_transcribe_diarize.app.windowed_transcription import (
    _CheckpointStore,
    _checkpoint_inference,
    WindowedRunner,
    plan_windows,
)


REVIEW_XFAIL = pytest.mark.xfail(
    strict=True,
    reason="lead review 9de2d9fc: retained resume binding not implemented",
)


def _wav(*, silent: bool) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        sample = b"\x00\x00" if silent else b"\x01\x00"
        audio.writeframes(sample * 160)
    return output.getvalue()


class _RecordingDecoder:
    model_path = "retained-resume-binding-control"

    def __init__(self) -> None:
        self.paths: list[Path] = []
        self.payloads: list[bytes] = []

    def transcribe(self, audio_path: str | Path, **_kwargs: object) -> TranscriptionResult:
        path = Path(audio_path)
        self.paths.append(path)
        self.payloads.append(path.read_bytes())
        return TranscriptionResult(
            text="[0][S01]same retained transcript[1]",
            prompt_len=1,
            generated_tokens=1,
            elapsed_sec=0.0,
            model=self.model_path,
            audio=str(path),
            decoding="greedy",
            temperature=None,
        )


class _RecordingArchive:
    def __init__(self, root: Path, *, silent: bool = False) -> None:
        self.root = root
        self.mix_bytes = _wav(silent=silent)
        self.prepare_sources: list[bytes] = []
        self.published_sources: list[bytes] = []

    def prepare_mix(
        self,
        source: Path,
        destination: Path,
        *,
        notices: list[str],
    ) -> Path:
        del notices
        self.prepare_sources.append(source.read_bytes())
        destination.write_bytes(self.mix_bytes)
        return destination

    def publish(
        self,
        account_id: str,
        meeting_id: str,
        source: Path,
    ) -> PublishedMeetingAudio:
        payload = source.read_bytes()
        self.published_sources.append(payload)
        path = self.root / account_id / meeting_id / "audio.mp3"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return PublishedMeetingAudio(
            path=path,
            relative_path=path.relative_to(self.root).as_posix(),
            byte_count=len(payload),
            duration_ms=10,
        )

    def discard(self, publication: PublishedMeetingAudio) -> None:
        publication.path.unlink(missing_ok=True)

    def discard_staged(self, _account_id: str, _meeting_id: str) -> None:
        return None

    def discard_unrecorded(self, account_id: str, meeting_id: str) -> None:
        directory = self.root / account_id / meeting_id
        for name in (".audio.staged.mp3", "audio.mp3", "audio.partial.mp3"):
            (directory / name).unlink(missing_ok=True)

    def resolve(
        self,
        account_id: str,
        meeting_id: str,
        relative_path: str,
        byte_count: int,
    ) -> Path | None:
        path = self.root / relative_path
        expected = self.root / account_id / meeting_id / path.name
        return path if path == expected and path.is_file() and path.stat().st_size == byte_count else None


def _runner(decoder: _RecordingDecoder, duration: float) -> WindowedRunner:
    def extract(
        _source: str | Path,
        destination: str | Path,
        *,
        start_seconds: float,
        duration_seconds: float,
    ) -> None:
        Path(destination).write_text(
            f"{start_seconds}:{duration_seconds}\n", encoding="utf-8"
        )

    return WindowedRunner(
        decoder,
        duration_probe=lambda _source: duration,
        window_extractor=extract,
    )


async def _active_handle(store: Phase2Store, subject: str = "account-a"):
    account, _ = await seed_workspace(store, subject)
    return account, await store.workspace(account).create_meeting("file")


def _retained_owner(tasks: FileMeetingTasks, account: object, handle: object) -> tuple[Path, Path]:
    owner_dir = tasks.retained_root / account.account_id / handle.meeting_id
    owner_dir.mkdir(parents=True)
    source = owner_dir / "input.media"
    source.write_bytes(b"raw retained upload")
    (owner_dir / "checkpoint").mkdir()
    (owner_dir / "owner.json").write_text(
        json.dumps(
            {
                "account_id": account.account_id,
                "meeting_id": handle.meeting_id,
                "ingress": "file",
                "source": source.name,
                "checkpoint": "checkpoint",
                "contract_version": RETAINED_FILE_WORK_CONTRACT_VERSION,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return owner_dir, source


def _bind_checkpoint(tasks: FileMeetingTasks, runner: WindowedRunner, source: Path, duration: float) -> None:
    _CheckpointStore(
        source.parent / "checkpoint",
        source=source,
        windows=plan_windows(duration),
        model_path=runner.model_path,
        inference=_checkpoint_inference(tasks._inference_options()),
        window_seconds=float(runner.window_seconds),
        stride_seconds=float(runner.stride_seconds),
        identity_contract=runner.identity_resolver.contract(),
    )


async def _await_claim(tasks: FileMeetingTasks, handle: object) -> None:
    assert await tasks.claim_retained_work(handle) is True
    await tasks._tasks[handle.meeting_id].task


@REVIEW_XFAIL
def test_single_window_unbound_restart_prepares_mix_and_matches_fresh(tmp_path: Path) -> None:
    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            account, fresh = await _active_handle(store)
            resumed = await store.workspace(account).create_meeting("file")
            decoder = _RecordingDecoder()
            archive = _RecordingArchive(tmp_path / "meeting-audio")
            tasks = FileMeetingTasks(
                _runner(decoder, 100.0),
                tmp_path / "file-work",
                audio_archive=archive,
            )

            fresh_dir = tasks.work_root / "fresh"
            fresh_dir.mkdir(parents=True)
            fresh_source = fresh_dir / "input.media"
            fresh_source.write_bytes(b"raw retained upload")
            await tasks._run(fresh, fresh_source, asyncio.Event())
            _retained_owner(tasks, account, resumed)
            await _await_claim(tasks, resumed)

            fresh_snapshot = await fresh.snapshot()
            resumed_snapshot = await resumed.snapshot()
            assert archive.prepare_sources == [b"raw retained upload"] * 2
            assert decoder.payloads == [archive.mix_bytes] * 2
            assert (fresh_snapshot.status, resumed_snapshot.status) == ("completed", "completed")
            assert fresh_snapshot.transcript == resumed_snapshot.transcript
            assert fresh_snapshot.audio is not None and fresh_snapshot.audio.state == "available"
            assert resumed_snapshot.audio is not None and resumed_snapshot.audio.state == "available"
            assert archive.published_sources == [archive.mix_bytes] * 2
        finally:
            await store.close()

    asyncio.run(exercise())


@REVIEW_XFAIL
def test_single_window_silent_unbound_restart_never_calls_decoder(tmp_path: Path) -> None:
    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            account, handle = await _active_handle(store)
            decoder = _RecordingDecoder()
            archive = _RecordingArchive(tmp_path / "meeting-audio", silent=True)
            tasks = FileMeetingTasks(
                _runner(decoder, 100.0),
                tmp_path / "file-work",
                audio_archive=archive,
            )
            _retained_owner(tasks, account, handle)
            await _await_claim(tasks, handle)
            snapshot = await handle.snapshot()
            assert len(archive.prepare_sources) == 1
            assert decoder.paths == []
            assert snapshot.status == "completed"
            assert snapshot.audio is not None and snapshot.audio.state == "available"
        finally:
            await store.close()

    asyncio.run(exercise())


@REVIEW_XFAIL
def test_multi_window_empty_checkpoint_restart_matches_fresh(tmp_path: Path) -> None:
    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            account, fresh = await _active_handle(store)
            resumed = await store.workspace(account).create_meeting("file")
            decoder = _RecordingDecoder()
            archive = _RecordingArchive(tmp_path / "meeting-audio")
            tasks = FileMeetingTasks(
                _runner(decoder, 390.0),
                tmp_path / "file-work",
                audio_archive=archive,
            )
            fresh_dir = tasks.work_root / "fresh"
            fresh_dir.mkdir(parents=True)
            fresh_source = fresh_dir / "input.media"
            fresh_source.write_bytes(b"raw retained upload")
            await tasks._run(fresh, fresh_source, asyncio.Event())
            _retained_owner(tasks, account, resumed)
            await _await_claim(tasks, resumed)
            fresh_snapshot = await fresh.snapshot()
            resumed_snapshot = await resumed.snapshot()
            assert archive.prepare_sources == [b"raw retained upload"] * 2
            assert fresh_snapshot.status == resumed_snapshot.status == "completed"
            assert fresh_snapshot.transcript == resumed_snapshot.transcript
            assert archive.published_sources == [archive.mix_bytes] * 2
        finally:
            await store.close()

    asyncio.run(exercise())


def test_mix_bound_restart_reuses_validated_mix_and_publishes_it(tmp_path: Path) -> None:
    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            account, handle = await _active_handle(store)
            decoder = _RecordingDecoder()
            runner = _runner(decoder, 100.0)
            archive = _RecordingArchive(tmp_path / "meeting-audio")
            tasks = FileMeetingTasks(runner, tmp_path / "file-work", audio_archive=archive)
            owner_dir, _source = _retained_owner(tasks, account, handle)
            mix = owner_dir / "transcription-mix.wav"
            mix.write_bytes(_wav(silent=False))
            _bind_checkpoint(tasks, runner, mix, 100.0)
            await _await_claim(tasks, handle)
            snapshot = await handle.snapshot()
            assert archive.prepare_sources == []
            assert decoder.payloads == [_wav(silent=False)]
            assert archive.published_sources == [_wav(silent=False)]
            assert snapshot.status == "completed"
            assert snapshot.audio is not None and snapshot.audio.state == "available"
        finally:
            await store.close()

    asyncio.run(exercise())


def test_input_bound_restart_reuses_input_and_keeps_audio_unavailable(tmp_path: Path) -> None:
    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            account, handle = await _active_handle(store)
            decoder = _RecordingDecoder()
            runner = _runner(decoder, 100.0)
            archive = _RecordingArchive(tmp_path / "meeting-audio")
            tasks = FileMeetingTasks(runner, tmp_path / "file-work", audio_archive=archive)
            _owner_dir, source = _retained_owner(tasks, account, handle)
            _bind_checkpoint(tasks, runner, source, 100.0)
            await _await_claim(tasks, handle)
            snapshot = await handle.snapshot()
            assert archive.prepare_sources == []
            assert decoder.payloads == [b"raw retained upload"]
            assert archive.published_sources == []
            assert snapshot.status == "completed"
            assert snapshot.audio is not None and snapshot.audio.state == "unavailable"
        finally:
            await store.close()

    asyncio.run(exercise())


@REVIEW_XFAIL
def test_retained_validation_uses_short_exponential_backoff(tmp_path: Path, monkeypatch) -> None:
    async def exercise() -> None:
        tasks = FileMeetingTasks(object(), tmp_path / "file-work")
        handle = SimpleNamespace(owner_key=("account-a", 1), meeting_id="meeting-a")
        owner_dir = tasks.retained_root / "account-a" / "meeting-a"
        owner_dir.mkdir(parents=True)
        (owner_dir / "owner.json").write_text("{}\n", encoding="utf-8")
        delays: list[float] = []

        def fail_validation(*_args: object) -> None:
            raise OSError("controlled transient validation failure")

        async def record_sleep(delay: float) -> None:
            delays.append(delay)

        tasks._verified_retained_resume_source = fail_validation
        monkeypatch.setattr("moss_transcribe_diarize.app.phase2_file.asyncio.sleep", record_sleep)
        with pytest.raises(Exception, match="controlled transient"):
            await tasks.claim_retained_work(handle)
        assert delays == [0.5, 1.0]

    asyncio.run(exercise())


@REVIEW_XFAIL
def test_bound_source_is_hashed_once_by_resolver_plus_once_by_validator(
    tmp_path: Path,
    monkeypatch,
) -> None:
    decoder = _RecordingDecoder()
    runner = _runner(decoder, 100.0)
    tasks = FileMeetingTasks(runner, tmp_path / "file-work")
    handle = SimpleNamespace(owner_key=("account-a", 1), meeting_id="meeting-a")
    account = SimpleNamespace(account_id="account-a")
    owner_dir, source = _retained_owner(tasks, account, handle)
    _bind_checkpoint(tasks, runner, source, 100.0)
    binary_reads = 0
    original_open = Path.open

    def counted_open(path: Path, mode: str = "r", *args: object, **kwargs: object):
        nonlocal binary_reads
        if path == source and mode == "rb":
            binary_reads += 1
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counted_open)
    verified = tasks._verified_retained_resume_source(handle, owner_dir)
    assert getattr(verified, "source", verified) == source
    assert binary_reads == 2


@REVIEW_XFAIL
def test_registration_failure_reports_general_restart_failure(tmp_path: Path) -> None:
    async def exercise() -> None:
        decoder = _RecordingDecoder()
        runner = _runner(decoder, 100.0)
        archive = _RecordingArchive(tmp_path / "meeting-audio")
        tasks = FileMeetingTasks(runner, tmp_path / "file-work", audio_archive=archive)
        reasons: list[str] = []

        class Handle:
            owner_key = ("account-a", 1)
            meeting_id = "meeting-a"
            status = "active"

            async def recover_interrupted_file_audio(self, _archive: object) -> None:
                return None

            async def finish(self, status: str, **kwargs: object) -> None:
                self.status = status
                reasons.append(str(kwargs.get("failure_reason")))

            async def snapshot(self):
                return SimpleNamespace(status=self.status)

        handle = Handle()
        account = SimpleNamespace(account_id="account-a")
        _retained_owner(tasks, account, handle)

        def fail_registration(_handle: object, task: asyncio.Task, **_kwargs: object) -> None:
            task.cancel()
            raise RuntimeError("controlled task registration failure")

        tasks._register = fail_registration

        class Store:
            async def active_file_meetings(self):
                return (handle,)

        await tasks.resume_retained_work(Store())
        await tasks._retained_resume_task
        assert reasons == ["Retained File restart could not finish."]

    asyncio.run(exercise())
