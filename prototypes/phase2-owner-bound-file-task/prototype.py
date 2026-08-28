"""One-command probe for the smallest reliable File-Meeting task owner."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Authority:
    generation: int = 0

    def revoke(self) -> None:
        self.generation += 1


@dataclass
class OwnerBoundMeeting:
    authority: Authority
    captured_generation: int
    status: str = "active"
    commits: int = 0

    def commit(self) -> None:
        if self.captured_generation != self.authority.generation or self.status != "active":
            raise PermissionError("stale authority")
        self.commits += 1
        self.status = "completed"


class AppOwnedTasks:
    """Only a strong-reference set; each coroutine already carries owner authority."""

    def __init__(self) -> None:
        self.tasks: set[asyncio.Task[None]] = set()
        self.rejected = 0

    def start(self, meeting: OwnerBoundMeeting, release: asyncio.Event) -> None:
        async def run() -> None:
            await release.wait()
            try:
                meeting.commit()
            except PermissionError:
                self.rejected += 1

        task = asyncio.create_task(run())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)


class ShutdownTasks:
    """Probe the exact shield-and-quiesce boundary required around ``to_thread``."""

    def __init__(self) -> None:
        self.tasks: set[asyncio.Task[None]] = set()
        self.commits = 0
        self.runner_started = threading.Event()
        self.runner_release = threading.Event()

    def start(self, source: Path) -> None:
        def transcribe() -> str:
            self.runner_started.set()
            assert self.runner_release.wait(timeout=5)
            assert source.exists()
            return "result"

        async def run() -> None:
            runner_task = asyncio.create_task(asyncio.to_thread(transcribe))
            try:
                await asyncio.shield(runner_task)
            except asyncio.CancelledError:
                await runner_task
                source.unlink()
                raise
            self.commits += 1
            source.unlink()

        task = asyncio.create_task(run())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def stop(self) -> None:
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def exercise() -> dict[str, object]:
    authority = Authority()
    app_tasks = AppOwnedTasks()
    stale = OwnerBoundMeeting(authority, captured_generation=0)
    stale_release = asyncio.Event()

    client_cookie: str | None = "opaque-session"
    app_tasks.start(stale, stale_release)
    response_accepted = True
    client_cookie = None
    await asyncio.sleep(0)
    task_survived_after_detach = len(app_tasks.tasks) == 1

    authority.revoke()
    stale.status = "interrupted"
    fresh = OwnerBoundMeeting(authority, captured_generation=1)
    fresh_release = asyncio.Event()
    app_tasks.start(fresh, fresh_release)
    fresh_release.set()
    stale_release.set()
    await asyncio.gather(*tuple(app_tasks.tasks))
    await asyncio.sleep(0)

    with tempfile.TemporaryDirectory() as temporary:
        work_root = Path(temporary) / "file-work"
        active_dir = work_root / "active-owner-work"
        active_dir.mkdir(parents=True)
        source = active_dir / "input.wav"
        source.write_bytes(b"transient")
        shutdown_tasks = ShutdownTasks()
        shutdown_tasks.start(source)
        while not shutdown_tasks.runner_started.is_set():
            await asyncio.sleep(0)
        stop_task = asyncio.create_task(shutdown_tasks.stop())
        await asyncio.sleep(0.01)
        stop_pending_while_runner_blocked = not stop_task.done()
        source_exists_while_runner_blocked = source.exists()
        shutdown_tasks.runner_release.set()
        await stop_task
        await asyncio.sleep(0)

        orphan_dir = work_root / "crash-orphan"
        orphan_dir.mkdir()
        (orphan_dir / "input.wav").write_bytes(b"orphan")
        orphan_seeded = orphan_dir.exists()
        for child in tuple(work_root.iterdir()):
            shutil.rmtree(child)
        orphan_removed_before_admission = not any(work_root.iterdir())

        shutdown_state = {
            "stop_pending_while_runner_blocked": stop_pending_while_runner_blocked,
            "source_exists_while_runner_blocked": source_exists_while_runner_blocked,
            "shutdown_commit_fenced": shutdown_tasks.commits == 0,
            "source_removed_after_runner_release": not source.exists(),
            "shutdown_task_set_size": len(shutdown_tasks.tasks),
            "orphan_seeded": orphan_seeded,
            "orphan_removed_before_admission": orphan_removed_before_admission,
        }

    state = {
        "meeting_count": 2,
        "response_accepted": response_accepted,
        "client_cookie": client_cookie,
        "task_survived_after_detach": task_survived_after_detach,
        "stale_status": stale.status,
        "stale_commits": stale.commits,
        "stale_commit_rejected": app_tasks.rejected == 1,
        "fresh_status": fresh.status,
        "fresh_commits": fresh.commits,
        "fresh_authority_unaffected": fresh.status == "completed" and fresh.commits == 1,
        "task_set_size": len(app_tasks.tasks),
        **shutdown_state,
    }
    expected = {
        "meeting_count": 2,
        "response_accepted": True,
        "client_cookie": None,
        "task_survived_after_detach": True,
        "stale_status": "interrupted",
        "stale_commits": 0,
        "stale_commit_rejected": True,
        "fresh_status": "completed",
        "fresh_commits": 1,
        "fresh_authority_unaffected": True,
        "task_set_size": 0,
        "stop_pending_while_runner_blocked": True,
        "source_exists_while_runner_blocked": True,
        "shutdown_commit_fenced": True,
        "source_removed_after_runner_release": True,
        "shutdown_task_set_size": 0,
        "orphan_seeded": True,
        "orphan_removed_before_admission": True,
    }
    print(json.dumps(state, indent=2, sort_keys=True))
    assert state == expected
    return state


if __name__ == "__main__":
    asyncio.run(exercise())
