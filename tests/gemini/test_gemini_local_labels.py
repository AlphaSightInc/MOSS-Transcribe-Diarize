from types import SimpleNamespace

from moss_transcribe_diarize.app.phase2_live import _transcript_document
from moss_transcribe_diarize.live_surface import default_speaker_name, published_speaker_label


def test_default_name_is_read_off_the_speaker_id_alone():
    assert default_speaker_name("local-0001") == "You"
    assert default_speaker_name("local-0002") == "User 1"
    assert default_speaker_name("speaker-0001") == "Speaker 1"
    assert default_speaker_name("speaker-0012") == "Speaker 12"
    assert default_speaker_name("S02") == "Speaker 2"  # a File decoder's token
    assert default_speaker_name("S00") == "S00"
    assert default_speaker_name("manual-AbC") == "S00"  # a person-made id is always named
    assert default_speaker_name(None) == "S00"


def test_scored_label_stays_the_positional_span_token():
    speakers = ("speaker-0001", "local-0002", "local-0001", "speaker-0002")
    assert [published_speaker_label(s, speakers) for s in speakers] == ["S01", "S02", "S03", "S04"]
    assert published_speaker_label("local-0003", speakers) == "S00"


def test_saved_transcript_names_do_not_depend_on_speech_order_or_on_other_names():
    def row(start, speaker, lane):
        return SimpleNamespace(start_sample=start * 16000, end_sample=(start + 1) * 16000,
                               canonical_speaker=speaker, text=f"words {start}",
                               source_lane=lane)
    # speaker-0003 speaks before speaker-0002; speaker-0004 was established but has no rows
    # left; speaker-0009 was never established.
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
                row(6, "speaker-0009", "system"), row(7, "speaker-0003", "system"))))

    def names(given):
        return [segment["speaker"] for segment in _transcript_document(snapshot, given)["segments"]]

    assert names({}) == ["Speaker 1", "Speaker 3", "User 1", "Speaker 2", "You", "S00", "S00",
                         "Speaker 3"]
    # Naming one speaker renames nobody else (F4: renames never renumber the others).
    assert names({"speaker-0001": "Alex"}) == ["Alex", "Speaker 3", "User 1", "Speaker 2", "You",
                                               "S00", "S00", "Speaker 3"]
