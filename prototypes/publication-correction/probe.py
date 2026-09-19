"""Throwaway production-seam falsifier for Round-2 publication and correction."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
import tempfile
import time
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.live_service_runtime import _TransientCanonicalPumpScheduler
from moss_transcribe_diarize.app import phase2
from moss_transcribe_diarize.app.phase2 import create_phase2_app
from tests.test_live_service_runtime import BlockingDecoder, _descriptor, _frame, _runtime

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "phase2"))
import test_owner_bound_live_meeting as phase2_fixture


def lifecycle_probe() -> dict[str, object]:
    decoder = BlockingDecoder()
    scheduler = _TransientCanonicalPumpScheduler()
    base = _descriptor(max_queue_depth=2, max_retained_samples=6000)
    descriptor = dataclasses.replace(
        base,
        bounds=dataclasses.replace(base.bounds, max_tape_bytes=12_000),
    )
    runtime = _runtime(
        speech=(True, False),
        decoder=decoder,
        descriptor=descriptor,
        scheduler=scheduler,
    )
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))
    assert decoder.entered.wait(timeout=1.0)
    state = runtime._sessions[created.session_id]
    release_calls = 0
    original_release = state.coordinator.release_finalized_identity

    def observe_release() -> None:
        nonlocal release_calls
        release_calls += 1
        original_release()

    state.coordinator.release_finalized_identity = observe_release
    before = state.coordinator.tape_accounting()
    asyncio.run(runtime.abort(created.session_id, "prototype abort while decoder reads"))
    during = state.coordinator.tape_accounting()
    calls_during = release_calls
    decoder.release.set()
    assert decoder.finished.wait(timeout=1.0)
    deadline = time.monotonic() + 1.0
    while scheduler.worker_count and time.monotonic() < deadline:
        time.sleep(0.001)
    after = state.coordinator.tape_accounting()
    events = [event.kind for event in runtime.events(created.session_id)]
    return {
        "reader_in_flight_at_abort": True,
        "retained_bytes_before_abort": before.retained_bytes,
        "retained_bytes_during_reader": during.retained_bytes,
        "retained_bytes_after_reader": after.retained_bytes,
        "identity_release_calls_during_reader": calls_during,
        "identity_release_calls_after_reader": release_calls,
        "events": events,
        "contract_pass": (
            before.retained_bytes > 0
            and during.retained_bytes > 0
            and after.retained_bytes == 0
            and calls_during == 0
            and release_calls == 1
            and events.index("session_aborted") < events.index("session_tape_released")
        ),
    }


def correction_probe(root: Path) -> dict[str, object]:
    # Local semantic probe only. Production continues to refuse anything but SQLite 3.53.4.
    phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
    database = root / "scratch.sqlite3"
    sessions = asyncio.run(phase2_fixture.provision(database))
    app = create_phase2_app(database_path=database)
    with TestClient(app, base_url="https://moss.test") as client:
        phase2_fixture.session(client, sessions["a"])

        async def seed(status: str) -> str:
            account = await app.state.phase2_store.account_for_session(sessions["a"])
            handle = await app.state.phase2_store.workspace(account).create_meeting("file")
            document = {
                "segments": [
                    {"id": "seg_0001", "start": 0.0, "end": 1.0, "speaker": "S01", "text": "first words"},
                    {"id": "seg_0002", "start": 1.0, "end": 2.0, "speaker": "S01", "text": "selected words"},
                    {"id": "seg_0003", "start": 2.0, "end": 3.0, "speaker": "S00", "text": "uncertain words"},
                ]
            }
            if status == "active":
                await handle.commit_transcript(document)
            else:
                await handle.finish_with_transcript(document, status)
            return handle.meeting_id

        active_id = client.portal.call(seed, "active")
        terminal_id = client.portal.call(seed, "completed")
        active_edit = client.put(
            f"/api/meetings/{active_id}/passages/speaker",
            json={"segment_ids": ["seg_0002"], "label": "New person"},
        )
        terminal_edit = client.put(
            f"/api/meetings/{terminal_id}/passages/speaker",
            json={"segment_ids": ["seg_0002"], "label": "New person"},
        )
        active_global_rename = client.put(
            f"/api/meetings/{active_id}/speakers/S01/name",
            json={"label": "Global", "save_voiceprint": False},
        )
        reopened = client.get(f"/api/meetings/{terminal_id}").json()
        return {
            "active_passage_status": active_edit.status_code,
            "terminal_passage_status": terminal_edit.status_code,
            "active_global_rename_status": active_global_rename.status_code,
            "reopened_has_needs_review": "needs_review" in reopened,
            "reopened_speakers": [row["speaker"] for row in reopened["transcript"]["segments"]],
            "reopened_words": [row["text"] for row in reopened["transcript"]["segments"]],
            "voiceprints": client.get("/api/voiceprints").json()["voiceprints"],
            "contract_pass": (
                active_edit.status_code == 409
                and terminal_edit.status_code == 200
                and reopened.get("needs_review") is True
                and reopened["transcript"]["segments"][2]["speaker"] == "Speaker uncertain"
            ),
        }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="moss-publication-probe-") as directory:
        result = {
            "question": "Do abort cleanup and settled passage correction preserve publication authority?",
            "lifecycle": lifecycle_probe(),
            "correction": correction_probe(Path(directory)),
        }
    result["verdict"] = (
        "PASS" if result["lifecycle"]["contract_pass"] and result["correction"]["contract_pass"]
        else "REJECT CURRENT DESIGN"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
