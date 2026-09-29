from moss_transcribe_diarize.live_surface import published_speaker_label


def test_local_default_label_uses_local_namespace_number_without_changing_system_label():
    speakers = ("speaker-0001", "local-0002", "local-0001", "speaker-0002")
    assert published_speaker_label("local-0001", speakers) == "Local 01"
    assert published_speaker_label("local-0002", speakers) == "Local 02"
    assert published_speaker_label("speaker-0001", speakers) == "S01"
    assert published_speaker_label("speaker-0002", speakers) == "S04"
    assert published_speaker_label("local-0003", speakers) == "S00"
