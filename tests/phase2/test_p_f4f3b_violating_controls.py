"""Strict expected failures on frozen 0de56e1a for F4 and F3b."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks


def test_f4_retained_validation_is_not_on_startup_path(tmp_path: Path) -> None:
    class Handle:
        owner_key = ("account-a", 1)
        meeting_id = "meeting-a"

    class Store:
        async def active_file_meetings(self):
            return (Handle(),)

    async def exercise() -> None:
        tasks = FileMeetingTasks(object(), tmp_path / "file-work")
        validation_started = asyncio.Event()
        release_validation = asyncio.Event()

        async def blocked_claim(_handle):
            validation_started.set()
            await release_validation.wait()
            return True

        tasks.claim_retained_work = blocked_claim  # type: ignore[method-assign]
        startup = asyncio.create_task(tasks.resume_retained_work(Store()))
        await validation_started.wait()
        try:
            assert startup.done(), "startup is still blocked on validation"
        finally:
            release_validation.set()
            await startup

    asyncio.run(exercise())


def test_f3b_feature_rows_record_numeric_proxy_counter_deltas() -> None:
    source = (
        Path(__file__).parents[2] / "prototypes" / "feature-rows" / "run.py"
    ).read_text(encoding="utf-8")
    assert '"delegated_to supplied authority"' not in source
