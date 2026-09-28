from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    EffectiveTranscriptSegment,
    LiveSession,
    TextRevisionProposal,
)


def test_gemini_relabels_an_owned_rolling_interval_without_changing_words():
    session = LiveSession(max_retained_samples=16000)
    session.accept_frame(AudioFrame(sequence=0, pcm=b"\0" * 32000, sample_count=16000))
    span = session.freeze_until(16000, reason="gemini")
    assert session.submit_empty_canonical(
        span_id=span.id, epoch=span.epoch, start_sample=0, end_sample=16000
    ).submitted
    session.register_canonical_speakers(("speaker-0001", "speaker-0002"))
    first = EffectiveTranscriptSegment(0, 8000, "hello world", "speaker-0001", "rolling")
    assert session.apply_text_revision(TextRevisionProposal(
        epoch=session.epoch, base_text_revision_version=0, source="rolling",
        start_sample=0, end_sample=16000, segments=(first,),
    )).applied

    assert session.revise_rolling_interval(
        start_sample=0, end_sample=8000, base_text_revision_version=1,
        segments=(
            EffectiveTranscriptSegment(0, 4000, "hello ", "speaker-0001", "rolling"),
            EffectiveTranscriptSegment(4000, 8000, "world", "speaker-0002", "rolling"),
        ),
    ).applied
    snapshot = session.snapshot()
    assert [row.canonical_speaker for row in snapshot.effective_transcript] == [
        "speaker-0001", "speaker-0002"
    ]
    assert "".join(row.text for row in snapshot.effective_transcript) == "hello world"
    assert snapshot.label_revision_version == 1
    assert not session.revise_rolling_interval(
        start_sample=0, end_sample=8000, base_text_revision_version=2,
        segments=(EffectiveTranscriptSegment(0, 8000, "different", "speaker-0002", "rolling"),),
    ).applied
