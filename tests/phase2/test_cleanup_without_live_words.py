"""A Gemini live meeting that kept no word has no saved transcript when Stop completes.

Its post-Stop clean-up must still settle: done (with any word it recovers) or failed.
"""
from __future__ import annotations

import asyncio
import base64
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.gemini_live_runtime import (
    GeminiBase, GeminiLiveRuntime, GeminiRolling, GeminiSegment, ScriptedGeminiEngine)
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds, LiveServiceConfigHashes, LiveServiceDescriptor)
from moss_transcribe_diarize.app.live_session import LIVE_SAMPLE_RATE
from moss_transcribe_diarize.app.phase2 import (
    REFINEMENT_FAILED_NOTICE, REFINEMENT_RUNNING_MARKER)
from test_owner_bound_live_meeting import make_app, provision, session


@pytest.mark.parametrize("cleanup, state, texts", [
    ("empty", "done", []),                      # the field case: no words live, none after
    ("finds_words", "done", ["recovered"]),     # clean-up hears what the live pass dropped
    ("fails", "failed", None),                  # provider error; nothing was ever saved
])
def test_gemini_cleanup_settles_a_meeting_that_never_saved_a_transcript(
    tmp_path, cleanup, state, texts,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))

    class WordlessLive(ScriptedGeminiEngine):
        def push_audio(self, start_sample, pcm16):
            self.end_sample = start_sample + len(pcm16) // 2

        async def drain_tail(self, deadline):
            # The live pass covered all the audio and kept no word (gated microphone, silent tab).
            self._publish(GeminiBase(self.end_sample, ()))
            self._publish(GeminiRolling(0, self.end_sample, (),
                                        revision_lanes=("system", "microphone")))
            return True

        async def finish(self, tape):
            if cleanup == "fails":
                raise RuntimeError("terminal decode refused")
            if cleanup == "finds_words":
                return (GeminiSegment(0, self.end_sample, "recovered", "terminal-a", "microphone"),)
            return ()

    descriptor = LiveServiceDescriptor(
        source_revision="test", provider_name="gemini", provider_revision="test",
        provider_manifest_hash="0" * 64,
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={}, identity_config={}, decoder_config={}),
        bounds=LiveServiceBounds(max_frame_samples=16000, max_queue_depth=4,
                                 max_retained_samples=32000, max_identity_speakers=8,
                                 max_events=64, max_tape_bytes=160000), frame_samples=16000,
    )

    def runtime(tapes: str) -> GeminiLiveRuntime:
        return GeminiLiveRuntime(
            descriptor=descriptor, tape_storage_root=tmp_path / tapes,
            engine_factory=lambda _id, publish, _usage, _settings: WordlessLive(
                publish, batches=[], terminal=()))

    def stored_notice(meeting_id: str) -> str | None:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT notice FROM meeting_outcomes WHERE meeting_id = ?", (meeting_id,)).fetchone()
        finally:
            connection.close()
        return None if row is None else row[0]

    live_runtime = runtime("tapes")
    app = make_app(database, live_runtime_factory=lambda: live_runtime)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions", json={"engine_settings": {
            "transcription": {"api_key": "user-key"}}}).json()["id"]
        for sequence in range(3):
            for lane in ("system", "microphone"):
                payload = {
                    "lane": lane, "sequence": sequence,
                    "capture_timestamp_ns": sequence * 1_000_000_000, "device_epoch": 0,
                    "pcm_base64": base64.b64encode(
                        (b"\x01\x00" if lane == "microphone" else b"\0\0") * 16000).decode("ascii"),
                    "sample_count": 16000, "sample_rate": LIVE_SAMPLE_RATE,
                    "silent": False, "discontinuity": False,
                }
                assert client.post(f"/api/live/sessions/{meeting_id}/frames", json=payload).status_code == 200
        assert client.post(f"/api/live/sessions/{meeting_id}/stop", json={"deadline": 2}).status_code in {200, 202}
        # Wait for the runtime's own ending, then for the Account bridge to have consumed it.
        client.portal.call(live_runtime.wait_terminal, meeting_id)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            detail = client.get(f"/api/meetings/{meeting_id}").json()
            if detail["status"] == "completed" and detail["refinement_state"] != "running":
                break
            time.sleep(.01)
        assert detail["status"] == "completed"

        # The clean-up ended, so its durable marker must have ended too.
        assert stored_notice(meeting_id) != REFINEMENT_RUNNING_MARKER
        assert detail["refinement_state"] == state, detail
        if state == "done":
            assert "notice" not in detail and detail["needs_review"] is False
            assert detail["refined_version"] == detail["transcript_version"]
            assert [row["text"] for row in detail["transcript"]["segments"]] == texts
        else:
            assert stored_notice(meeting_id) == REFINEMENT_FAILED_NOTICE
            assert detail["notice"] == REFINEMENT_FAILED_NOTICE
        # The capture page's own view of the session reaches the same ending.
        snapshot = client.get(f"/api/live/sessions/{meeting_id}/snapshot").json()["snapshot"]
        assert snapshot["session"]["finalization_status"] == ("final" if state == "done" else "failed")
        assert not app.state.phase2_live.refinement_running(meeting_id)

    # A restart reads the same ending: nothing is left for crash recovery to call interrupted.
    with TestClient(make_app(database, live_runtime_factory=lambda: runtime("restarted-tapes")),
                    base_url="https://moss.test") as client:
        session(client, sessions["a"])
        assert client.get(f"/api/meetings/{meeting_id}").json()["refinement_state"] == state
        assert client.delete(f"/api/meetings/{meeting_id}").status_code == 204
