"""Throwaway production-path operator status size probe; prints counts only."""

import asyncio
import json
import tempfile
from pathlib import Path

from moss_transcribe_diarize.app.inference_scheduler import InferenceDispatchScheduler
from moss_transcribe_diarize.app.phase2 import Phase2Store
from moss_transcribe_diarize.app.phase2_control import (
    MAX_CONTROL_LINE_BYTES,
    Phase2ControlError,
    Phase2ControlServer,
    request_control,
)
from moss_transcribe_diarize.app.phase2_operator import Phase2OperatorStatus, render_operator_status


class FileStatusAdapter:
    def __init__(self, scheduler: InferenceDispatchScheduler) -> None:
        self._inference_scheduler = scheduler

    def operator_snapshot(self) -> dict[str, str]:
        return {}


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="moss-h2e2-") as root:
        root_path = Path(root)
        database = root_path / "moss.sqlite3"
        store = await Phase2Store.open(database)
        scheduler = InferenceDispatchScheduler()
        operator = Phase2OperatorStatus(
            store,
            database_path=database,
            audio_root=root_path / "audio",
            live=None,
            files=FileStatusAdapter(scheduler),
        )
        await operator.start()
        server = Phase2ControlServer(root_path / "control.sock", lifecycle=None, operator=operator)
        await server.start()
        accounts = []
        completed = []
        meetings_created = 0

        async def observe(phase: str) -> int:
            status = await operator.snapshot()
            clock = status["capacity"]["dispatch_stage_clocks"]
            status_json = json.dumps(status, sort_keys=True).encode()
            response_bytes = len(json.dumps({"ok": True, "result": status}, sort_keys=True).encode()) + 1
            try:
                returned = await request_control(server.path, "status")
                result = (
                    "PASS"
                    if isinstance(returned, dict)
                    and returned.get("schema") == status["schema"]
                    and len(returned.get("accounts", [])) == len(status["accounts"])
                    and len(returned.get("active_meetings", [])) == len(status["active_meetings"])
                    else "CHANGED"
                )
            except Phase2ControlError as exc:
                result = (
                    "INVALID_RESPONSE"
                    if str(exc) == "Phase-2 product returned an invalid control response."
                    else "OTHER_CONTROL_ERROR"
                )
            print(json.dumps({
                "phase": phase,
                "accounts": len(status["accounts"]),
                "meetings_created": meetings_created,
                "active_live": status["capacity"]["live"]["active"],
                "active_meetings": len(status["active_meetings"]),
                "clock_owners": len(clock["owners"]),
                "status_json_bytes": len(status_json),
                "response_bytes": response_bytes,
                "accounts_section_bytes": len(json.dumps(status["accounts"], sort_keys=True).encode()),
                "active_section_bytes": len(json.dumps(status["active_meetings"], sort_keys=True).encode()),
                "clocks_section_bytes": len(json.dumps(clock, sort_keys=True).encode()),
                "render_ok": isinstance(render_operator_status(status), str),
                "request": result,
                "limit_bytes": MAX_CONTROL_LINE_BYTES,
            }, sort_keys=True))
            return response_bytes

        try:
            await observe("empty")
            for number in range(1, 12):
                account, _ = await store.bootstrap_browser(None)
                accounts.append(account)
                workspace = store.workspace(account)
                for _ in range(2):
                    meeting = await workspace.create_meeting("file")
                    meetings_created += 1
                    await meeting.finish("completed")
                    completed.append(meeting.meeting_id)
                await observe(f"account_{number}")

            active = []
            for number in range(1, 3):
                meeting = await store.workspace(accounts[number - 1]).create_meeting("live")
                meetings_created += 1
                active.append(meeting)
                await observe(f"active_live_{number}")
            for meeting in active:
                await meeting.finish("interrupted")
            await observe("active_live_cleared")

            crossed = False
            near_host_checked = False
            for number, meeting_id in enumerate(completed, 1):
                scheduler.run_background(meeting_id, lambda: None, owner_class="file")
                crossed = await observe(f"completed_dispatch_owner_{number}") > MAX_CONTROL_LINE_BYTES
                if crossed:
                    break
            extra = 0
            while not crossed and extra < 40:
                account = accounts[extra % len(accounts)]
                meeting = await store.workspace(account).create_meeting("file")
                meetings_created += 1
                await meeting.finish("completed")
                scheduler.run_background(meeting.meeting_id, lambda: None, owner_class="file")
                extra += 1
                response_bytes = await observe(f"extra_dispatch_owner_{extra}")
                crossed = response_bytes > MAX_CONTROL_LINE_BYTES
                if not near_host_checked and 15_800 <= response_bytes <= MAX_CONTROL_LINE_BYTES:
                    live = await store.workspace(accounts[0]).create_meeting("live")
                    meetings_created += 1
                    await observe("near_host_plus_one_active_live")
                    await live.finish("interrupted")
                    await observe("near_host_active_cleared")
                    near_host_checked = True

            for number in range(12, 14):
                account, _ = await store.bootstrap_browser(None)
                accounts.append(account)
                await observe(f"account_{number}")
        finally:
            await server.stop()
            await store.close()


if __name__ == "__main__":
    asyncio.run(main())
