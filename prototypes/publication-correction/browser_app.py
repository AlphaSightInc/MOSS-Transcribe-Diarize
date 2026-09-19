"""Isolated browser stub for the saved correction journey; no capture or decoder."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import uvicorn

from moss_transcribe_diarize.app import phase2

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "phase2"))
import test_owner_bound_live_meeting as fixture


ROOT = Path(os.environ["MOSS_PUBLICATION_BROWSER_ROOT"])
phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
app = phase2.create_phase2_app(
    database_path=ROOT / "browser.sqlite3",
    file_work_root=ROOT / "file-work",
    open_workspace=True,
    live_runtime_factory=fixture.make_runtime,
    live_helper_lease_seconds=60,
)


@app.on_event("startup")
async def seed() -> None:
    account, _ = await app.state.phase2_store.bootstrap_browser(None, open_workspace=True)
    workspace = app.state.phase2_store.workspace(account)
    if await workspace.list_meetings():
        return
    handle = await workspace.create_meeting("file")
    await handle.finish_with_transcript(
        {
            "segments": [
                {"id": "seg_0001", "start": 0, "end": 2, "speaker_entity_id": "person-a", "speaker": "Alex", "text": "Opening words"},
                {"id": "seg_0002", "start": 2, "end": 4, "speaker_entity_id": "person-a", "speaker": "Alex", "text": "Passage to correct"},
                {"id": "seg_0003", "start": 4, "end": 6, "speaker": "S00", "text": "Uncertain closing words"},
            ]
        },
        "completed",
        notice="Final transcript refinement was unavailable for some audio. Previously committed words were kept.",
    )


@app.post("/prototype/seed")
async def seed_route() -> dict[str, bool]:
    await seed()
    return {"seeded": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=17960, log_level="warning")
