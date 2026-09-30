from types import SimpleNamespace

from moss_transcribe_diarize.app.phase2_live import _transcript_document
from moss_transcribe_diarize.live_surface import default_speaker_name, published_speaker_label


def test_default_names_are_you_then_users_on_the_microphone_and_numbered_speakers_elsewhere():
    first_spoken = ("speaker-0001", "local-0002", "local-0001", "speaker-0002")
    assert default_speaker_name("local-0001", first_spoken) == "You"
    assert default_speaker_name("local-0002", first_spoken) == "User 1"
    assert default_speaker_name("speaker-0001", first_spoken) == "Speaker 1"
    assert default_speaker_name("speaker-0002", first_spoken) == "Speaker 2"
    assert default_speaker_name("local-0003", first_spoken) == "S00"
    assert default_speaker_name(None, first_spoken) == "S00"


def test_scored_label_stays_the_positional_span_token():
    speakers = ("speaker-0001", "local-0002", "local-0001", "speaker-0002")
    assert [published_speaker_label(s, speakers) for s in speakers] == ["S01", "S02", "S03", "S04"]
    assert published_speaker_label("local-0003", speakers) == "S00"


def test_saved_transcript_numbers_unnamed_speakers_in_order_of_first_speech():
    def row(start, speaker, lane):
        return SimpleNamespace(start_sample=start * 16000, end_sample=(start + 1) * 16000,
                               canonical_speaker=speaker, text=f"words {start}",
                               source_lane=lane)
    # speaker-0001 was established first but is named; speaker-0003 speaks before -0002;
    # speaker-0004 was established but absorbed (no rows) -- numbering has no gaps.
    snapshot = SimpleNamespace(
        descriptor=SimpleNamespace(sample_rate=16000),
        session=SimpleNamespace(
            identity_snapshot=SimpleNamespace(canonical_speakers=(
                "speaker-0001", "speaker-0004", "speaker-0002", "local-0001", "speaker-0003",
                "local-0002")),
            effective_transcript=(
                row(0, "speaker-0001", "system"), row(1, "speaker-0003", "system"),
                row(2, "local-0002", "microphone"), row(3, "speaker-0002", "system"),
                row(4, "local-0001", "microphone"), row(5, None, "system"),
                row(6, "speaker-0003", "system"))))
    document = _transcript_document(snapshot, {"speaker-0001": "Alex"})
    assert [segment["speaker"] for segment in document["segments"]] == [
        "Alex", "Speaker 1", "User 1", "Speaker 2", "You", "S00", "Speaker 1"]
