"""P75 E1 server: synthetic documents, real durable store, fake summary generator."""
from __future__ import annotations

import asyncio
import copy

import pytest
from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import (
    AccountRevoked, MeetingNotSettled, REFINEMENT_RUNNING_MARKER, create_phase2_app,
    readable_transcript,
)
from test_owner_bound_live_meeting import provision, session

DOCUMENT = {"segments": [
    {"id": "seg_0001", "start": 0., "end": 1., "speaker_entity_id": "person-a",
     "speaker": "Alex", "text": "first words", "source_lane": "system"},
    {"id": "seg_0002", "start": 1., "end": 2., "speaker_entity_id": "person-a",
     "speaker": "Alex", "text": "selected words", "source_lane": "microphone",
     "words": [{"text": "selected", "start": 1., "end": 1.5},
               {"text": "words", "start": 1.5, "end": 2.}]},
    {"id": "seg_0003", "start": 2., "end": 3., "speaker_entity_id": "person-b",
     "speaker": "Blair", "text": "other words"},
]}


async def seed(app, credential, status="completed", notice=None):
    store = app.state.phase2_store
    account = await store.account_for_session(credential)
    handle = await store.workspace(account).create_meeting("file")
    document = copy.deepcopy(DOCUMENT)
    if status == "active":
        await handle.commit_transcript(document)
    else:
        await handle.finish_with_transcript(document, status, notice=notice)
    return handle


@pytest.fixture
def workspace(tmp_path):
    database = tmp_path / "m.sqlite"
    sessions = asyncio.run(provision(database))
    calls = []

    async def generate(document, **kwargs):
        calls.append(document)
        return ({"summary": "Synthetic summary.", "topics": [], "details": [],
                 "speaker_background": [], "data_references": []},
                {"model": "gemini-3.5-flash-lite", "input_tokens": 10,
                 "output_tokens": 5, "cost_usd": 0.})

    app = create_phase2_app(database_path=database, summary_generator=generate)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        handle = client.portal.call(seed, app, sessions["a"])
        yield app, client, handle, sessions, database, calls


def edit(client, meeting_id, text, passage_id="seg_0002"):
    return client.put(f"/api/meetings/{meeting_id}/passages/{passage_id}/text", json={"text": text})


def test_one_text_edit_preserves_other_passages_speakers_times_and_advances_version(workspace):
    app, client, handle, _, _, _ = workspace
    before = client.get(f"/api/meetings/{handle.meeting_id}").json()
    changed = edit(client, handle.meeting_id, "  corrected words \n")
    assert changed.status_code == 200, changed.text
    assert changed.json() == {
        "meeting_id": handle.meeting_id, "segment_ids": ["seg_0002"],
        "speaker_id": "person-a", "label": "Alex", "transcript_version": 2,
        "needs_review": False,
    }
    after = client.get(f"/api/meetings/{handle.meeting_id}").json()
    expected = copy.deepcopy(before["transcript"])
    expected["segments"][1].update(text="corrected words", edited=True, original_text="selected words")
    expected["segments"][1].pop("words")
    assert after["transcript"] == expected
    assert after["transcript_version"] == before["transcript_version"] + 1
    assert after["audio"] == before["audio"]
    assert client.portal.call(handle.snapshot).transcript == expected


def test_second_text_edit_keeps_first_original(workspace):
    _, client, handle, _, _, _ = workspace
    assert edit(client, handle.meeting_id, "first correction").status_code == 200
    assert edit(client, handle.meeting_id, "second correction").status_code == 200
    state = client.get(f"/api/meetings/{handle.meeting_id}").json()
    assert state["transcript"]["segments"][1]["original_text"] == "selected words"
    assert state["transcript"]["segments"][1]["text"] == "second correction"
    assert state["transcript_version"] == 3


@pytest.mark.parametrize("text", ["", " \n\t ", "x" * 5001, None, 123, [], {}],
                         ids=["empty", "whitespace", "too-long", "null", "number", "list", "object"])
def test_text_edit_invalid_text_is_400_and_does_not_mutate(workspace, text):
    _, client, handle, _, _, _ = workspace
    before = client.get(f"/api/meetings/{handle.meeting_id}").json()
    response = edit(client, handle.meeting_id, text)
    assert response.status_code == 400, response.text
    assert client.get(f"/api/meetings/{handle.meeting_id}").json() == before


@pytest.mark.parametrize("text", ["a", "x" * 5000, "  " + "x" * 5000 + "  "],
                         ids=["one-char", "max-length", "trim-before-length"])
def test_text_edit_accepts_trimmed_length_boundaries(workspace, text):
    _, client, handle, _, _, _ = workspace
    assert edit(client, handle.meeting_id, text).status_code == 200
    state = client.get(f"/api/meetings/{handle.meeting_id}").json()
    assert state["transcript"]["segments"][1]["text"] == text.strip()


@pytest.mark.parametrize("body", [{}, [], {"text": None}])
def test_text_edit_invalid_body_is_400(workspace, body):
    _, client, handle, _, _, _ = workspace
    response = client.put(f"/api/meetings/{handle.meeting_id}/passages/seg_0002/text", json=body)
    assert response.status_code == 400


def test_text_edit_unknown_passage_is_404(workspace):
    _, client, handle, _, _, _ = workspace
    assert edit(client, handle.meeting_id, "corrected").status_code == 200
    assert edit(client, handle.meeting_id, "corrected", "missing").status_code == 404


def test_text_edit_other_account_is_404(workspace):
    _, client, handle, sessions, _, _ = workspace
    session(client, sessions["b"])
    assert edit(client, handle.meeting_id, "foreign").status_code == 404
    session(client, sessions["a"])
    # Prove the endpoint exists, and the foreign request changed nothing.
    assert client.get(f"/api/meetings/{handle.meeting_id}").json()["transcript_version"] == 1
    assert edit(client, handle.meeting_id, "owner").status_code == 200


@pytest.mark.parametrize("status,notice", [("active", None), ("completed", REFINEMENT_RUNNING_MARKER)])
def test_text_edit_not_settled_is_409_in_route_and_store(workspace, status, notice):
    app, client, _, sessions, _, _ = workspace
    handle = client.portal.call(seed, app, sessions["a"], status, notice)
    before = client.get(f"/api/meetings/{handle.meeting_id}").json()
    blocked = edit(client, handle.meeting_id, "too early")
    assert blocked.status_code == 409, blocked.text
    if status == "active":
        assert blocked.json() == {"detail": "Wait for automatic processing to settle before correcting speakers."}
    else:
        assert blocked.json() == {"code": "refinement_running"}
    with pytest.raises(MeetingNotSettled):
        client.portal.call(handle.edit_passage_text, "seg_0002", "too early")
    assert client.get(f"/api/meetings/{handle.meeting_id}").json() == before
    if notice:
        client.portal.call(handle.settle_refinement, DOCUMENT)
        assert edit(client, handle.meeting_id, "after refinement").status_code == 200


def test_text_edit_survives_history_and_server_restart(tmp_path):
    database = tmp_path / "restart.sqlite"
    sessions = asyncio.run(provision(database))
    app = create_phase2_app(database_path=database)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        handle = client.portal.call(seed, app, sessions["a"])
        assert edit(client, handle.meeting_id, "history correction").status_code == 200
        history = client.get("/api/meetings").json()["meetings"]
        assert history[0]["transcript"]["segments"][1]["text"] == "history correction"
    with TestClient(create_phase2_app(database_path=database), base_url="https://moss.test") as reopened:
        session(reopened, sessions["a"])
        state = reopened.get(f"/api/meetings/{handle.meeting_id}").json()
        assert state["transcript"]["segments"][1]["text"] == "history correction"
        assert state["transcript"]["segments"][1]["original_text"] == "selected words"
        assert state["transcript_version"] == 2


def test_speaker_reassignment_after_edit_keeps_text(workspace):
    _, client, handle, _, _, _ = workspace
    assert edit(client, handle.meeting_id, "my correction").status_code == 200
    reassigned = client.put(f"/api/meetings/{handle.meeting_id}/passages/speaker",
                            json={"segment_ids": ["seg_0002"], "speaker_id": "person-b"})
    assert reassigned.status_code == 200
    row = client.get(f"/api/meetings/{handle.meeting_id}").json()["transcript"]["segments"][1]
    assert (row["text"], row["original_text"], row["edited"]) == ("my correction", "selected words", True)
    assert row["speaker"] == "Blair"


def test_rename_all_after_edit_keeps_text(workspace):
    _, client, handle, _, _, _ = workspace
    assert edit(client, handle.meeting_id, "my correction").status_code == 200
    renamed = client.put(f"/api/meetings/{handle.meeting_id}/speakers/person-a/name",
                         json={"label": "New Alex", "save_voiceprint": False})
    assert renamed.status_code == 200, renamed.text
    rows = client.get(f"/api/meetings/{handle.meeting_id}").json()["transcript"]["segments"]
    assert [row["speaker"] for row in rows] == ["New Alex", "New Alex", "Blair"]
    assert (rows[1]["text"], rows[1]["original_text"], rows[1]["edited"]) == ("my correction", "selected words", True)


def test_later_production_publications_cannot_overwrite_text_edit(workspace):
    _, client, handle, _, _, _ = workspace
    assert edit(client, handle.meeting_id, "durable correction").status_code == 200
    with pytest.raises(AccountRevoked):
        client.portal.call(handle.commit_transcript, DOCUMENT)
    with pytest.raises(AccountRevoked):
        client.portal.call(handle.finish_with_transcript, DOCUMENT, "completed")
    with pytest.raises(AccountRevoked):
        client.portal.call(handle.settle_refinement, DOCUMENT)
    assert client.get(f"/api/meetings/{handle.meeting_id}").json()["transcript"]["segments"][1]["text"] == "durable correction"


def test_on_demand_summary_gets_edited_text_and_preserves_manual_spaces(workspace):
    _, client, handle, _, _, calls = workspace
    text = "大 家好，these are intentional spaces."
    assert edit(client, handle.meeting_id, text).status_code == 200
    response = client.post(f"/api/meetings/{handle.meeting_id}/summary/server", json={
        "source_version": 2,
        "provider": {"vendor": "gemini", "model": "gemini-3.5-flash-lite", "api_key": "synthetic-key"},
    })
    assert response.status_code == 200, response.text
    assert calls[0]["segments"][1]["text"] == text
    assert "words" not in calls[0]["segments"][1]
    assert client.get(f"/api/meetings/{handle.meeting_id}").json()["transcript"]["segments"][1]["text"] == text


def test_readable_transcript_keeps_user_edited_text_exact():
    document = {"segments": [{"id": "seg_0001", "text": "大 家好", "edited": True},
                             {"id": "seg_0002", "text": "大 家好"}]}
    result = readable_transcript(document)
    assert result["segments"][0]["text"] == "大 家好"
    assert result["segments"][1]["text"] == "大家好"
    assert document["segments"][1]["text"] == "大 家好"
