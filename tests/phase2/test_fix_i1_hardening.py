"""Strict controls for I1 registration and retained-owner enumeration."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from types import MethodType

import pytest

from moss_transcribe_diarize.app.phase2 import Phase2Store
from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def test_registration_failure_never_leaves_active_meeting_unowned() -> None:
    import probe_01

    cases = asyncio.run(probe_01.run())
    registration = [case for case in cases if case.get("boundary") == "registration"]
    assert len(registration) == 2
    assert all(case["held"] for case in registration)


def test_unreadable_retained_directory_is_skipped_without_aborting_startup(
    tmp_path: Path,
) -> None:
    from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks

    tasks = FileMeetingTasks(object(), tmp_path / "file-work")
    unreadable = tasks.retained_root / "unreadable-account"
    (unreadable / "owner").mkdir(parents=True)
    unreadable.chmod(0)
    try:
        owners = tasks.retained_work_owners()
    finally:
        unreadable.chmod(0o700)
    assert ("unreadable-account", "owner") not in owners


@pytest.mark.parametrize("ingress", ["file", "url"])
def test_task_creation_failure_settles_and_reclaims_only_its_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ingress: str,
) -> None:
    import probe_01

    async def exercise() -> None:
        tasks = FileMeetingTasks(
            object(), tmp_path / "file-work", url_acquirer=probe_01.Acquirer()
        )
        workspace = probe_01.Workspace()

        def fail_create(_coroutine):
            raise RuntimeError("injected task creation failure")

        monkeypatch.setattr(asyncio, "create_task", fail_create)
        with pytest.raises(RuntimeError, match="injected task creation failure"):
            if ingress == "file":
                await tasks.accept(workspace, probe_01.Upload())
            else:
                await tasks.accept_url(workspace, "https://example.test/offline.wav")
        handle = workspace.handles[0]
        assert handle.status == "failed"
        assert handle.meeting_id not in tasks._tasks
        assert not any(tasks.work_root.iterdir())
        assert not (tasks.retained_root / handle.owner_key[0] / handle.meeting_id).exists()

    asyncio.run(exercise())


@pytest.mark.parametrize("ingress", ["file", "url"])
def test_success_path_preserves_stored_meeting_and_owner_bytes(
    tmp_path: Path,
    ingress: str,
) -> None:
    import probe_01

    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        tasks = FileMeetingTasks(
            object(), tmp_path / "file-work", url_acquirer=probe_01.Acquirer()
        )
        release = asyncio.Event()
        run_started = asyncio.Event()

        async def held_run(self, handle, input_path, started, **_kwargs):
            del self, handle, input_path
            run_started.set()
            started.set()
            await release.wait()

        tasks._run = MethodType(held_run, tasks)
        try:
            account, _session = await store.bootstrap_browser(None)
            workspace = store.workspace(account)
            if ingress == "file":
                handle = await tasks.accept(workspace, probe_01.Upload())
            else:
                handle = await tasks.accept_url(
                    workspace, "https://example.test/offline.wav"
                )
                await asyncio.wait_for(run_started.wait(), timeout=2)

            snapshot = await handle.snapshot()
            owner = tasks.retained_root / account.account_id / handle.meeting_id
            expected_manifest = (
                json.dumps(
                    {
                        "account_id": account.account_id,
                        "meeting_id": handle.meeting_id,
                        "ingress": ingress,
                        "source": "input.wav",
                        "checkpoint": "checkpoint",
                        "contract_version": 1,
                    },
                    sort_keys=True,
                )
                + "\n"
            ).encode()
            assert snapshot.status == "active"
            assert handle.meeting_id in tasks._tasks
            assert (owner / "input.wav").read_bytes() == b"offline fixture"
            assert (owner / "owner.json").read_bytes() == expected_manifest
            assert (owner / "checkpoint").is_dir()
        finally:
            release.set()
            await tasks.stop()
            await store.close()

    asyncio.run(exercise())


def test_unreadable_account_is_logged_once_while_terminal_sibling_is_reclaimed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        tasks = FileMeetingTasks(object(), tmp_path / "file-work")
        try:
            account, _session = await store.bootstrap_browser(None)
            terminal = await store.workspace(account).create_meeting("file")
            await terminal.finish("interrupted")
            terminal_owner = tasks.retained_root / account.account_id / terminal.meeting_id
            terminal_owner.mkdir(parents=True)
            unreadable = tasks.retained_root / "private-account"
            (unreadable / "private-owner").mkdir(parents=True)
            original_iterdir = Path.iterdir

            def controlled_iterdir(path: Path):
                if path == unreadable:
                    raise PermissionError("private contents")
                return original_iterdir(path)

            monkeypatch.setattr(Path, "iterdir", controlled_iterdir)
            with caplog.at_level(
                logging.WARNING, logger="moss_transcribe_diarize.app.phase2_file"
            ):
                owners = tasks.retained_work_owners()
            reclaimable = await store.terminal_file_meeting_owners(
                retained_owners=owners
            )
            tasks.reclaim_terminal_retained_work(reclaimable)

            messages = [
                record.getMessage()
                for record in caplog.records
                if "account directory unreadable" in record.getMessage()
            ]
            assert messages == ["Retained File account directory unreadable; skipping."]
            assert "private-account" not in caplog.text
            assert "private-owner" not in caplog.text
            assert not terminal_owner.exists()
            assert unreadable.is_dir()
        finally:
            await tasks.stop()
            await store.close()

    asyncio.run(exercise())


def test_unreadable_owner_entry_is_logged_once_and_sibling_is_returned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    tasks = FileMeetingTasks(object(), tmp_path / "file-work")
    good = tasks.retained_root / "account" / "good-owner"
    bad = tasks.retained_root / "account" / "private-owner"
    good.mkdir(parents=True)
    bad.mkdir()
    original_is_symlink = Path.is_symlink

    def controlled_is_symlink(path: Path) -> bool:
        if path == bad:
            raise PermissionError("private contents")
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", controlled_is_symlink)
    with caplog.at_level(
        logging.WARNING, logger="moss_transcribe_diarize.app.phase2_file"
    ):
        owners = tasks.retained_work_owners()

    assert owners == (("account", "good-owner"),)
    assert [
        record.getMessage()
        for record in caplog.records
        if "owner entry unreadable" in record.getMessage()
    ] == ["Retained File owner entry unreadable; skipping."]
    assert "private-owner" not in caplog.text
