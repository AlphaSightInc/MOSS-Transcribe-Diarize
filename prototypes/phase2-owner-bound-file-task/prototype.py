"""One-command probe for the smallest reliable File-Meeting task owner."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass


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
    }
    print(json.dumps(state, indent=2, sort_keys=True))
    assert state == expected
    return state


if __name__ == "__main__":
    asyncio.run(exercise())
