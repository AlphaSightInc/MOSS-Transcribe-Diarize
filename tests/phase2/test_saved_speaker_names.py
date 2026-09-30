"""Saved transcripts name speakers by one rule (I-4), in every saved version.

B2 (round-3 stress, long60): refinement copied the first version's *default* names onto
the refined version, so a speaker first numbered "Speaker 4" kept it while a speaker new in
the refined version was also numbered "Speaker 4" (collision), and absorbed speakers left
gaps. Only names a person or a voiceprint gave may carry over.
B3: File/URL transcripts saved the decoder's raw `S01`/`S02`.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import REFINEMENT_RUNNING_MARKER, create_phase2_app
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


def test_refined_version_keeps_given_names_and_renumbers_every_default(tmp_path: Path):
    live_names = {"speaker-0001": "Blair"}  # a voiceprint named Blair while recording
    first = _transcript_document(_snapshot(
        ["speaker-0001", "speaker-0003", "speaker-0004", "speaker-0002", "local-0001"]),
        live_names)
    assert [s["speaker"] for s in first["segments"]] == [
        "Blair", "Speaker 1", "Speaker 2", "Speaker 3", "You"]
    for segment in first["segments"]:  # a person names speaker-0002 after Stop
        if segment.get("speaker_entity_id") == "speaker-0002":
            segment["speaker"] = "Alex"
    # Refinement: speaker-0003 is gone, speaker-0005 is new, speaker-0004 now speaks first,
    # and a second microphone voice appears.
    refined = _transcript_document(_snapshot(
        ["speaker-0001", "speaker-0004", "speaker-0005", "speaker-0002", "local-0001",
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
        ("speaker-0001", "Blair"), ("speaker-0004", "Speaker 1"), ("speaker-0005", "Speaker 2"),
        ("speaker-0002", "Alex"), ("local-0001", "You"), ("local-0002", "User 1"),
        ("S00", "Speaker TBD"), ("speaker-0004", "Speaker 1")]
    labels = {}
    for speaker, label in rows:
        if speaker != "S00":
            assert labels.setdefault(label, speaker) == speaker, f"{label} names two speakers"


def test_file_transcript_saves_default_names_and_keeps_the_decoder_token_as_identity():
    document = file_transcript_document(
        "[0][S02]first voice[1][1][S01]second voice[2][2][S00]nobody known[3][3][S02]again[4]")
    assert [(s.get("speaker_entity_id"), s["speaker"]) for s in document["segments"]] == [
        ("S02", "Speaker 1"), ("S01", "Speaker 2"), (None, "S00"), ("S02", "Speaker 1")]
