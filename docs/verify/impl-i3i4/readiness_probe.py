"""Zero-decoder I3 readiness measurement at the accepted owner/cost matrix."""

from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks


async def measure(root: Path, owners: int, validation_ms: int) -> dict[str, object]:
    tasks = FileMeetingTasks(object(), root / "file-work")
    handles = tuple(
        SimpleNamespace(owner_key=("account-a", 1), meeting_id=f"meeting-{index}")
        for index in range(owners)
    )
    for handle in handles:
        owner_dir = tasks.retained_root / "account-a" / handle.meeting_id
        owner_dir.mkdir(parents=True)
        (owner_dir / "owner.json").write_text("{}\n", encoding="utf-8")
    entered = threading.Event()

    def injected_validation(*_args: object) -> None:
        entered.set()
        time.sleep(validation_ms / 1000)

    tasks._verified_retained_input = injected_validation  # type: ignore[method-assign]

    class Store:
        async def active_file_meetings(self):
            return handles

    started = time.perf_counter_ns()
    claimed = await tasks.resume_retained_work(Store())
    readiness_ns = time.perf_counter_ns() - started
    validation_entered = await asyncio.to_thread(entered.wait, 1)
    await tasks.stop()
    expected = frozenset(("account-a", handle.meeting_id) for handle in handles)
    result = {
        "owners": owners,
        "injected_validation_ms": validation_ms,
        "readiness_ms": round(readiness_ns / 1_000_000, 6),
        "reservation_ms_per_owner": round(readiness_ns / owners / 1_000_000, 6),
        "exact_reserved_set": claimed == expected,
        "validation_entered_after_readiness": validation_entered,
    }
    assert result["exact_reserved_set"] is True
    assert result["validation_entered_after_readiness"] is True
    if owners == 120:
        assert result["reservation_ms_per_owner"] <= 0.2
    return result


async def main() -> None:
    results = []
    with tempfile.TemporaryDirectory(prefix="moss-i3-readiness-") as temporary:
        root = Path(temporary)
        for validation_ms in (3, 300):
            for owners in (1, 10, 120):
                results.append(
                    await measure(root / f"{validation_ms}-{owners}", owners, validation_ms)
                )
    print(json.dumps({"decoder_calls": 0, "results": results}, indent=2))


asyncio.run(main())
