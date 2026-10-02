"""A live meeting keeps `moss:refinement:running` in its outcome while post-Stop clean-up runs.

A process that ends first leaves that marker behind; no clean-up can be running in the next
process, so the meeting must behave as a failed clean-up: live transcript kept, corrections
and deletion allowed.
"""
from __future__ import annotations

import asyncio
import base64
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds, LiveServiceConfigHashes, LiveServiceDescriptor)
from moss_transcribe_diarize.app.live_session import LIVE_SAMPLE_RATE
from moss_transcribe_diarize.app.phase2 import (
    MeetingNotSettled, REFINEMENT_FAILED_NOTICE, REFINEMENT_RUNNING_MARKER, create_phase2_app)
from test_owner_bound_live_meeting import make_app, provision, session

DOCUMENT = {"segments": [
    {"id": "seg_0001", "start": 0., "end": 1., "speaker_entity_id": "speaker-0001",
     "speaker": "Speaker 1", "text": "live words", "source_lane": "system"},
    {"id": "seg_0002", "start": 1., "end": 2., "speaker_entity_id": "speaker-0002",
     "speaker": "Speaker 2", "text": "more live words", "source_lane": "system"},
]}


def stored_notice(database, meeting_id):
    with sqlite3.connect(database) as db:
        row = db.execute("SELECT notice FROM meeting_outcomes WHERE meeting_id=?",
                         (meeting_id,)).fetchone()
    return None if row is None else row[0]


def left_by_an_ended_process(database, token, notice=REFINEMENT_RUNNING_MARKER, mode="live"):
    """Process 1: a completed meeting whose outcome row is as that process left it."""
    app = create_phase2_app(database_path=database)
    with TestClient(app, base_url="https://moss.test") as client:
        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(token)
            handle = await store.workspace(account).create_meeting(mode)
            await handle.finish_with_transcript(DOCUMENT, "completed", notice=notice)
            return handle.meeting_id
        return client.portal.call(seed)


def test_restart_makes_a_leftover_running_cleanup_editable_and_deletable(tmp_path):
    database = tmp_path / "moss.sqlite3"
    tokens = asyncio.run(provision(database))
    meeting_id = left_by_an_ended_process(database, tokens["a"])
    assert stored_notice(database, meeting_id) == REFINEMENT_RUNNING_MARKER
    with TestClient(make_app(database), base_url="https://moss.test") as client:   # process 2
        session(client, tokens["a"])
        path = f"/api/meetings/{meeting_id}"
        detail = client.get(path).json()
        assert (detail["refinement_state"], detail["notice"]) == ("failed", REFINEMENT_FAILED_NOTICE)
        edited = client.put(f"{path}/passages/seg_0001/text", json={"text": "my correction"})
        assert edited.status_code == 200, edited.text
        moved = client.put(f"{path}/passages/speaker",
                           json={"segment_ids": ["seg_0002"], "label": "Blair"})
        assert moved.status_code == 200, moved.text
        rows = client.get(path).json()["transcript"]["segments"]
        assert [(row["text"], row["speaker"]) for row in rows] == [
            ("my correction", "Speaker 1"), ("more live words", "Blair")]
        assert client.delete(path).status_code == 204
        assert client.get("/api/meetings").json() == {"meetings": []}


def test_restart_stores_the_failed_form_for_a_leftover_running_marker(tmp_path):
    """The database itself stops saying "running": one stored truth for every reader."""
    database = tmp_path / "moss.sqlite3"
    tokens = asyncio.run(provision(database))
    meeting_id = left_by_an_ended_process(database, tokens["a"])
    with TestClient(make_app(database), base_url="https://moss.test"):
        assert stored_notice(database, meeting_id) == REFINEMENT_FAILED_NOTICE


def test_gemini_cleanup_interrupted_by_restart_can_be_corrected(tmp_path):
    """End to end: a real live meeting, the clean-up held open, the server restarted."""
    from moss_transcribe_diarize.app.gemini_live_runtime import (
        GeminiBase, GeminiLiveRuntime, GeminiRolling, GeminiSegment, ScriptedGeminiEngine)

    database = tmp_path / "moss.sqlite3"
    tokens = asyncio.run(provision(database))
    never = asyncio.Event()

    class HeldTerminal(ScriptedGeminiEngine):
        def push_audio(self, start_sample, pcm16):
            self.end_sample = start_sample + len(pcm16) // 2

        async def drain_tail(self, deadline):
            self._publish(GeminiBase(self.end_sample, ()))
            self._publish(GeminiRolling(0, self.end_sample, (
                GeminiSegment(0, self.end_sample, "live", "speaker-0001", "system"),),
                revision_lanes=("system",)))
            return True

        async def finish(self, tape):
            await never.wait()

    descriptor = LiveServiceDescriptor(
        source_revision="test", provider_name="gemini", provider_revision="test",
        provider_manifest_hash="0" * 64,
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={}, identity_config={}, decoder_config={}),
        bounds=LiveServiceBounds(max_frame_samples=16000, max_queue_depth=4,
                                 max_retained_samples=32000, max_identity_speakers=8,
                                 max_events=64, max_tape_bytes=160000), frame_samples=16000)

    def app(tapes):
        return make_app(database, live_runtime_factory=lambda: GeminiLiveRuntime(
            descriptor=descriptor, tape_storage_root=tmp_path / tapes,
            engine_factory=lambda _id, publish, _usage, _settings: HeldTerminal(
                publish, batches=[], terminal=())))

    with TestClient(app("tapes"), base_url="https://moss.test") as client:
        session(client, tokens["a"])
        meeting_id = client.post("/api/live/sessions", json={"engine_settings": {
            "transcription": {"api_key": "user-key"}}}).json()["id"]
        for sequence in range(3):
            for lane in ("system", "microphone"):
                assert client.post(f"/api/live/sessions/{meeting_id}/frames", json={
                    "lane": lane, "sequence": sequence,
                    "capture_timestamp_ns": sequence * 1_000_000_000, "device_epoch": 0,
                    "pcm_base64": base64.b64encode(
                        (b"\x01\x00" if lane == "system" else b"\0\0") * 16000).decode("ascii"),
                    "sample_count": 16000, "sample_rate": LIVE_SAMPLE_RATE,
                    "silent": False, "discontinuity": False}).status_code == 200
        assert client.post(f"/api/live/sessions/{meeting_id}/stop",
                           json={"deadline": 2}).status_code in {200, 202}
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            detail = client.get(f"/api/meetings/{meeting_id}").json()
            if detail["status"] == "completed":
                break
            time.sleep(.01)
        assert detail["refinement_state"] == "running", detail
        # While it really runs, corrections stay refused (the protection to keep).
        running = client.put(f"/api/meetings/{meeting_id}/passages/seg_0001/text",
                             json={"text": "too early"})
        assert (running.status_code, running.json()) == (409, {"code": "refinement_running"})
    # A graceful shutdown cancels the clean-up, removes its staged audio, and leaves the marker.
    assert not list((database.parent / "meetings").glob("**/.live-mix.pcm"))
    assert stored_notice(database, meeting_id) == REFINEMENT_RUNNING_MARKER
    with TestClient(app("restarted-tapes"), base_url="https://moss.test") as client:
        session(client, tokens["a"])
        path = f"/api/meetings/{meeting_id}"
        assert client.get(path).json()["refinement_state"] == "failed"
        edited = client.put(f"{path}/passages/seg_0001/text", json={"text": "my correction"})
        assert edited.status_code == 200, edited.text
        assert client.get(path).json()["transcript"]["segments"][0]["text"] == "my correction"
        assert client.get(f"{path}/audio/download").status_code == 200
        assert client.delete(path).status_code == 204


@pytest.mark.parametrize("notice", ["moss:refinement:done:1", "moss:refinement:done",
                                    REFINEMENT_FAILED_NOTICE, "synthetic outcome", None])
def test_restart_leaves_every_other_outcome_as_stored(tmp_path, notice):
    database = tmp_path / "moss.sqlite3"
    tokens = asyncio.run(provision(database))
    meeting_id = left_by_an_ended_process(database, tokens["a"], notice)
    with TestClient(make_app(database), base_url="https://moss.test") as client:
        session(client, tokens["a"])
        before = client.get(f"/api/meetings/{meeting_id}").json()
    with TestClient(make_app(database), base_url="https://moss.test") as client:
        session(client, tokens["a"])
        assert client.get(f"/api/meetings/{meeting_id}").json() == before
        assert stored_notice(database, meeting_id) == notice


def test_a_marker_written_in_this_process_still_refuses_text_edit_under_the_write_lock(tmp_path):
    """The store check is what protects an edit that got past the route check."""
    database = tmp_path / "moss.sqlite3"
    tokens = asyncio.run(provision(database))
    app = make_app(database)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, tokens["a"])

        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(tokens["a"])
            handle = await store.workspace(account).create_meeting("live")
            await handle.finish_with_transcript(DOCUMENT, "completed",
                                                notice=REFINEMENT_RUNNING_MARKER)
            return handle

        handle = client.portal.call(seed)
        # What a real clean-up sets in memory at the same moment it stores the marker.
        app.state.phase2_live.refinement_running = lambda meeting_id: meeting_id == handle.meeting_id
        with pytest.raises(MeetingNotSettled):
            client.portal.call(handle.edit_passage_text, "seg_0001", "too early")
        assert client.portal.call(handle.settle_refinement, DOCUMENT) == 2
        app.state.phase2_live.refinement_running = lambda meeting_id: False
        assert client.put(f"/api/meetings/{handle.meeting_id}/passages/seg_0001/text",
                          json={"text": "after clean-up"}).status_code == 200


def test_restart_discards_the_staged_audio_a_killed_cleanup_left(tmp_path):
    database = tmp_path / "moss.sqlite3"
    tokens = asyncio.run(provision(database))
    meeting_id = left_by_an_ended_process(database, tokens["a"])
    with sqlite3.connect(database) as db:
        account_id, = db.execute("SELECT account_id FROM meetings WHERE meeting_id=?",
                                 (meeting_id,)).fetchone()
    stage = database.parent / "meetings" / account_id / meeting_id / ".live-mix.pcm"
    stage.parent.mkdir(parents=True, exist_ok=True)
    stage.write_bytes(b"\0\0" * 16000)
    with TestClient(make_app(database), base_url="https://moss.test"):
        assert not stage.exists()
