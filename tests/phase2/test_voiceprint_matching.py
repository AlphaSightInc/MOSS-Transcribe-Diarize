from __future__ import annotations

import asyncio
import math
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2_voiceprint_match import VoiceprintProfile, match_voiceprint, normalized_mean
from tests.phase2.test_owner_bound_live_meeting import EligibleIdentity, feed_two_lane_span, make_app, provision, session, wait_snapshot


def observation(vector=(1., 0.), seconds=1., embedder="test", provisional=False):
    return SimpleNamespace(speaker_label="speaker-0001", centroid=vector, sample_seconds=seconds,
                           embedder_id=embedder, provisional=provisional)


def test_measured_rule_floors_compatibility_abstention_and_duplicate_names():
    a = VoiceprintProfile("a", "Alex", "test", (1., 0.))
    b = VoiceprintProfile("b", "Alex", "test", (0., 1.))
    incompatible = VoiceprintProfile("c", "Other", "old", (1., 0.))
    assert match_voiceprint(observation(), (a, b, incompatible)) == a
    assert match_voiceprint(observation((0., 1.)), (a, b)) == b
    assert match_voiceprint(observation(), (b, incompatible)) is None
    assert match_voiceprint(observation(seconds=.999), (a,)) is None
    assert match_voiceprint(observation(seconds=1.), (a,)) == a
    assert match_voiceprint(observation(provisional=True), (a,)) is None
    assert match_voiceprint(observation((math.nan, 0.)), (a,)) is None
    assert match_voiceprint(observation(), ()) is None
    for score, accepted in ((.459, False), (.46, True), (.461, True)):
        vector = (score, math.sqrt(1 - score * score))
        assert (match_voiceprint(observation(vector), (a,)) is not None) == accepted
    assert normalized_mean(((1., 0.), (0., 1.))) == pytest.approx((2 ** -.5, 2 ** -.5))
    assert normalized_mean(((1., 0.), (-1., 0.))) is None
    assert normalized_mean(((1., 0.), (1.,))) is None


class RecognizableIdentity(EligibleIdentity):
    def match_observations(self, *, base_snapshot):
        return tuple(observation((.6, .8), seconds=1., embedder="wespeaker:test-revision")
                     for _ in base_snapshot.canonical_speakers)


def test_live_one_second_recognition_is_private_never_enrolls_and_delete_fences_prepared_result(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database, identity_factory=RecognizableIdentity)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        enrolled = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, enrolled)
        wait_snapshot(client, enrolled, lambda body: body["meeting_transcript_version"] == 1)
        named = client.put(f"/api/meetings/{enrolled}/speakers/speaker-0001/name", json={"label": "Alex"}).json()
        assert client.post(f"/api/live/sessions/{enrolled}/stop", json={"deadline": 2.0}).status_code == 200
        bank = client.get("/api/voiceprints").json()

        recognized = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, recognized)
        result = wait_snapshot(client, recognized, lambda body: body["speaker_labels"] == {"speaker-0001": "Alex"})
        assert result["meeting_transcript_version"] == 1
        assert client.get(f"/api/meetings/{recognized}").json()["transcript"]["segments"][0]["speaker"] == "Alex"
        assert client.get("/api/voiceprints").json() == bank

        other_active = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, other_active)
        wait_snapshot(client, other_active, lambda body: body["speaker_labels"] == {"speaker-0001": "Alex"})
        manual = client.put(f"/api/meetings/{recognized}/speakers/speaker-0001/name", json={"label": "Sam"})
        assert manual.status_code == 200
        assert client.get(f"/api/live/sessions/{other_active}/snapshot").json()["speaker_labels"] == {"speaker-0001": "Sam"}
        assert client.get(f"/api/meetings/{enrolled}").json()["transcript"]["segments"][0]["speaker"] == "Alex"
        assert client.get("/api/voiceprints").json()["voiceprints"][0]["sample_count"] == 2

        identity = app.state.phase2_speaker_identity
        handle = app.state.phase2_live._bindings[recognized].handle
        prepared = client.portal.call(identity.prepare_matches, handle,
                                      (observation((.6, .8), embedder="wespeaker:test-revision"),))
        assert client.delete(f"/api/voiceprints/{named['voiceprint_id']}").status_code == 200
        async def stale():
            async with identity.publication(handle, (), prepared=prepared) as changes:
                assert changes == {}
        client.portal.call(stale)
        assert client.get("/api/voiceprints").json() == {"voiceprints": []}
        assert client.post(
            f"/api/live/sessions/{recognized}/stop", json={"deadline": 2.0}
        ).status_code == 200

        session(client, sessions["b"])
        foreign = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, foreign)
        result = wait_snapshot(client, foreign, lambda body: body["meeting_transcript_version"] == 1)
        assert result["speaker_labels"] == {}


def test_profile_read_failure_fences_publication_and_notifies_stop(tmp_path: Path):
    import sqlite3
    from tests.phase2.test_owner_bound_live_meeting import v2_frame
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database, identity_factory=RecognizableIdentity)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        identity = app.state.phase2_speaker_identity
        async def fail_profiles(_owner):
            raise sqlite3.OperationalError("injected bank read failure")
        identity._profiles = fail_profiles
        for sequence in range(3):
            for lane in ("system", "microphone"):
                assert client.post(f"/api/live/sessions/{meeting_id}/frames", json=v2_frame(sequence, lane)).status_code in (200, 409)
        result = wait_snapshot(client, meeting_id, lambda body: body["persistence_failure"] == "transcript_persistence_failed")
        assert result["persistence_failure"] == "transcript_persistence_failed"
        binding = app.state.phase2_live._bindings[meeting_id]
        assert not binding.worker.done()
        assert client.get(f"/api/meetings/{meeting_id}").json()["status"] == "interrupted"
        assert client.post(f"/api/live/sessions/{meeting_id}/stop", json={"deadline": 2.0}).status_code in (200, 409)
