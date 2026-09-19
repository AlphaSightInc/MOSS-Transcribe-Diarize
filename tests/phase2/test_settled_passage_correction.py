"""Settled recording-local passage correction and saved review truth."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import create_phase2_app
from test_owner_bound_live_meeting import provision, session


async def _seed(app, sign_in_session: str, status: str) -> str:
    account = await app.state.phase2_store.account_for_session(sign_in_session)
    handle = await app.state.phase2_store.workspace(account).create_meeting("file")
    document = {
        "segments": [
            {
                "id": "seg_0001",
                "start": 0.0,
                "end": 1.0,
                "speaker_entity_id": "person-a",
                "speaker": "Alex",
                "text": "first words",
            },
            {
                "id": "seg_0002",
                "start": 1.0,
                "end": 2.0,
                "speaker_entity_id": "person-a",
                "speaker": "Alex",
                "text": "selected words",
            },
            {
                "id": "seg_0003",
                "start": 2.0,
                "end": 3.0,
                "speaker": "S00",
                "text": "uncertain words",
            },
        ]
    }
    if status == "active":
        await handle.commit_transcript(document)
    else:
        await handle.finish_with_transcript(document, status)
    return handle.meeting_id


def test_passage_correction_refuses_unsettled_and_persists_exact_new_person(tmp_path):
    database = tmp_path / "m.sqlite"
    sessions = asyncio.run(provision(database))
    app = create_phase2_app(database_path=database)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        active_id = client.portal.call(_seed, app, sessions["a"], "active")
        refused = client.put(
            f"/api/meetings/{active_id}/passages/speaker",
            json={"segment_ids": ["seg_0002"], "label": "Blair"},
        )
        assert refused.status_code == 409
        assert refused.json()["detail"] == "Wait for automatic processing to settle before correcting speakers."

        meeting_id = client.portal.call(_seed, app, sessions["a"], "completed")
        before = client.get(f"/api/meetings/{meeting_id}").json()
        assert before["needs_review"] is True
        assert before["transcript"]["segments"][2] == {
            "id": "seg_0003",
            "start": 2.0,
            "end": 3.0,
            "speaker_entity_id": "S00",
            "speaker": "Speaker uncertain",
            "text": "uncertain words",
        }
        original_words = [row["text"] for row in before["transcript"]["segments"]]

        changed = client.put(
            f"/api/meetings/{meeting_id}/passages/speaker",
            json={"segment_ids": ["seg_0002"], "label": "Blair"},
        )
        assert changed.status_code == 200, changed.text
        result = changed.json()
        assert result["meeting_id"] == meeting_id
        assert result["segment_ids"] == ["seg_0002"]
        assert result["label"] == "Blair"
        assert result["speaker_id"].startswith("manual-")
        assert result["needs_review"] is True

        reopened = client.get(f"/api/meetings/{meeting_id}").json()
        rows = reopened["transcript"]["segments"]
        assert [row["text"] for row in rows] == original_words
        assert [row["speaker"] for row in rows] == ["Alex", "Blair", "Speaker uncertain"]
        assert rows[0]["speaker_entity_id"] == "person-a"
        assert rows[1]["speaker_entity_id"] == result["speaker_id"]
        assert rows[2]["speaker_entity_id"] == "S00"
        assert reopened["transcript_version"] == before["transcript_version"] + 1
        assert client.get("/api/voiceprints").json() == {"voiceprints": []}


def test_passage_correction_to_existing_person_clears_review_and_is_owner_bound(tmp_path):
    database = tmp_path / "m.sqlite"
    sessions = asyncio.run(provision(database))
    app = create_phase2_app(database_path=database)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.portal.call(_seed, app, sessions["a"], "completed")
        corrected = client.put(
            f"/api/meetings/{meeting_id}/passages/speaker",
            json={"segment_ids": ["seg_0003"], "speaker_id": "person-a"},
        )
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()["label"] == "Alex"
        assert corrected.json()["needs_review"] is False
        reopened = client.get(f"/api/meetings/{meeting_id}").json()
        assert reopened["needs_review"] is False
        assert [row["speaker"] for row in reopened["transcript"]["segments"]] == [
            "Alex", "Alex", "Alex"
        ]
        assert [row["text"] for row in reopened["transcript"]["segments"]] == [
            "first words", "selected words", "uncertain words"
        ]
        assert client.get("/api/voiceprints").json() == {"voiceprints": []}

        session(client, sessions["b"])
        foreign = client.put(
            f"/api/meetings/{meeting_id}/passages/speaker",
            json={"segment_ids": ["seg_0001"], "label": "Foreign"},
        )
        assert foreign.status_code == 404


def test_passage_correction_rejects_missing_or_ambiguous_targets(tmp_path):
    database = tmp_path / "m.sqlite"
    sessions = asyncio.run(provision(database))
    app = create_phase2_app(database_path=database)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.portal.call(_seed, app, sessions["a"], "completed")
        cases = [
            ({"segment_ids": [], "label": "Blair"}, 400),
            ({"segment_ids": ["missing"], "label": "Blair"}, 404),
            ({"segment_ids": ["seg_0001"], "speaker_id": "missing"}, 404),
            ({"segment_ids": ["seg_0001"], "speaker_id": "person-a", "label": "Blair"}, 400),
        ]
        for payload, expected in cases:
            response = client.put(
                f"/api/meetings/{meeting_id}/passages/speaker", json=payload
            )
            assert response.status_code == expected, (payload, response.text)


@pytest.mark.parametrize("unknown_id", ["S00", "UNKNOWN"])
def test_persisted_unknown_ids_stay_reviewable_when_another_passage_changes(
    tmp_path, unknown_id
):
    """S00 is emitted by saved Live; UNKNOWN is the legacy transcript fallback."""

    database = tmp_path / "m.sqlite"
    sessions = asyncio.run(provision(database))
    app = create_phase2_app(database_path=database)

    async def seed() -> str:
        account = await app.state.phase2_store.account_for_session(sessions["a"])
        handle = await app.state.phase2_store.workspace(account).create_meeting("live")
        await handle.finish_with_transcript(
            {
                "segments": [
                    {
                        "id": "known",
                        "start": 0.0,
                        "end": 1.0,
                        "speaker_entity_id": "person-a",
                        "speaker": "Alex",
                        "text": "known words",
                    },
                    {
                        "id": "unknown",
                        "start": 1.0,
                        "end": 2.0,
                        "speaker_entity_id": unknown_id,
                        "speaker": unknown_id,
                        "text": "unattributed words",
                    },
                ]
            },
            "completed",
        )
        return handle.meeting_id

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.portal.call(seed)
        before = client.get(f"/api/meetings/{meeting_id}").json()
        assert before["needs_review"] is True
        assert before["transcript"]["segments"][1]["speaker"] == "Speaker uncertain"

        changed = client.put(
            f"/api/meetings/{meeting_id}/passages/speaker",
            json={"segment_ids": ["known"], "label": "Blair"},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["needs_review"] is True

        reopened = client.get(f"/api/meetings/{meeting_id}").json()
        assert reopened["needs_review"] is True
        assert reopened["transcript"]["segments"][1] == {
            "id": "unknown",
            "start": 1.0,
            "end": 2.0,
            "speaker_entity_id": "S00",
            "speaker": "Speaker uncertain",
            "text": "unattributed words",
        }
        assert client.put(
            f"/api/meetings/{meeting_id}/passages/speaker",
            json={"segment_ids": ["known"], "speaker_id": unknown_id},
        ).status_code == 404
