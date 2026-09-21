"""Run-E controls discovered by the P-F1F5 throwaway prototype."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from moss_transcribe_diarize.app.phase2 import Phase2Store, create_phase2_app
from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks


class _NeverDecoder:
    def transcribe(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("these controls must dispatch no decoder")


class _NeverAcquirer:
    async def acquire(self, *_args: object, **_kwargs: object) -> Path:
        raise AssertionError("accept-time retention failure must precede acquisition")


class _HoldingAcquirer:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def acquire(self, _source_url: str, staging_dir: Path) -> Path:
        self.started.set()
        await self.release.wait()
        source = staging_dir / "input.wav"
        source.write_bytes(b"source")
        return source


class _Upload:
    filename = "input.wav"

    def __init__(self) -> None:
        self._chunks = [b"source", b""]

    async def read(self, _size: int) -> bytes:
        return self._chunks.pop(0)


class _CapturingWorkspace:
    def __init__(self, workspace: Any) -> None:
        self._workspace = workspace
        self.handle = None

    async def create_meeting(self, mode: str) -> Any:
        self.handle = await self._workspace.create_meeting(mode)
        return self.handle


def _inject_retain_failure(tasks: FileMeetingTasks, arm: str):
    original = tasks._retain_new_directory

    def fail(handle: Any, staging_dir: Path) -> Path:
        if arm == "post_move":
            original(handle, staging_dir)
        raise OSError(f"controlled {arm} retention failure")

    return fail


@pytest.mark.parametrize("arm", ["pre_move", "post_move"])
def test_f1_url_accept_retention_failure_settles_created_meeting(
    tmp_path: Path,
    arm: str,
) -> None:
    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        tasks = FileMeetingTasks(
            _NeverDecoder(), tmp_path / "file-work", url_acquirer=_NeverAcquirer()
        )
        try:
            account, _session = await store.bootstrap_browser(None)
            workspace = _CapturingWorkspace(store.workspace(account))
            sibling = tasks.retained_root / account.account_id / "sibling" / "marker"
            sibling.parent.mkdir(parents=True)
            sibling.write_text("preserve", encoding="utf-8")
            outside = tmp_path / "outside" / "marker"
            outside.parent.mkdir()
            outside.write_text("preserve", encoding="utf-8")
            tasks._retain_new_directory = _inject_retain_failure(tasks, arm)  # type: ignore[method-assign]

            with pytest.raises(OSError, match=f"controlled {arm}"):
                await tasks.accept_url(workspace, "https://example.test/input.wav")

            handle = workspace.handle
            snapshot = await handle.snapshot()
            assert snapshot.status == "failed"
            assert snapshot.failure_code == "storage_failed"
            assert snapshot.failure_reason == "The meeting could not be saved."
            assert handle.meeting_id not in tasks._tasks
            assert not any(tasks.work_root.iterdir())
            assert not (tasks.retained_root / account.account_id / handle.meeting_id).exists()
            assert sibling.read_text(encoding="utf-8") == "preserve"
            assert outside.read_text(encoding="utf-8") == "preserve"
        finally:
            await tasks.stop()
            await store.close()

    asyncio.run(exercise())


def test_f1_file_accept_pre_move_failure_leaves_no_staging_or_owner(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        tasks = FileMeetingTasks(_NeverDecoder(), tmp_path / "file-work")
        try:
            account, _session = await store.bootstrap_browser(None)
            workspace = _CapturingWorkspace(store.workspace(account))
            tasks._retain_new_directory = _inject_retain_failure(tasks, "pre_move")  # type: ignore[method-assign]
            with pytest.raises(OSError, match="controlled pre_move"):
                await tasks.accept(workspace, _Upload())
            snapshot = await workspace.handle.snapshot()
            assert snapshot.status == "failed"
            assert snapshot.failure_code == "storage_failed"
            assert not any(tasks.work_root.iterdir())
            assert not (tasks.retained_root / account.account_id / workspace.handle.meeting_id).exists()
        finally:
            await tasks.stop()
            await store.close()

    asyncio.run(exercise())


def test_f1_file_accept_post_move_failure_settles_and_cleans_its_owner(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        tasks = FileMeetingTasks(_NeverDecoder(), tmp_path / "file-work")
        try:
            account, _session = await store.bootstrap_browser(None)
            workspace = _CapturingWorkspace(store.workspace(account))
            tasks._retain_new_directory = _inject_retain_failure(tasks, "post_move")  # type: ignore[method-assign]
            with pytest.raises(OSError, match="controlled post_move"):
                await tasks.accept(workspace, _Upload())
            snapshot = await workspace.handle.snapshot()
            assert snapshot.status == "failed"
            assert snapshot.failure_code == "storage_failed"
            assert not any(tasks.work_root.iterdir())
            assert not (
                tasks.retained_root / account.account_id / workspace.handle.meeting_id
            ).exists()
        finally:
            await tasks.stop()
            await store.close()

    asyncio.run(exercise())


def test_f1_file_meeting_creation_failure_cleans_only_staging(tmp_path: Path) -> None:
    class _RejectingWorkspace:
        async def create_meeting(self, _mode: str) -> Any:
            raise RuntimeError("controlled Meeting creation failure")

    async def exercise() -> None:
        tasks = FileMeetingTasks(_NeverDecoder(), tmp_path / "file-work")
        try:
            with pytest.raises(RuntimeError, match="controlled Meeting creation failure"):
                await tasks.accept(_RejectingWorkspace(), _Upload())
            assert not any(tasks.work_root.iterdir())
            assert not tasks.retained_root.exists()
        finally:
            await tasks.stop()

    asyncio.run(exercise())


def test_f1_successful_url_accept_is_unchanged(tmp_path: Path) -> None:
    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        acquirer = _HoldingAcquirer()
        tasks = FileMeetingTasks(
            _NeverDecoder(), tmp_path / "file-work", url_acquirer=acquirer
        )
        try:
            account, _session = await store.bootstrap_browser(None)
            handle = await tasks.accept_url(
                store.workspace(account), "https://example.test/input.wav"
            )
            await asyncio.wait_for(acquirer.started.wait(), timeout=2)
            snapshot = await handle.snapshot()
            assert snapshot.status == "active"
            assert handle.meeting_id in tasks._tasks
            assert not any(tasks.work_root.iterdir())
            assert (tasks.retained_root / account.account_id / handle.meeting_id).is_dir()
        finally:
            await tasks.stop()
            await store.close()

    asyncio.run(exercise())


def test_f5_startup_reclaim_probes_only_existing_retained_owners(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def seed() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            account, _session = await store.bootstrap_browser(None)
            rows = [
                (account.account_id, f"terminal-{index:03d}", "file", "completed", index, index)
                for index in range(100)
            ]
            await store._connection.executemany(
                """
                INSERT INTO meetings(
                    account_id, meeting_id, mode, status, created_at_ms, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            await store._connection.commit()
            for _account, meeting_id, *_rest in rows[:7]:
                owner = tmp_path / "file-retained" / account.account_id / meeting_id
                owner.mkdir(parents=True)
        finally:
            await store.close()

    asyncio.run(seed())
    probes: list[Path] = []
    original = FileMeetingTasks._remove_retained_work_dir

    def count_probe(self: FileMeetingTasks, owner_dir: Path) -> None:
        probes.append(owner_dir)
        original(self, owner_dir)

    monkeypatch.setattr(FileMeetingTasks, "_remove_retained_work_dir", count_probe)
    app = create_phase2_app(
        database_path=tmp_path / "state.sqlite3",
        file_runner=_NeverDecoder(),
        file_work_root=tmp_path / "file-work",
        meeting_audio_root=tmp_path / "meeting-audio",
    )

    async def startup() -> None:
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(startup())
    assert len(probes) == 7
    assert all(path.parent.parent == tmp_path / "file-retained" for path in probes)


def test_f5_reclaim_preserves_active_unknown_and_outside_owners(tmp_path: Path) -> None:
    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        tasks = FileMeetingTasks(_NeverDecoder(), tmp_path / "file-work")
        try:
            account, _session = await store.bootstrap_browser(None)
            terminal = await store.workspace(account).create_meeting("file")
            active = await store.workspace(account).create_meeting("file")
            await terminal.finish("interrupted")
            terminal_dir = tasks.retained_root / account.account_id / terminal.meeting_id
            active_dir = tasks.retained_root / account.account_id / active.meeting_id
            unknown_dir = tasks.retained_root / account.account_id / "unknown-meeting"
            outside = tmp_path / "outside" / "marker"
            for owner_dir in (terminal_dir, active_dir, unknown_dir):
                owner_dir.mkdir(parents=True)
            outside.parent.mkdir()
            outside.write_text("preserve", encoding="utf-8")

            retained = tasks.retained_work_owners()
            reclaimable = await store.terminal_file_meeting_owners(
                retained_owners=retained
            )
            assert reclaimable == ((account.account_id, terminal.meeting_id),)
            tasks.reclaim_terminal_retained_work(reclaimable)

            assert not terminal_dir.exists()
            assert active_dir.is_dir()
            assert unknown_dir.is_dir()
            assert outside.read_text(encoding="utf-8") == "preserve"
        finally:
            await tasks.stop()
            await store.close()

    asyncio.run(exercise())


def test_f5_reclaim_at_100000_history_probes_seven_retained_owners(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def seed() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            account, _session = await store.bootstrap_browser(None)
            rows = [
                (account.account_id, f"terminal-{index:06d}", "file", "completed", index, index)
                for index in range(100_000)
            ]
            await store._connection.executemany(
                """
                INSERT INTO meetings(
                    account_id, meeting_id, mode, status, created_at_ms, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            await store._connection.commit()
            for _account, meeting_id, *_rest in rows[:7]:
                (tmp_path / "file-retained" / account.account_id / meeting_id).mkdir(
                    parents=True
                )
        finally:
            await store.close()

    asyncio.run(seed())
    probes: list[Path] = []
    original = FileMeetingTasks._remove_retained_work_dir

    def count_probe(self: FileMeetingTasks, owner_dir: Path) -> None:
        probes.append(owner_dir)
        original(self, owner_dir)

    monkeypatch.setattr(FileMeetingTasks, "_remove_retained_work_dir", count_probe)
    app = create_phase2_app(
        database_path=tmp_path / "state.sqlite3",
        file_runner=_NeverDecoder(),
        file_work_root=tmp_path / "file-work",
        meeting_audio_root=tmp_path / "meeting-audio",
    )

    async def startup() -> None:
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(startup())
    assert len(probes) == 7
