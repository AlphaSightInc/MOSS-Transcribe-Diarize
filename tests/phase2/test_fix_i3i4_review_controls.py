"""Strict violating controls copied from the two closure reviews."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from _browser_workspace_fixtures import seed_workspace
from test_retained_file_claim import (
    _RestartDecoder,
    _app,
    _extract,
    _runner,
    _seed_retained_claim,
    _snapshot,
)

from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.phase2 import Phase2Store
from moss_transcribe_diarize.app.phase2_file import (
    RETAINED_FILE_WORK_CONTRACT_VERSION,
    FileProcessingError,
    FileMeetingTasks,
)
from moss_transcribe_diarize.app.phase2_lifecycle import MeetingLifecycleSettlementError
from moss_transcribe_diarize.app.windowed_transcription import (
    _CheckpointStore,
    _checkpoint_inference,
    WindowedRunner,
    WindowTranscriptionError,
    plan_windows,
)
from moss_transcribe_diarize.subtitle import subtitle_segments_from_transcript


class _Delegate:
    model_path = "closure-review-model"


@pytest.mark.xfail(strict=True, reason="F1: restart validates the original input, not the checkpoint source")
def test_retained_normalized_mix_checkpoint_is_accepted_on_restart(
    tmp_path: Path,
) -> None:
    """A production-created mix checkpoint must not be rejected as wrong-source."""

    runner = WindowedRunner(
        _Delegate(),
        duration_probe=lambda _source: 180.0,
    )
    tasks = FileMeetingTasks(runner, tmp_path / "file-work")
    handle = SimpleNamespace(owner_key=("account-a", 1), meeting_id="meeting-a")
    owner_dir = tasks.retained_root / "account-a" / "meeting-a"
    owner_dir.mkdir(parents=True)
    retained_input = owner_dir / "input.media"
    retained_input.write_bytes(b"original retained container")
    normalized_mix = owner_dir / "transcription-mix.wav"
    normalized_mix.write_bytes(b"normalized production PCM")
    (owner_dir / "owner.json").write_text(
        json.dumps(
            {
                "account_id": "account-a",
                "meeting_id": "meeting-a",
                "ingress": "file",
                "source": retained_input.name,
                "checkpoint": "checkpoint",
                "contract_version": RETAINED_FILE_WORK_CONTRACT_VERSION,
            }
        ),
        encoding="utf-8",
    )

    windows = plan_windows(180.0)
    inference = _checkpoint_inference(tasks._inference_options())
    checkpoint = _CheckpointStore(
        owner_dir / "checkpoint",
        source=normalized_mix,
        windows=windows,
        model_path=runner.model_path,
        inference=inference,
        window_seconds=float(runner.window_seconds),
        stride_seconds=float(runner.stride_seconds),
        identity_contract=runner.identity_resolver.contract(),
    )
    checkpoint.commit_window(
        windows[0],
        TranscriptionResult(
            text="[0][S01]preserved prefix[1]",
            prompt_len=1,
            generated_tokens=1,
            elapsed_sec=0.0,
            model=runner.model_path,
            audio=str(normalized_mix),
            decoding="greedy",
            temperature=None,
        ),
        possibly_truncated=False,
    )

    runner.bind_resume_inference(tasks._inference_options())
    assert runner.validate_resume(normalized_mix, owner_dir / "checkpoint").accepted
    assert tasks._verified_retained_input(handle, owner_dir) == retained_input


@pytest.mark.xfail(strict=True, reason="F2: validation I/O errors are misclassified as refusal")
def test_resume_validation_io_error_is_not_checkpoint_refusal(tmp_path: Path) -> None:
    """An unavailable validator is not evidence that an honest prefix is invalid."""

    source = tmp_path / "input.wav"
    source.write_bytes(b"honest source")
    checkpoint_dir = tmp_path / "checkpoint"
    inference = _checkpoint_inference({})
    windows = plan_windows(180.0)
    healthy = WindowedRunner(
        _Delegate(),
        duration_probe=lambda _source: 180.0,
        resume_inference=inference,
    )
    _CheckpointStore(
        checkpoint_dir,
        source=source,
        windows=windows,
        model_path=healthy.model_path,
        inference=inference,
        window_seconds=float(healthy.window_seconds),
        stride_seconds=float(healthy.stride_seconds),
        identity_contract=healthy.identity_resolver.contract(),
    )

    def unavailable_probe(_source: Path) -> float:
        raise OSError("controlled validator I/O failure")

    unavailable = WindowedRunner(
        _Delegate(),
        duration_probe=unavailable_probe,
        resume_inference=inference,
    )
    verdict = unavailable.validate_resume(source, checkpoint_dir)

    assert verdict.status != "refused", verdict.reason


@pytest.mark.xfail(strict=True, reason="T1/A-1: fallback owner survives the boot that interrupts it")
def test_t1_nonresumable_owner_dir_is_reclaimed_in_the_boot_that_interrupts_it(tmp_path):
    async def exercise():
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            account, _ = await seed_workspace(store, "account-a")
            handle = await store.workspace(account).create_meeting("file")
        finally:
            await store.close()
        owner_dir = tmp_path / "file-retained" / account.account_id / handle.meeting_id
        owner_dir.mkdir(parents=True)
        (owner_dir / "input.wav").write_bytes(b"raw user media (URL mid-download shape)")
        decoder = _RestartDecoder()
        decoder.fail_window = None
        app = _app(tmp_path, decoder)
        async with app.router.lifespan_context(app):
            tasks = app.state.phase2_file_tasks
            coordinator = getattr(tasks, "_retained_resume_task", None)
            if coordinator is not None:
                await coordinator
            snapshot = await _snapshot(app, handle)
            assert snapshot.status == "interrupted"
            assert decoder.calls == []
            survived_first_boot = owner_dir.exists()
        app2 = _app(tmp_path, _RestartDecoder())
        async with app2.router.lifespan_context(app2):
            survived_second_boot = owner_dir.exists()
        return survived_first_boot, survived_second_boot

    first, second = asyncio.run(exercise())
    assert first is False, "terminal owner dir must be reclaimed in the boot that made it terminal"


@pytest.mark.xfail(strict=True, reason="T2/A-2: reserved owner is invisible to operator interrupt")
def test_t2_operator_interrupt_is_refused_while_a_reserved_owner_is_being_validated(tmp_path):
    async def exercise():
        _tasks, handle, decoder, _owner_dir, store = await _seed_retained_claim(tmp_path)
        await store.close()
        entered = threading.Event()
        release = threading.Event()
        original = FileMeetingTasks._verified_retained_input

        def held(self, h, d):
            entered.set()
            release.wait(5)
            return original(self, h, d)

        FileMeetingTasks._verified_retained_input = held
        try:
            decoder.block_window = 2
            app = _app(tmp_path, decoder)
            async with app.router.lifespan_context(app):
                assert await asyncio.to_thread(entered.wait, 2)
                lifecycle = app.state.phase2_lifecycle
                try:
                    await lifecycle.interrupt_meeting(handle.meeting_id)
                    outcome_during = "honoured"
                except MeetingLifecycleSettlementError as exc:
                    outcome_during = f"REFUSED: {exc}"
                release.set()
                await app.state.phase2_file_tasks._retained_resume_task
                await asyncio.to_thread(decoder.blocked.wait, 5)
                asyncio.get_running_loop().call_later(0.2, decoder.release.set)
                await lifecycle.interrupt_meeting(handle.meeting_id)
            return outcome_during
        finally:
            release.set()
            FileMeetingTasks._verified_retained_input = original

    outcome = asyncio.run(exercise())
    assert outcome == "honoured", outcome


@pytest.mark.xfail(strict=True, reason="T3/B-1: one settlement failure stops later owners")
def test_t3_one_owner_persistent_outcome_write_failure_orphans_later_reserved_owners(tmp_path):
    async def exercise():
        archive = SimpleNamespace()
        tasks = FileMeetingTasks(object(), tmp_path / "file-work", audio_archive=archive)
        finishes: list[tuple[str, str, str | None]] = []

        class Handle:
            def __init__(self, meeting_id: str, fail: bool):
                self.owner_key = ("account-a", 1)
                self.meeting_id = meeting_id
                self.fail = fail
                self.status = "active"

            async def recover_interrupted_file_audio(self, _archive):
                return None

            async def finish(self, status, **kwargs):
                finishes.append((self.meeting_id, status, kwargs.get("failure_code")))
                if self.fail:
                    raise sqlite3.OperationalError("database is locked")
                self.status = status

            async def snapshot(self):
                return SimpleNamespace(status=self.status)

        first = Handle("owner-1-invalid-db-locked", fail=True)
        second = Handle("owner-2-never-validated", fail=False)
        for handle in (first, second):
            owner_dir = tasks.retained_root / "account-a" / handle.meeting_id
            owner_dir.mkdir(parents=True)
            (owner_dir / "owner.json").write_text("{}\n", encoding="utf-8")
        validated: list[str] = []

        def validation(_self, handle, _owner_dir):
            validated.append(handle.meeting_id)
            return None

        tasks._verified_retained_input = validation.__get__(tasks)

        class Store:
            async def active_file_meetings(self):
                return (first, second)

        await tasks.resume_retained_work(Store())
        crashed = None
        try:
            await tasks._retained_resume_task
        except Exception as exc:
            crashed = repr(exc)
        return validated, crashed

    validated, crashed = asyncio.run(exercise())
    assert crashed is None and "owner-2-never-validated" in validated


class _SpeechlessThenFailDecoder:
    model_path = "review-speechless-runner"

    def __init__(self) -> None:
        self.calls: list[int] = []
        self.fail_window: int | None = 1

    def transcribe(self, audio_path, **_kwargs):
        index = int(Path(audio_path).stem.rsplit("-", 1)[1])
        self.calls.append(index)
        if index == self.fail_window:
            raise RuntimeError("controlled interruption")
        return TranscriptionResult(
            text="", prompt_len=0, generated_tokens=0, elapsed_sec=0.0,
            model=self.model_path, audio=str(audio_path), decoding="greedy", temperature=None,
            window_diagnostics=[{"condition": "speechless_window_empty", "detector": "digital_zero"}],
        )


@pytest.mark.xfail(strict=True, reason="T4/B-2: validation creates checkpoint state")
def test_t4_checkpoint_validation_honest_shapes_and_side_effects(tmp_path):
    source = tmp_path / "input.wav"
    source.write_bytes(b"retained source")
    decoder = _RestartDecoder()
    decoder.fail_window = 2
    runner = _runner(decoder)
    tasks = FileMeetingTasks(runner, tmp_path / "file-work")
    valid = tmp_path / "valid"
    with pytest.raises(WindowTranscriptionError):
        runner.transcribe(source, checkpoint_dir=valid)
    decoder.fail_window = None
    assert tasks._checkpoint_is_valid(source, valid) is True
    empty = tmp_path / "empty"
    empty.mkdir()
    assert tasks._checkpoint_is_valid(source, empty) is True
    assert not (empty / "manifest.json").exists()
    missing = tmp_path / "missing"
    tasks._checkpoint_is_valid(source, missing)
    assert not missing.exists()


class _CopyMixArchive:
    def prepare_mix(
        self,
        _source: Path,
        destination: Path,
        *,
        notices: list[str],
    ) -> Path:
        del notices
        destination.write_bytes(b"normalized production mix")
        return destination


def test_mix_bound_checkpoint_resumes_through_real_lifespan(tmp_path: Path) -> None:
    """The restart decodes only the mix windows not committed before the crash."""

    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            account, _ = await seed_workspace(store, "account-a")
            handle = await store.workspace(account).create_meeting("file")
        finally:
            await store.close()

        decoder = _RestartDecoder()
        runner = _runner(decoder)
        first_tasks = FileMeetingTasks(
            runner,
            tmp_path / "file-work",
            audio_archive=_CopyMixArchive(),
        )
        owner_dir = first_tasks.retained_root / account.account_id / handle.meeting_id
        owner_dir.mkdir(parents=True)
        source = owner_dir / "input.wav"
        source.write_bytes(b"original retained container")
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
        with pytest.raises(FileProcessingError):
            first_tasks._transcribe_from_one_mix(source, {})
        assert decoder.calls == [0, 1, 2]
        mix = owner_dir / "transcription-mix.wav"
        assert mix.is_file()

        reference_decoder = _RestartDecoder()
        reference_decoder.fail_window = None
        reference = _runner(reference_decoder).transcribe(mix)
        expected = {
            "segments": [
                segment.to_dict()
                for segment in subtitle_segments_from_transcript(
                    reference.text,
                    postprocess=False,
                )
            ]
        }

        decoder.calls.clear()
        decoder.fail_window = None
        app = _app(tmp_path, decoder)
        async with app.router.lifespan_context(app):
            await app.state.phase2_file_tasks._retained_resume_task
            entry = app.state.phase2_file_tasks._tasks.get(handle.meeting_id)
            if entry is not None:
                await entry.task
            snapshot = await _snapshot(app, handle)
            assert decoder.calls == [2, 3]
            assert snapshot.status == "completed"
            assert snapshot.transcript == expected
            assert not owner_dir.exists()

    asyncio.run(exercise())


@pytest.mark.parametrize("outcome", ["refused", "error"])
def test_reserved_terminal_validation_paths_reconcile_audio_before_cleanup(
    tmp_path: Path,
    outcome: str,
) -> None:
    async def exercise() -> None:
        events: list[str] = []

        class Handle:
            owner_key = ("account-a", 1)
            meeting_id = f"owner-{outcome}"
            status = "active"

            async def recover_interrupted_file_audio(self, _archive):
                events.append("audio")

            async def finish(self, status, **_kwargs):
                events.append(status)
                self.status = status

            async def snapshot(self):
                return SimpleNamespace(status=self.status)

        handle = Handle()
        tasks = FileMeetingTasks(
            object(),
            tmp_path / "file-work",
            audio_archive=object(),
        )
        owner_dir = tasks.retained_root / "account-a" / handle.meeting_id
        owner_dir.mkdir(parents=True)
        (owner_dir / "owner.json").write_text("{}\n", encoding="utf-8")
        attempts = 0

        def validate(_handle, _owner_dir):
            nonlocal attempts
            attempts += 1
            if outcome == "error":
                raise OSError("controlled validation I/O failure")
            return None

        tasks._verified_retained_resume_source = validate

        class Store:
            async def active_file_meetings(self):
                return (handle,)

        await tasks.resume_retained_work(Store())
        await tasks._retained_resume_task
        assert events == ["audio", "interrupted" if outcome == "refused" else "failed"]
        assert attempts == (1 if outcome == "refused" else 3)
        assert not owner_dir.exists()

    asyncio.run(exercise())


def test_reserved_fence_settles_now_but_cleans_only_after_validation_returns(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        events: list[str] = []
        entered = threading.Event()
        release = threading.Event()

        class Handle:
            owner_key = ("account-a", 1)
            meeting_id = "owner-fenced"
            status = "active"

            async def recover_interrupted_file_audio(self, _archive):
                events.append("audio")

            async def finish(self, status, **_kwargs):
                events.append(status)
                self.status = status

            async def snapshot(self):
                return SimpleNamespace(status=self.status)

        handle = Handle()
        tasks = FileMeetingTasks(
            object(),
            tmp_path / "file-work",
            audio_archive=object(),
        )
        owner_dir = tasks.retained_root / "account-a" / handle.meeting_id
        owner_dir.mkdir(parents=True)
        (owner_dir / "owner.json").write_text("{}\n", encoding="utf-8")

        def validate(_handle, directory):
            entered.set()
            release.wait()
            return directory / "input.wav"

        tasks._verified_retained_resume_source = validate

        class Store:
            async def active_file_meetings(self):
                return (handle,)

        await tasks.resume_retained_work(Store())
        assert await asyncio.to_thread(entered.wait, 1)
        assert tasks.operator_snapshot() == {handle.meeting_id: "validating"}
        reservation = tasks.fence_meeting(handle.meeting_id)
        assert reservation is not None
        assert await tasks.settle_meeting(reservation) is True
        assert events == ["audio", "interrupted"]
        assert owner_dir.exists()
        release.set()
        await tasks._retained_resume_task
        assert not owner_dir.exists()

    asyncio.run(exercise())


def test_account_revoke_does_not_reclaim_a_live_reserved_validation(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        _tasks, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        await store.close()
        decoder.calls.clear()
        entered = threading.Event()
        release = threading.Event()
        original = FileMeetingTasks._verified_retained_input

        def held(self, target, directory):
            entered.set()
            release.wait()
            return original(self, target, directory)

        FileMeetingTasks._verified_retained_input = held
        try:
            app = _app(tmp_path, decoder)
            async with app.router.lifespan_context(app):
                assert await asyncio.to_thread(entered.wait, 1)
                assert await app.state.phase2_lifecycle.revoke_account(
                    handle.owner_key[0]
                )
                assert owner_dir.exists()
                assert decoder.calls == []
                release.set()
                await app.state.phase2_file_tasks._retained_resume_task
                assert not owner_dir.exists()
        finally:
            release.set()
            FileMeetingTasks._verified_retained_input = original

    asyncio.run(exercise())
