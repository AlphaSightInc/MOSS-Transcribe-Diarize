"""Saved transcripts name speakers by one rule (I-4), in every saved version.

B2 (round-3 stress, long60): refinement copied the first version's *default* names onto
the refined version: two speakers saved as "Speaker 4". Only names a person or a voiceprint
gave may carry over.
F4 (round-4 UI e2e, run a): defaults were then renumbered by first speech in the refined
version, so the voice shown as "Speaker 1" all meeting was saved as "Speaker 3". A default
name is read off the speaker's id, which clean-up keeps: same name in every version, a new
speaker takes the next unused number, a speaker that disappears leaves a gap.
B3: File/URL transcripts saved the decoder's raw `S01`/`S02`.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import (REFINEMENT_DONE_MARKER, REFINEMENT_RUNNING_MARKER,
                                             create_phase2_app)
from moss_transcribe_diarize.app.phase2_file import file_transcript_document
from moss_transcribe_diarize.app.phase2_live import _transcript_document

R = 16000


def _snapshot(speakers):
    """A live snapshot whose rows speak in the given order (None = unattributed)."""
    rows = tuple(SimpleNamespace(
        start_sample=i * R, end_sample=(i + 1) * R, canonical_speaker=speaker,
        text=f"words {i}",
        source_lane="microphone" if (speaker or "").startswith("local-") else "system")
        for i, speaker in enumerate(speakers))
    established = tuple(dict.fromkeys(s for s in speakers if s is not None))
    return SimpleNamespace(descriptor=SimpleNamespace(sample_rate=R), session=SimpleNamespace(
        identity_snapshot=SimpleNamespace(canonical_speakers=established),
        effective_transcript=rows))


def test_refined_version_keeps_every_live_name_and_numbers_only_new_speakers(tmp_path: Path):
    live_names = {"speaker-0001": "Blair"}  # a voiceprint named Blair while recording
    first = _transcript_document(_snapshot(
        ["speaker-0001", "speaker-0002", "speaker-0003", "speaker-0004", "local-0001"]),
        live_names)
    assert [s["speaker"] for s in first["segments"]] == [
        "Blair", "Speaker 2", "Speaker 3", "Speaker 4", "You"]
    for segment in first["segments"]:  # a person names speaker-0002 after Stop
        if segment.get("speaker_entity_id") == "speaker-0002":
            segment["speaker"] = "Alex"
    # Clean-up: speaker-0003 is gone, speaker-0005 is new, speaker-0004 now speaks first
    # (r4-ui-e2e run a: the live "Speaker 1" was re-saved as "Speaker 3"), and a second
    # microphone voice appears.
    refined = _transcript_document(_snapshot(
        ["speaker-0004", "speaker-0001", "speaker-0005", "speaker-0002", "local-0001",
         "local-0002", None, "speaker-0004"]), live_names)

    app = create_phase2_app(database_path=tmp_path / "db")
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")

        async def run():
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            handle = await store.workspace(account).create_meeting("live")
            await handle.finish_with_transcript(first, "completed",
                                                notice=REFINEMENT_RUNNING_MARKER)
            account_id = handle.owner_key[0]
            async with store._mutation():
                await store._connection.execute(
                    "INSERT INTO voiceprints(account_id, voiceprint_id, label, embedder_id, "
                    "embedding_dimension, revision, created_at_ms, updated_at_ms) "
                    "VALUES (?, 'vp-blair', 'Blair', 'test', 4, 1, 0, 0)", (account_id,))
                for speaker, label, voiceprint in (("speaker-0001", "Blair", "vp-blair"),
                                                   ("speaker-0002", "Alex", None)):
                    await store._connection.execute(
                        "INSERT INTO meeting_speakers(account_id, meeting_id, speaker_id, "
                        "label, voiceprint_id) VALUES (?, ?, ?, ?, ?)",
                        (account_id, handle.meeting_id, speaker, label, voiceprint))
            assert await handle.settle_refinement(refined) == 2
            return (await handle.snapshot()).transcript

        saved = client.portal.call(run)
    rows = [(s.get("speaker_entity_id"), s["speaker"]) for s in saved["segments"]]
    assert rows == [
        ("speaker-0004", "Speaker 4"),   # same name as live, although it now speaks first
        ("speaker-0001", "Blair"),       # voiceprint name kept
        ("speaker-0005", "Speaker 5"),   # new in clean-up: the next unused number
        ("speaker-0002", "Alex"),        # name given after Stop kept
        ("local-0001", "You"), ("local-0002", "User 1"),
        ("S00", "Speaker TBD"), ("speaker-0004", "Speaker 4")]  # no "Speaker 3": it is gone
    labels = {}
    for speaker, label in rows:
        if speaker != "S00":
            assert labels.setdefault(label, speaker) == speaker, f"{label} names two speakers"


def test_file_transcript_saves_default_names_and_keeps_the_decoder_token_as_identity():
    document = file_transcript_document(
        "[0][S02]first voice[1][1][S01]second voice[2][2][S00]nobody known[3][3][S02]again[4]")
    assert [(s.get("speaker_entity_id"), s["speaker"]) for s in document["segments"]] == [
        ("S02", "Speaker 2"), ("S01", "Speaker 1"), (None, "S00"), ("S02", "Speaker 2")]


def test_meeting_records_the_version_its_clean_up_produced_and_renames_keep_it(tmp_path: Path):
    """D1 (issue #15): a rename bumps the transcript version but is not a new clean-up
    result, so a summary made after the clean-up must not look stale."""
    first = _transcript_document(_snapshot(["speaker-0001", "speaker-0002"]), {})
    refined = _transcript_document(_snapshot(["speaker-0001", "speaker-0002", "speaker-0001"]), {})
    app = create_phase2_app(database_path=tmp_path / "db")
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")

        async def seed(notice):
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            handle = await store.workspace(account).create_meeting("live")
            await handle.finish_with_transcript(first, "completed", notice=notice)
            return handle

        handle = client.portal.call(seed, REFINEMENT_RUNNING_MARKER)
        path = f"/api/meetings/{handle.meeting_id}"
        assert "refined_version" not in client.get(path).json()
        assert client.portal.call(handle.settle_refinement, refined) == 2
        detail = client.get(path).json()
        assert (detail["refinement_state"], detail["refined_version"], detail["transcript_version"]) == ("done", 2, 2)
        assert "notice" not in detail and detail["needs_review"] is False
        named = client.put(f"{path}/speakers/speaker-0001/name",
                           json={"label": "Alex", "save_voiceprint": False})
        assert named.status_code == 200, named.text
        detail = client.get(path).json()
        assert (detail["refinement_state"], detail["refined_version"], detail["transcript_version"]) == ("done", 2, 3)
        listed = client.get("/api/meetings").json()["meetings"][0]
        assert (listed["refined_version"], listed["transcript_version"]) == (2, 3)

        # A clean-up saved before versions were recorded stays "done", version unknown.
        legacy = client.portal.call(seed, REFINEMENT_DONE_MARKER)
        detail = client.get(f"/api/meetings/{legacy.meeting_id}").json()
        assert detail["refinement_state"] == "done" and "refined_version" not in detail
        assert "notice" not in detail
