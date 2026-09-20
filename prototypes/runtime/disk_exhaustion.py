"""R4-7 File job ENOSPC outcome on an hdiutil-mounted disposable volume."""

from __future__ import annotations

import asyncio
import errno
import io
import json
import os
import shutil
import sys
import time
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import Phase2Store, SESSION_COOKIE, create_phase2_app


class ExhaustingRunner:
    model_path = "runtime-enospc-control"

    def __init__(self) -> None:
        self.state: dict[str, object] = {}

    def transcribe(self, audio_path: str | Path, **_kwargs: object):
        pressure = Path(audio_path).parent / "pressure.bin"
        block = b"\xa5" * (8 * 1024 * 1024)
        written = 0
        self.state["free_before_runner"] = shutil.disk_usage(pressure.parent).free
        try:
            with pressure.open("wb", buffering=0) as output:
                while written < 2 * 1024 * 1024 * 1024:
                    output.write(block)
                    written += len(block)
                    if written % (64 * 1024 * 1024) == 0:
                        os.fsync(output.fileno())
        except OSError as exc:
            self.state.update(
                enospc_errno=exc.errno,
                enospc_observed=exc.errno == errno.ENOSPC,
                bytes_written_before_failure=written,
                free_at_failure=shutil.disk_usage(pressure.parent).free,
            )
            # Release measurement pressure before the product persists the typed failure.
            # The ENOSPC is real; this cleanup keeps the evidence store writable.
            pressure.unlink(missing_ok=True)
            raise
        raise AssertionError("disposable volume did not reach ENOSPC")


def wav_bytes() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\x01\x00" * 16_000)
    return output.getvalue()


async def provision(database: Path) -> str:
    store = await Phase2Store.open(database)
    try:
        _, session_id = await store.bootstrap_browser(None)
        return session_id
    finally:
        await store.close()


def wait_terminal(client: TestClient, meeting_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 30
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/meetings/{meeting_id}")
        response.raise_for_status()
        last = response.json()
        if last["status"] != "active":
            return last
        time.sleep(0.05)
    raise AssertionError({"reason": "meeting stayed active", "last": last})


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: disk_exhaustion.py MOUNTPOINT")
    root = Path(sys.argv[1]).resolve()
    database = root / "state" / "moss.sqlite3"
    work_root = root / "file-work"
    audio_root = root / "meetings"
    session_id = asyncio.run(provision(database))
    runner = ExhaustingRunner()
    app = create_phase2_app(
        database_path=database,
        file_runner=runner,
        file_work_root=work_root,
        meeting_audio_root=audio_root,
    )
    with TestClient(app, base_url="https://moss.test") as client:
        client.cookies.set(SESSION_COOKIE, session_id, domain="moss.test", path="/")
        accepted = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", wav_bytes(), "audio/wav")},
        )
        accepted.raise_for_status()
        meeting_id = accepted.json()["id"]
        terminal = wait_terminal(client, meeting_id)

    reopened = create_phase2_app(
        database_path=database,
        file_work_root=work_root,
        meeting_audio_root=audio_root,
    )
    with TestClient(reopened, base_url="https://moss.test") as client:
        client.cookies.set(SESSION_COOKIE, session_id, domain="moss.test", path="/")
        response = client.get(f"/api/meetings/{meeting_id}")
        response.raise_for_status()
        saved = response.json()

    state = {
        "verdict": "SUPPORTED",
        "volume": str(root),
        "runner": runner.state,
        "first_terminal": terminal,
        "reopened": saved,
        "never_completed": terminal["status"] != "completed" and saved["status"] != "completed",
        "explicit_saved_failure": (
            terminal["status"] == "failed"
            and saved["status"] == "failed"
            and bool(saved.get("failure_code"))
            and bool(saved.get("failure_reason"))
        ),
    }
    if not runner.state.get("enospc_observed"):
        raise AssertionError(state)
    if not state["never_completed"] or not state["explicit_saved_failure"]:
        raise AssertionError(state)
    print(json.dumps(state, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
