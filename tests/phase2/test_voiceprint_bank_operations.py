from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from tests.phase2.test_owner_bound_live_meeting import (
    EligibleIdentity, feed_two_lane_span, make_app, provision, session, wait_snapshot,
)


def test_bank_rename_delete_are_exact_id_private_and_freeze_stopped_history(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database, identity_factory=EligibleIdentity)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meetings = []
        profiles = []
        for _ in range(3):
            meeting_id = client.post("/api/live/sessions").json()["id"]
            meetings.append(meeting_id)
            feed_two_lane_span(client, meeting_id)
            wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] == 1)
            named = client.put(f"/api/meetings/{meeting_id}/speakers/speaker-0001/name", json={"label": "Alex"})
            assert named.status_code == 200
            profiles.append(named.json()["voiceprint_id"])
        # Model a previously recognized exact link. Recognition quality is not
        # supplied by this fixture; it isolates bank propagation and persistence.
        async def link():
            store = app.state.phase2_store
            async with store._mutation():
                await store._connection.execute(
                    "UPDATE meeting_speakers SET voiceprint_id=? WHERE meeting_id=?",
                    (profiles[0], meetings[1]),
                )
        client.portal.call(link)
        assert client.post(f"/api/live/sessions/{meetings[0]}/stop", json={"deadline": 2.0}).status_code == 200
        stopped = client.get(f"/api/meetings/{meetings[0]}").json()

        session(client, sessions["b"])
        assert client.put(f"/api/voiceprints/{profiles[0]}/name", json={"label": "Foreign"}).status_code == 404
        assert client.delete(f"/api/voiceprints/{profiles[0]}").status_code == 404
        session(client, sessions["a"])
        renamed = client.put(f"/api/voiceprints/{profiles[0]}/name", json={"label": "Sam"})
        assert renamed.status_code == 200
        assert client.get(f"/api/meetings/{meetings[0]}").json() == stopped
        active = client.get(f"/api/meetings/{meetings[1]}").json()
        assert active["transcript"]["segments"][0]["speaker"] == "Sam"
        assert client.get(f"/api/live/sessions/{meetings[1]}/snapshot").json()["speaker_labels"] == {"speaker-0001": "Sam"}
        assert client.get(f"/api/meetings/{meetings[2]}").json()["transcript"]["segments"][0]["speaker"] == "Alex"
        assert client.put(f"/api/voiceprints/{profiles[0]}/name", json={"label": "  "}).status_code == 400
        deleted = client.delete(f"/api/voiceprints/{profiles[0]}")
        assert deleted.status_code == 200
        assert deleted.json()["bank_revision"] > renamed.json()["bank_revision"]
        assert client.get(f"/api/meetings/{meetings[0]}").json() == stopped
        assert client.get(f"/api/meetings/{meetings[1]}").json() == active
        assert {v["id"] for v in client.get("/api/voiceprints").json()["voiceprints"]} == set(profiles[1:])
        async def inspect():
            store = app.state.phase2_store
            async with store._external_read():
                for table in ("voiceprint_samples", "meeting_speakers"):
                    cursor = await store._connection.execute(f"SELECT COUNT(*) FROM {table} WHERE voiceprint_id=?", (profiles[0],))
                    assert (await cursor.fetchone())[0] == 0
                    await cursor.close()
        client.portal.call(inspect)
        assert client.delete(f"/api/voiceprints/{profiles[0]}").status_code == 404


def test_bank_cancelled_client_and_concurrent_renames_converge_after_commit(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database, identity_factory=EligibleIdentity)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] == 1)
        profile_id = client.put(f"/api/meetings/{meeting_id}/speakers/speaker-0001/name", json={"label": "Original"}).json()["voiceprint_id"]
        runtime = app.state.phase2_live.runtime
        runtime._voiceprint_embedder_identity = ("wespeaker:test-revision", 2)
        assert client.get("/api/voiceprints").json()["voiceprints"][0]["compatibility"] == "compatible"
        runtime._voiceprint_embedder_identity = ("wespeaker:replacement-revision", 2)
        assert client.get("/api/voiceprints").json()["voiceprints"][0]["compatibility"] == "re_enrollment_required"

        async def stress():
            identity = app.state.phase2_speaker_identity
            binding = app.state.phase2_live._bindings[meeting_id]
            owner = binding.owner_key
            connection = app.state.phase2_store._connection
            original_commit = connection.commit
            entered, release = asyncio.Event(), asyncio.Event()
            async def held_commit():
                await original_commit()
                entered.set()
                await release.wait()
            connection.commit = held_commit
            try:
                caller = asyncio.create_task(identity._change_voiceprint(owner, profile_id, "Durable"))
                await asyncio.wait_for(entered.wait(), 5)
                caller.cancel()
                try:
                    await caller
                except asyncio.CancelledError:
                    pass
                release.set()
                await identity.shutdown()
                assert binding.speaker_labels == {"speaker-0001": "Durable"}
            finally:
                release.set()
                connection.commit = original_commit
            results = await asyncio.gather(*(identity._change_voiceprint(owner, profile_id, f"Name {index}") for index in range(32)))
            revisions = [result["bank_revision"] for result in results]
            assert len(set(revisions)) == 32
            final = results[revisions.index(max(revisions))]["label"]
            assert binding.speaker_labels == {"speaker-0001": final}
            assert (await binding.handle.snapshot()).transcript["segments"][0]["speaker"] == final
            profiles = await identity._list_voiceprints(owner)
            assert [(profile.label, profile.sample_count) for profile in profiles] == [(final, 1)]
        client.portal.call(stress)


def test_naming_api_explicit_enrollment_choice_and_default(tmp_path: Path):
    database = tmp_path / "choice.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database, identity_factory=EligibleIdentity)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting)
        wait_snapshot(client, meeting, lambda body: body["meeting_transcript_version"] == 1)
        url = f"/api/meetings/{meeting}/speakers/speaker-0001/name"
        renamed = client.put(url, json={"label": "Local", "save_voiceprint": False})
        assert renamed.status_code == 200
        assert renamed.json()["enrollment"] == "not_requested"
        assert client.get("/api/voiceprints").json()["voiceprints"] == []
        assert client.put(url, json={"label": "Invalid", "save_voiceprint": "false"}).status_code == 400
        enrolled = client.put(url, json={"label": "Saved", "save_voiceprint": True})
        assert enrolled.status_code == 200
        assert enrolled.json()["enrollment"] == "enrolled"
        default = client.put(url, json={"label": "Default"})
        assert default.status_code == 200
        assert default.json()["enrollment"] == "enrolled"
        assert default.json()["voiceprint_id"] == enrolled.json()["voiceprint_id"]
