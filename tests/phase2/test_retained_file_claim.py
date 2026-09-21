"""Product-seam controls for Meeting-owned retained File work."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import httpx
import pytest

from _browser_workspace_fixtures import seed_workspace

from moss_transcribe_diarize.app.inference_scheduler import (
    InferenceDispatchScheduler,
    ScheduledInferenceRunner,
)
from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.phase2 import MeetingHandle, Phase2Store, create_phase2_app
from moss_transcribe_diarize.app.phase2_file import (
    FileMeetingTasks,
    RetainedFileWorkBusy,
)
from moss_transcribe_diarize.app.windowed_transcription import (
    WindowTranscriptionError,
    WindowedRunner,
)


class _RestartDecoder:
    model_path = "retained-claim-test-runner"

    def __init__(self) -> None:
        self.calls: list[int] = []
        self.fail_window: int | None = 2
        self.block_window: int | None = None
        self.blocked = threading.Event()
        self.release = threading.Event()

    def transcribe(self, audio_path: str | Path, **_kwargs: object) -> TranscriptionResult:
        index = int(Path(audio_path).stem.rsplit("-", 1)[1])
        self.calls.append(index)
        if index == self.fail_window:
            raise RuntimeError("controlled restart interruption")
        if index == self.block_window:
            self.blocked.set()
            if not self.release.wait(timeout=5):
                raise RuntimeError("controlled startup did not release")
        return TranscriptionResult(
            text=f"[59][S01]window {index}[60]",
            prompt_len=1,
            generated_tokens=1,
            elapsed_sec=0.0,
            model=self.model_path,
            audio=str(audio_path),
            decoding="greedy",
            temperature=None,
        )


class _NoUrlAcquirer:
    def __init__(self) -> None:
        self.calls = 0

    async def acquire(self, *_args: object, **_kwargs: object) -> Path:
        self.calls += 1
        raise AssertionError("retained URL work must not reacquire its source")


class _HeldUrlAcquirer:
    """Deterministically hold a URL Meeting before it has a retained source."""

    def __init__(self) -> None:
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def acquire(self, *_args: object, **_kwargs: object) -> Path:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        raise AssertionError("the held URL acquisition must be cancelled")


class _CompletedUrlAcquirer:
    """Deterministically complete a URL download when the control releases it."""

    def __init__(self) -> None:
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def acquire(self, _source_url: str, directory: Path) -> Path:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        path = directory / "input.wav"
        path.write_bytes(b"downloaded URL source")
        return path


def _extract(
    _source: str | Path,
    destination: str | Path,
    *,
    start_seconds: float,
    duration_seconds: float,
) -> None:
    Path(destination).write_text(f"{start_seconds}:{duration_seconds}\n", encoding="utf-8")


def _runner(
    decoder: _RestartDecoder,
    scheduler: InferenceDispatchScheduler | None = None,
    *,
    duration_seconds: float = 390.0,
) -> WindowedRunner:
    return WindowedRunner(
        (
            decoder
            if scheduler is None
            else ScheduledInferenceRunner(decoder, scheduler, kind="background")
        ),
        duration_probe=lambda _source: duration_seconds,
        window_extractor=_extract,
    )


async def _seed_retained_claim(
    root: Path,
    *,
    duration_seconds: float = 390.0,
    interrupted_window: int = 2,
) -> tuple[FileMeetingTasks, object, _RestartDecoder, Path, Phase2Store]:
    store = await Phase2Store.open(root / "state.sqlite3")
    account, _ = await seed_workspace(store, "account-a")
    handle = await store.workspace(account).create_meeting("file")
    decoder = _RestartDecoder()
    decoder.fail_window = interrupted_window
    runner = _runner(decoder, duration_seconds=duration_seconds)
    tasks = FileMeetingTasks(runner, root / "file-work")
    owner_dir = tasks.retained_root / account.account_id / handle.meeting_id
    owner_dir.mkdir(parents=True)
    source = owner_dir / "input.wav"
    source.write_bytes(b"retained source")
    (owner_dir / "owner.json").write_text(
        json.dumps(
            {
                "account_id": account.account_id,
                "meeting_id": handle.meeting_id,
                "ingress": "file",
                "source": source.name,
                "checkpoint": "checkpoint",
                "contract_version": 1,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(WindowTranscriptionError):
        runner.transcribe(source, checkpoint_dir=owner_dir / "checkpoint")
    assert decoder.calls == list(range(interrupted_window + 1))
    decoder.fail_window = None
    return tasks, handle, decoder, owner_dir, store


async def _snapshot(app: object, handle: object) -> object:
    store = app.state.phase2_store  # type: ignore[attr-defined]
    account_id, generation = handle.owner_key  # type: ignore[attr-defined]
    reopened = MeetingHandle(store, account_id, generation, handle.meeting_id)  # type: ignore[attr-defined]
    return await reopened.snapshot()


async def _await_file_task(app: object, meeting_id: str) -> None:
    entry = app.state.phase2_file_tasks._tasks.get(meeting_id)  # type: ignore[attr-defined]
    if entry is not None:
        await entry.task


def _app(
    root: Path,
    decoder: _RestartDecoder,
    *,
    url_acquirer: object | None = None,
    inference_scheduler: InferenceDispatchScheduler | None = None,
    duration_seconds: float = 390.0,
):
    return create_phase2_app(
        database_path=root / "state.sqlite3",
        file_runner=_runner(
            decoder,
            inference_scheduler,
            duration_seconds=duration_seconds,
        ),
        file_work_root=root / "file-work",
        meeting_audio_root=root / "meeting-audio",
        inference_scheduler=inference_scheduler,
        **({"url_acquirer": url_acquirer} if url_acquirer is not None else {}),
    )


def test_retained_claim_reuses_only_the_verified_prefix(tmp_path: Path) -> None:
    async def exercise() -> None:
        tasks, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        try:
            assert await tasks.claim_retained_work(handle) is True
            await tasks._tasks[handle.meeting_id].task
            assert decoder.calls == [0, 1, 2, 2, 3]
            assert (await handle.snapshot()).status == "completed"
            assert not owner_dir.exists()
        finally:
            await store.close()

    asyncio.run(exercise())


def test_checkpoint_validation_binds_the_file_inference_contract(tmp_path: Path) -> None:
    async def exercise() -> None:
        tasks, _handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        try:
            source = owner_dir / "input.wav"
            checkpoint = owner_dir / "checkpoint"
            assert tasks._checkpoint_is_valid(source, checkpoint) is True
            tasks._prompt = "different retained inference contract"
            assert tasks._checkpoint_is_valid(source, checkpoint) is False
            assert decoder.calls == [0, 1, 2]
        finally:
            await store.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("mutation", ["owner", "source", "contract", "prefix"])
def test_retained_claim_refuses_mutated_owner_source_contract_or_prefix(
    tmp_path: Path,
    mutation: str,
) -> None:
    async def exercise() -> None:
        tasks, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        try:
            manifest_path = owner_dir / "owner.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if mutation == "owner":
                manifest["account_id"] = "other-account"
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            elif mutation == "source":
                (owner_dir / "input.wav").write_bytes(b"substituted source")
            elif mutation == "contract":
                manifest["contract_version"] = 2
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            else:
                next((owner_dir / "checkpoint" / "windows").glob("w*.json")).unlink()

            assert await tasks.claim_retained_work(handle) is False
            assert decoder.calls == [0, 1, 2]
            assert (await handle.snapshot()).status == "active"
            assert owner_dir.exists()
        finally:
            await store.close()

    asyncio.run(exercise())


def test_lifespan_replays_retained_url_only_from_its_local_copy(tmp_path: Path) -> None:
    """C7: product startup uses the retained File source, never reacquisition."""

    async def exercise() -> None:
        _, handle, decoder, owner_dir, store = await _seed_retained_claim(
            tmp_path,
            duration_seconds=12_060.0,
            interrupted_window=40,
        )
        try:
            owner = json.loads((owner_dir / "owner.json").read_text(encoding="utf-8"))
            owner["ingress"] = "url"
            (owner_dir / "owner.json").write_text(json.dumps(owner), encoding="utf-8")
        finally:
            await store.close()

        acquirer = _NoUrlAcquirer()
        app = _app(
            tmp_path,
            decoder,
            url_acquirer=acquirer,
            duration_seconds=12_060.0,
        )
        async with app.router.lifespan_context(app):
            await _await_file_task(app, handle.meeting_id)
            snapshot = await _snapshot(app, handle)
            assert decoder.calls == [*range(41), *range(40, 101)]
            assert acquirer.calls == 0
            assert snapshot.status == "completed"
            assert snapshot.transcript_version == 1
            texts = [segment["text"] for segment in snapshot.transcript["segments"]]
            assert len(texts) == len(set(texts)) == 101
            assert not owner_dir.exists()

    asyncio.run(exercise())


def test_lifespan_retries_the_uncommitted_window_after_a_prior_crash(tmp_path: Path) -> None:
    """C2: a retained prefix makes the product replay only the interrupted window."""

    async def exercise() -> None:
        _, handle, decoder, owner_dir, store = await _seed_retained_claim(
            tmp_path,
            duration_seconds=12_060.0,
            interrupted_window=40,
        )
        await store.close()

        app = _app(tmp_path, decoder, duration_seconds=12_060.0)
        async with app.router.lifespan_context(app):
            await _await_file_task(app, handle.meeting_id)
            snapshot = await _snapshot(app, handle)
            assert decoder.calls == [*range(41), *range(40, 101)]
            assert snapshot.status == "completed"
            assert snapshot.transcript_version == 1
            texts = [segment["text"] for segment in snapshot.transcript["segments"]]
            assert len(texts) == len(set(texts)) == 101
            assert not owner_dir.exists()

    asyncio.run(exercise())


def test_lifespan_cancellation_of_resumed_file_work_is_durably_cancelled(
    tmp_path: Path,
) -> None:
    """C3: cancellation during retained startup reaches terminal truth before cleanup."""

    async def exercise() -> None:
        _, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        await store.close()
        decoder.block_window = 2
        scheduler = InferenceDispatchScheduler(max_calls=1, max_background_calls=1)
        app = _app(tmp_path, decoder, inference_scheduler=scheduler)
        context = app.router.lifespan_context(app)
        startup = asyncio.create_task(context.__aenter__())
        assert await asyncio.to_thread(decoder.blocked.wait, 2)
        await asyncio.wait_for(asyncio.shield(startup), timeout=1)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://moss.test"
        ) as client:
            assert (await client.get("/")).status_code == 200
        fenced = asyncio.Event()
        original_fence = app.state.phase2_file_tasks.fence_meeting

        def observe_fence(meeting_id: str):
            entry = original_fence(meeting_id)
            if entry is not None:
                fenced.set()
            return entry

        app.state.phase2_file_tasks.fence_meeting = observe_fence
        cancellation = asyncio.create_task(
            app.state.phase2_lifecycle.interrupt_meeting(handle.meeting_id)
        )
        await asyncio.wait_for(fenced.wait(), timeout=2)
        assert handle.meeting_id in app.state.phase2_file_tasks._fenced_meeting_ids
        assert owner_dir.exists()

        decoder.release.set()
        try:
            assert await cancellation is True
            await startup
            snapshot = await _snapshot(app, handle)
            assert decoder.calls == [0, 1, 2, 2]
            assert snapshot.status == "interrupted"
            assert snapshot.failure_code == "cancelled"
            assert snapshot.transcript is None
            assert not owner_dir.exists()
        finally:
            if not startup.done():
                decoder.release.set()
                await startup
            await context.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_lifespan_records_retained_commit_failure_without_aborting_startup(
    tmp_path: Path,
) -> None:
    """C2: a retained commit failure becomes a visible terminal outcome after boot."""

    async def exercise() -> None:
        _, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        await store.close()
        commit_started = asyncio.Event()
        release_failure = asyncio.Event()
        original_commit = MeetingHandle.commit_transcript

        async def reject_commit(self, document, *, terminal=False):
            if self.meeting_id != handle.meeting_id:
                return await original_commit(self, document, terminal=terminal)
            commit_started.set()
            await release_failure.wait()
            raise RuntimeError("controlled retained commit failure")

        MeetingHandle.commit_transcript = reject_commit
        app = _app(tmp_path, decoder)
        context = app.router.lifespan_context(app)
        startup = asyncio.create_task(context.__aenter__())
        entered = False
        try:
            await asyncio.wait_for(commit_started.wait(), timeout=2)
            await asyncio.wait_for(asyncio.shield(startup), timeout=1)
            entered = True
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://moss.test"
            ) as client:
                assert (await client.get("/")).status_code == 200
            entry = app.state.phase2_file_tasks._tasks[handle.meeting_id]
            release_failure.set()
            await entry.task
            snapshot = await _snapshot(app, handle)
            assert snapshot.status == "failed"
            assert snapshot.failure_code == "resume_failed"
            assert snapshot.failure_reason == "Retained File restart could not finish."
            assert snapshot.transcript is None
            assert not owner_dir.exists()
        finally:
            release_failure.set()
            if not startup.done():
                try:
                    await startup
                except Exception:
                    pass
            if entered:
                await context.__aexit__(None, None, None)
            MeetingHandle.commit_transcript = original_commit

    asyncio.run(exercise())


def test_lifespan_retries_a_failed_last_resort_retained_outcome_write(
    tmp_path: Path,
) -> None:
    """D5: one transient last-resort failure still reaches durable terminal truth."""

    async def exercise() -> None:
        _, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        await store.close()
        finish_failed = asyncio.Event()
        original_complete = FileMeetingTasks._complete
        original_finish = MeetingHandle.finish

        async def fail_complete(self, target, input_path, runner_task, *, resumed=False):
            if target.meeting_id == handle.meeting_id:
                raise RuntimeError("controlled retained completion failure")
            return await original_complete(
                self, target, input_path, runner_task, resumed=resumed
            )

        async def fail_first_outcome(self, status, **kwargs):
            if self.meeting_id == handle.meeting_id and not finish_failed.is_set():
                finish_failed.set()
                raise RuntimeError("controlled retained outcome write failure")
            return await original_finish(self, status, **kwargs)

        FileMeetingTasks._complete = fail_complete
        MeetingHandle.finish = fail_first_outcome
        app = _app(tmp_path, decoder)
        context = app.router.lifespan_context(app)
        entered = False
        try:
            await context.__aenter__()
            entered = True
            await asyncio.wait_for(finish_failed.wait(), timeout=2)
            await asyncio.sleep(0)
            snapshot = await _snapshot(app, handle)
            assert snapshot.status == "failed"
            assert snapshot.failure_code == "resume_failed"
            assert snapshot.failure_reason == "Retained File restart could not finish."
            assert not owner_dir.exists()
        finally:
            if entered:
                await context.__aexit__(None, None, None)
            MeetingHandle.finish = original_finish
            FileMeetingTasks._complete = original_complete

    asyncio.run(exercise())


def test_lifespan_records_retained_publication_failure_without_aborting_startup(
    tmp_path: Path,
) -> None:
    """C2: a retained audio publication failure becomes a visible terminal outcome."""

    async def exercise() -> None:
        _, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        await store.close()
        publication_started = asyncio.Event()
        release_failure = asyncio.Event()
        original_publish = MeetingHandle.record_audio_unavailable

        async def reject_publication(self):
            if self.meeting_id != handle.meeting_id:
                return await original_publish(self)
            publication_started.set()
            await release_failure.wait()
            raise RuntimeError("controlled retained publication failure")

        MeetingHandle.record_audio_unavailable = reject_publication
        app = _app(tmp_path, decoder)
        context = app.router.lifespan_context(app)
        startup = asyncio.create_task(context.__aenter__())
        entered = False
        try:
            await asyncio.wait_for(publication_started.wait(), timeout=2)
            await asyncio.wait_for(asyncio.shield(startup), timeout=1)
            entered = True
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://moss.test"
            ) as client:
                assert (await client.get("/")).status_code == 200
            entry = app.state.phase2_file_tasks._tasks[handle.meeting_id]
            release_failure.set()
            await entry.task
            snapshot = await _snapshot(app, handle)
            assert snapshot.status == "failed"
            assert snapshot.failure_code == "resume_failed"
            assert snapshot.failure_reason == "Retained File restart could not finish."
            assert snapshot.transcript_version == 1
            assert not owner_dir.exists()
        finally:
            release_failure.set()
            if not startup.done():
                try:
                    await startup
                except Exception:
                    pass
            if entered:
                await context.__aexit__(None, None, None)
            MeetingHandle.record_audio_unavailable = original_publish

    asyncio.run(exercise())


def test_lifespan_records_retained_cleanup_failure_without_aborting_startup(
    tmp_path: Path,
) -> None:
    """C2: terminal cleanup failure remains visible without reopening the Meeting."""

    async def exercise() -> None:
        _, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        await store.close()
        original_remove = FileMeetingTasks._remove_terminal_work_dir

        def fail_remove(self, work_dir):
            if work_dir == owner_dir:
                raise RuntimeError("controlled retained cleanup failure")
            original_remove(self, work_dir)

        FileMeetingTasks._remove_terminal_work_dir = fail_remove
        app = _app(tmp_path, decoder)
        context = app.router.lifespan_context(app)
        entered = False
        try:
            await context.__aenter__()
            entered = True
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://moss.test"
            ) as client:
                assert (await client.get("/")).status_code == 200
            await _await_file_task(app, handle.meeting_id)
            snapshot = await _snapshot(app, handle)
            assert snapshot.status == "completed"
            assert snapshot.transcript_version == 1
            assert snapshot.failure_code == "resume_failed"
            assert snapshot.failure_reason == "Retained File restart could not finish."
            assert snapshot.needs_review is True
            assert owner_dir.exists()
        finally:
            if entered:
                await context.__aexit__(None, None, None)
            FileMeetingTasks._remove_terminal_work_dir = original_remove

    asyncio.run(exercise())


def test_lifespan_refuses_missing_retained_url_copy_without_decoder_dispatch(
    tmp_path: Path,
) -> None:
    """C3: refused retained input is removed only after fallback terminal truth."""

    async def exercise() -> None:
        _, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        try:
            owner = json.loads((owner_dir / "owner.json").read_text(encoding="utf-8"))
            owner["ingress"] = "url"
            (owner_dir / "owner.json").write_text(json.dumps(owner), encoding="utf-8")
            (owner_dir / "input.wav").unlink()
        finally:
            await store.close()

        acquirer = _NoUrlAcquirer()
        app = _app(tmp_path, decoder, url_acquirer=acquirer)
        sibling_dir = owner_dir.parent / "unrelated-meeting"
        sibling_dir.mkdir()
        sibling_marker = sibling_dir / "preserve"
        sibling_marker.write_text("unrelated retained work", encoding="utf-8")
        terminal_statuses: list[str] = []
        removal_statuses: list[str] = []
        original_finish = MeetingHandle.finish
        original_remove = FileMeetingTasks._remove_terminal_work_dir

        async def observe_finish(self, status, **kwargs):
            await original_finish(self, status, **kwargs)
            if self.meeting_id == handle.meeting_id:
                terminal_statuses.append((await self.snapshot()).status)

        def observe_remove(self, work_dir):
            if work_dir == owner_dir:
                removal_statuses.extend(terminal_statuses)
            original_remove(self, work_dir)

        MeetingHandle.finish = observe_finish
        FileMeetingTasks._remove_terminal_work_dir = observe_remove
        try:
            async with app.router.lifespan_context(app):
                snapshot = await _snapshot(app, handle)
                assert decoder.calls == [0, 1, 2]
                assert acquirer.calls == 0
                assert snapshot.status == "interrupted"
                assert snapshot.transcript is None
                assert not owner_dir.exists()
                assert removal_statuses == ["interrupted"]
                assert sibling_marker.read_text(encoding="utf-8") == "unrelated retained work"
        finally:
            FileMeetingTasks._remove_terminal_work_dir = original_remove
            MeetingHandle.finish = original_finish

    asyncio.run(exercise())


def test_url_cancellation_reclaims_only_its_terminal_retained_directory(
    tmp_path: Path,
) -> None:
    """C3: cancelling an in-flight URL acquisition reclaims only its terminal owner."""

    async def exercise() -> None:
        acquirer = _HeldUrlAcquirer()
        app = _app(tmp_path, _RestartDecoder(), url_acquirer=acquirer)
        async with app.router.lifespan_context(app):
            store = app.state.phase2_store
            account, _ = await seed_workspace(store, "account-a")
            handle = await app.state.phase2_file_tasks.accept_url(
                store.workspace(account),
                "https://example.test/input.wav",
            )
            await asyncio.wait_for(acquirer.started.wait(), timeout=2)
            owner_dir = (
                app.state.phase2_file_tasks.retained_root
                / account.account_id
                / handle.meeting_id
            )
            sibling_dir = owner_dir.parent / "unrelated-meeting"
            sibling_dir.mkdir()
            sibling_marker = sibling_dir / "preserve"
            sibling_marker.write_text("unrelated retained work", encoding="utf-8")

            assert owner_dir.is_dir()
            assert await app.state.phase2_lifecycle.interrupt_meeting(handle.meeting_id)

            snapshot = await _snapshot(app, handle)
            assert acquirer.calls == 1
            assert snapshot.status == "interrupted"
            assert snapshot.transcript is None
            assert not owner_dir.exists()
            assert sibling_marker.read_text(encoding="utf-8") == "unrelated retained work"

    asyncio.run(exercise())


def test_url_retained_source_failure_becomes_visible_terminal_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C4: persistence failure after download cannot leave an active taskless Meeting."""

    async def exercise() -> None:
        acquirer = _CompletedUrlAcquirer()
        decoder = _RestartDecoder()
        app = _app(tmp_path, decoder, url_acquirer=acquirer)

        def reject_recorded_source(self, handle, input_path, *, ingress):
            raise OSError("controlled retained source persistence failure")

        monkeypatch.setattr(
            FileMeetingTasks, "_record_retained_source", reject_recorded_source
        )
        async with app.router.lifespan_context(app):
            store = app.state.phase2_store
            account, _ = await seed_workspace(store, "account-a")
            handle = await app.state.phase2_file_tasks.accept_url(
                store.workspace(account),
                "https://example.test/input.wav",
            )
            await asyncio.wait_for(acquirer.started.wait(), timeout=2)
            owner_dir = (
                app.state.phase2_file_tasks.retained_root
                / account.account_id
                / handle.meeting_id
            )
            sibling_dir = owner_dir.parent / "unrelated-meeting"
            sibling_dir.mkdir()
            sibling_marker = sibling_dir / "preserve"
            sibling_marker.write_text("unrelated retained work", encoding="utf-8")
            task = app.state.phase2_file_tasks._tasks[handle.meeting_id].task

            acquirer.release.set()
            await task

            snapshot = await _snapshot(app, handle)
            assert acquirer.calls == 1
            assert decoder.calls == []
            assert snapshot.status == "failed"
            assert snapshot.failure_code == "storage_failed"
            assert snapshot.failure_reason == "The meeting could not be saved."
            assert snapshot.transcript is None
            assert not owner_dir.exists()
            assert sibling_marker.read_text(encoding="utf-8") == "unrelated retained work"

    asyncio.run(exercise())


def test_account_revocation_does_not_resume_retained_file_work(
    tmp_path: Path,
) -> None:
    """D1: revocation releases only its terminal retained File owner."""

    async def exercise() -> None:
        decoder = _RestartDecoder()
        decoder.fail_window = None
        app = _app(tmp_path, decoder)
        async with app.router.lifespan_context(app):
            store = app.state.phase2_store
            account, _ = await seed_workspace(store, "account-a")
            handle = await store.workspace(account).create_meeting("file")
            owner_dir = (
                app.state.phase2_file_tasks.retained_root
                / account.account_id
                / handle.meeting_id
            )
            owner_dir.mkdir(parents=True)
            source = owner_dir / "input.wav"
            source.write_bytes(b"retained source")
            (owner_dir / "checkpoint").mkdir()
            (owner_dir / "owner.json").write_text(
                json.dumps(
                    {
                        "account_id": account.account_id,
                        "meeting_id": handle.meeting_id,
                        "ingress": "file",
                        "source": source.name,
                        "checkpoint": "checkpoint",
                        "contract_version": 1,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            sibling_meeting_marker = owner_dir.parent / "unrelated-meeting" / "marker"
            sibling_meeting_marker.parent.mkdir()
            sibling_meeting_marker.write_text("unrelated retained work", encoding="utf-8")
            sibling_account, _ = await seed_workspace(store, "account-b")
            sibling_handle = await store.workspace(sibling_account).create_meeting("file")
            sibling_account_marker = (
                app.state.phase2_file_tasks.retained_root
                / sibling_account.account_id
                / sibling_handle.meeting_id
                / "marker"
            )
            sibling_account_marker.parent.mkdir(parents=True)
            sibling_account_marker.write_text("unrelated retained work", encoding="utf-8")
            await sibling_handle.finish("interrupted")
            crashed = _RestartDecoder()
            with pytest.raises(WindowTranscriptionError):
                _runner(crashed).transcribe(source, checkpoint_dir=owner_dir / "checkpoint")
            assert crashed.calls == [0, 1, 2]
            assert sorted(path.name for path in owner_dir.iterdir()) == [
                "checkpoint", "input.wav", "owner.json",
            ]

            assert await app.state.phase2_lifecycle.revoke_account(account.account_id)
            assert (account.account_id, account.authority_generation) in (
                app.state.phase2_file_tasks._fenced_owner_keys
            )
            async with store._external_read():
                cursor = await store._connection.execute(
                    "SELECT status, version FROM meetings m "
                    "LEFT JOIN meeting_transcripts t "
                    "ON t.account_id = m.account_id AND t.meeting_id = m.meeting_id "
                    "WHERE m.meeting_id = ?",
                    (handle.meeting_id,),
                )
                row = await cursor.fetchone()
                await cursor.close()
            assert decoder.calls == []
            assert tuple(row) == ("interrupted", None)
            assert not owner_dir.exists()
            assert sibling_meeting_marker.read_text(encoding="utf-8") == "unrelated retained work"
            assert sibling_account_marker.read_text(encoding="utf-8") == "unrelated retained work"

    asyncio.run(exercise())


def test_lifespan_reclaims_disabled_account_terminal_retained_work(
    tmp_path: Path,
) -> None:
    """D1: startup reclaims terminal retained work an earlier revoke left behind."""

    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            account, _ = await seed_workspace(store, "account-a")
            handle = await store.workspace(account).create_meeting("file")
            owner_dir = tmp_path / "file-retained" / account.account_id / handle.meeting_id
            owner_dir.mkdir(parents=True)
            (owner_dir / "input.wav").write_bytes(b"retained source")
            (owner_dir / "checkpoint").mkdir()
            (owner_dir / "owner.json").write_text("retained owner", encoding="utf-8")
            sibling_meeting_marker = owner_dir.parent / "unrelated-meeting" / "marker"
            sibling_meeting_marker.parent.mkdir()
            sibling_meeting_marker.write_text("unrelated retained work", encoding="utf-8")
            sibling_account_marker = (
                tmp_path / "file-retained" / "unrelated-account" / "unrelated-meeting" / "marker"
            )
            sibling_account_marker.parent.mkdir(parents=True)
            sibling_account_marker.write_text("unrelated retained work", encoding="utf-8")
            await handle.finish("interrupted")
            assert await store.revoke_account(account.account_id)
        finally:
            await store.close()

        app = _app(tmp_path, _RestartDecoder())
        async with app.router.lifespan_context(app):
            assert not owner_dir.exists()
            assert sibling_meeting_marker.read_text(encoding="utf-8") == "unrelated retained work"
            assert sibling_account_marker.read_text(encoding="utf-8") == "unrelated retained work"

    asyncio.run(exercise())


def test_lifespan_refuses_nonresumable_file_and_live_rows_without_dispatch(
    tmp_path: Path,
) -> None:
    """C9/C10: invalid File and every Live row remain the generic fallback's job."""

    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            account, _ = await seed_workspace(store, "account-a")
            file_handle = await store.workspace(account).create_meeting("file")
            live_handle = await store.workspace(account).create_meeting("live")
        finally:
            await store.close()

        decoder = _RestartDecoder()
        decoder.fail_window = None
        app = _app(tmp_path, decoder)
        async with app.router.lifespan_context(app):
            file_snapshot = await _snapshot(app, file_handle)
            live_snapshot = await _snapshot(app, live_handle)
            assert decoder.calls == []
            assert file_snapshot.status == "interrupted"
            assert file_snapshot.transcript is None
            assert live_snapshot.status == "interrupted"
            assert live_snapshot.transcript is None

    asyncio.run(exercise())


def test_lifespan_refuses_a_competing_retained_work_owner(tmp_path: Path) -> None:
    """C4: a second real lifespan cannot dispatch or recover the first owner's Meeting."""

    async def exercise() -> None:
        _, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        await store.close()
        decoder.block_window = 2
        first = _app(tmp_path, decoder)
        first_context = first.router.lifespan_context(first)
        first_startup = asyncio.create_task(first_context.__aenter__())
        assert await asyncio.to_thread(decoder.blocked.wait, 2)

        competing = _RestartDecoder()
        competing.fail_window = None
        second = _app(tmp_path, competing)
        with pytest.raises(RetainedFileWorkBusy):
            async with second.router.lifespan_context(second):
                pass

        decoder.release.set()
        await first_startup
        try:
            await _await_file_task(first, handle.meeting_id)
            snapshot = await _snapshot(first, handle)
            assert decoder.calls == [0, 1, 2, 2, 3]
            assert competing.calls == []
            assert snapshot.status == "completed"
            assert snapshot.transcript_version == 1
            assert not owner_dir.exists()
        finally:
            await first_context.__aexit__(None, None, None)

    asyncio.run(exercise())
