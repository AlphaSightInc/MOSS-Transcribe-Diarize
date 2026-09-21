"""Focused helper for the phase-2 I1 registration control."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import MethodType, SimpleNamespace


class Handle:
    def __init__(self, meeting_id: str):
        self.meeting_id = meeting_id
        self.owner_key = ("stress-account", 0)
        self.status = "active"
        self.finish_calls: list[str] = []

    async def finish(self, status: str, **_kwargs) -> None:
        self.finish_calls.append(status)
        self.status = status

    async def snapshot(self):
        return SimpleNamespace(status=self.status)


class Workspace:
    def __init__(self):
        self.handles: list[Handle] = []

    async def create_meeting(self, mode: str) -> Handle:
        assert mode == "file"
        handle = Handle(f"meeting-{len(self.handles)}")
        self.handles.append(handle)
        return handle


class Upload:
    filename = "input.wav"

    def __init__(self):
        self._sent = False

    async def read(self, _size: int) -> bytes:
        if self._sent:
            return b""
        self._sent = True
        return b"offline fixture"


class Acquirer:
    async def acquire(self, _url: str, directory: Path) -> Path:
        path = directory / "input.wav"
        path.write_bytes(b"offline fixture")
        return path


async def _case(ingress: str) -> dict[str, object]:
    from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks

    from tempfile import TemporaryDirectory

    with TemporaryDirectory(prefix=f"moss-stress-i1-{ingress}-registration-") as raw:
        tasks = FileMeetingTasks(
            object(), Path(raw) / "file-work", url_acquirer=Acquirer()
        )
        workspace = Workspace()
        leaked_tasks: list[asyncio.Task] = []

        async def held_run(self, handle, input_path, started, **_kwargs):
            del self, handle, input_path
            leaked_tasks.append(asyncio.current_task())
            started.set()
            await asyncio.Event().wait()

        def fail_register(_self, _handle, _task, **_kwargs):
            raise RuntimeError("injected registration failure")

        tasks._run = MethodType(held_run, tasks)
        tasks._register = MethodType(fail_register, tasks)
        try:
            if ingress == "file":
                await tasks.accept(workspace, Upload())
            else:
                await tasks.accept_url(workspace, "https://example.test/offline.wav")
        except RuntimeError:
            pass
        await asyncio.sleep(0)

        states = []
        for handle in workspace.handles:
            registered = handle.meeting_id in tasks._tasks
            states.append({
                "status": handle.status,
                "registered": registered,
                "active_without_owner": handle.status == "active" and not registered,
            })
        for task in leaked_tasks:
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*leaked_tasks, return_exceptions=True)
        await tasks.stop()
        return {
            "boundary": "registration",
            "meetings": states,
            "held": not any(row["active_without_owner"] for row in states),
        }


async def run() -> list[dict[str, object]]:
    return [await _case(ingress) for ingress in ("file", "url")]
