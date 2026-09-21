"""Strict violating controls for the post-I3/I4 diagnosis signals."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from _browser_workspace_fixtures import seed_workspace

from moss_transcribe_diarize.app.phase2 import MeetingHandle, Phase2Store, create_phase2_app
from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks


def test_s1_stalled_validation_does_not_starve_later_retained_owners(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        tasks = FileMeetingTasks(object(), tmp_path / "file-work")
        handles = tuple(
            SimpleNamespace(owner_key=("account-a", 1), meeting_id=meeting_id)
            for meeting_id in ("owner-1", "owner-2")
        )
        for handle in handles:
            owner_dir = tasks.retained_root / handle.owner_key[0] / handle.meeting_id
            owner_dir.mkdir(parents=True)
            (owner_dir / "owner.json").write_text("{}\n", encoding="utf-8")

        first_entered = threading.Event()
        release_first = threading.Event()
        second_validated = threading.Event()
        second_resumed = asyncio.Event()

        def validate(handle: object, owner_dir: Path) -> object:
            if handle.meeting_id == "owner-1":  # type: ignore[attr-defined]
                first_entered.set()
                release_first.wait()
            else:
                second_validated.set()
            source = owner_dir / "input.wav"
            return SimpleNamespace(
                input_path=source,
                source=source,
                checkpoint_bound=False,
                mix_path=None,
            )

        async def run(
            handle: object,
            _input_path: Path,
            started: asyncio.Event,
            *,
            resumed: bool,
            resume_source: object,
        ) -> None:
            assert resumed is True
            assert resume_source is not None
            started.set()
            if handle.meeting_id == "owner-2":  # type: ignore[attr-defined]
                second_resumed.set()

        tasks._verified_retained_resume_source = validate  # type: ignore[method-assign]
        tasks._run = run  # type: ignore[method-assign]

        class Store:
            async def active_file_meetings(self) -> tuple[object, ...]:
                return handles

        claimed = await tasks.resume_retained_work(Store())
        assert claimed == frozenset(
            (("account-a", "owner-1"), ("account-a", "owner-2"))
        )
        assert await asyncio.to_thread(first_entered.wait, 1)
        try:
            validated = await asyncio.to_thread(second_validated.wait, 0.2)
            try:
                await asyncio.wait_for(second_resumed.wait(), timeout=0.2)
                resumed = True
            except TimeoutError:
                resumed = False
            assert (validated, resumed) == (True, True)
        finally:
            release_first.set()
            coordinator = tasks._retained_resume_task
            if coordinator is not None:
                await coordinator
            await tasks.stop()

    asyncio.run(exercise())


def test_s3_lifespan_reclaims_fallback_interrupted_owner_in_same_boot(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        database = tmp_path / "state.sqlite3"
        work_root = tmp_path / "file-work"
        store = await Phase2Store.open(database)
        try:
            account, _ = await seed_workspace(store, "account-a")
            handle = await store.workspace(account).create_meeting("file")
        finally:
            await store.close()

        owner_dir = tmp_path / "file-retained" / account.account_id / handle.meeting_id
        owner_dir.mkdir(parents=True)
        (owner_dir / "retained-prefix").write_bytes(b"retained work")
        first = create_phase2_app(
            database_path=database,
            file_runner=object(),
            file_work_root=work_root,
            meeting_audio_root=tmp_path / "meeting-audio",
        )
        async with first.router.lifespan_context(first):
            reopened = MeetingHandle(
                first.state.phase2_store,
                account.account_id,
                account.authority_generation,
                handle.meeting_id,
            )
            assert (await reopened.snapshot()).status == "interrupted"
            remained_after_fallback = owner_dir.exists()

        second = create_phase2_app(
            database_path=database,
            file_runner=object(),
            file_work_root=work_root,
            meeting_audio_root=tmp_path / "meeting-audio",
        )
        async with second.router.lifespan_context(second):
            reclaimed_on_next_boot = not owner_dir.exists()

        assert (remained_after_fallback, reclaimed_on_next_boot) == (False, True)

    asyncio.run(exercise())
