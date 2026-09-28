import time
from types import SimpleNamespace

import pytest

from moss_transcribe_diarize.app.gemini_provider import WindowDiarizer, parse_words, TerminalTranscriber
from moss_transcribe_diarize.app.live_tape import CompleteMixedTape


def response(*annotations):
    return {"steps": [{"content": [{"annotations": list(annotations)}]}],
            "usage": {"input_tokens_by_modality": [{"modality": "audio", "tokens": 100}],
                      "total_output_tokens": 10}}


def word(text, speaker, start, end):
    return {"type": "word_info", "text": text, "speaker": speaker,
            "start_offset": f"{start}s", "end_offset": f"{end}s"}


class FakeResponse:
    def __init__(self, payload): self.payload = payload
    def model_dump(self, **_kwargs): return self.payload


class FakeInteractions:
    def __init__(self, replies): self.replies = list(replies); self.requests = []
    def create(self, **kwargs):
        self.requests.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception): raise reply
        return FakeResponse(reply)


def test_window_request_repairs_invalid_offsets_and_reports_every_attempt():
    fake = FakeInteractions([RuntimeError("429"), response(
        word("hi", "spk:0", 0.2, 55935), word("late", "spk:0", 4, 5))])
    usage = []
    provider = WindowDiarizer(SimpleNamespace(interactions=fake), lambda **row: usage.append(row))
    result = provider.diarize(bytes(2 * 16000), deadline=time.monotonic() + 10)
    assert len(fake.requests) == 2
    assert fake.requests[0]["generation_config"]["transcription_config"]["mode"] == {
        "type": "verbatim", "timestamp_granularities": ["word"], "diarization_mode": "speaker"}
    assert result.clamped == result.dropped == 1
    assert len(result.words) == 1 and result.words[0].end_sample == 16000
    assert usage[0]["error_code"] == usage[0]["retry_code"] == "429"
    assert usage[1]["clamped_words"] == usage[1]["dropped_words"] == 1
    assert sum(row["audio_seconds_sent"] for row in usage) == 2
    assert usage[1]["cost_usd"] == pytest.approx(0.00032)


def test_terminal_overlap_maps_local_labels_and_keeps_one_owner(tmp_path):
    fake = FakeInteractions([response(word("a", "spk:0", 0, 1), word("b", "spk:0", 3, 4)),
                             response(word("b", "spk:9", 0, 1), word("c", "spk:9", 2, 3))])
    provider = WindowDiarizer(SimpleNamespace(interactions=fake), lambda **_row: None)
    tape = CompleteMixedTape(epoch=0, capacity_bytes=7*32000, storage_root=tmp_path)
    tape.append(start_sample=0, pcm=bytes(7*32000))
    rows = TerminalTranscriber(provider, chunk_seconds=4, overlap_seconds=1).transcribe(tape)
    assert [row.text for row in rows] == ["a", "b c"]
    assert len({row.speaker for row in rows}) == 1
    assert [row.start_sample for row in rows] == [0, 48000]
    tape.release()


def test_terminal_publishes_speaker_turns_with_1_5_second_gap_limit(tmp_path):
    fake = FakeInteractions([response(
        word("a", "spk:0", 0, 1), word("b", "spk:0", 1.4, 2),
        word("c", "spk:0", 2.5, 3), word("d", "spk:1", 3.1, 4),
        word("e", "spk:1", 5.8, 6),
    )])
    provider = WindowDiarizer(SimpleNamespace(interactions=fake), lambda **_row: None)
    tape = CompleteMixedTape(epoch=0, capacity_bytes=7*32000, storage_root=tmp_path)
    tape.append(start_sample=0, pcm=bytes(7*32000))
    rows = TerminalTranscriber(provider).transcribe(tape)
    assert [(row.text, row.start_sample, row.end_sample) for row in rows] == [
        ("a b c", 0, 3*16000), ("d", 49600, 4*16000),
        ("e", 92800, 6*16000),
    ]
    assert rows[0].speaker != rows[1].speaker == rows[2].speaker
    tape.release()


def test_microphone_terminal_transcribes_without_diarization_and_filters_words(tmp_path):
    fake = FakeInteractions([response(word("echo", "spk:?", 0, 1),
                                      word("local", "spk:?", 1, 2))])
    provider = WindowDiarizer(SimpleNamespace(interactions=fake), lambda **_row: None)
    tape = CompleteMixedTape(epoch=0, capacity_bytes=2*32000, storage_root=tmp_path)
    tape.append(start_sample=0, pcm=bytes(2*32000))
    terminal = TerminalTranscriber(provider, diarize=False,
        word_filter=lambda words: tuple(w for w in words if w.text == "local"),
        source_lane="microphone", fixed_speaker="speaker-microphone")
    rows = terminal.transcribe(tape)
    assert fake.requests[0]["generation_config"]["transcription_config"]["mode"] == {
        "type": "verbatim", "timestamp_granularities": ["word"]}
    assert [(r.text, r.speaker, r.source_lane) for r in rows] == [
        ("local", "speaker-microphone", "microphone")]
    tape.release()


def test_unordered_overlapping_annotations_keep_all_words_on_one_sample_line():
    from moss_transcribe_diarize.app.gemini_live_runtime import GeminiSegment
    from moss_transcribe_diarize.app.gemini_provider import ordered_segments
    rows = ordered_segments((GeminiSegment(6, 9, "later", "S1"),
                             GeminiSegment(0, 7, "early", "S2"),
                             GeminiSegment(6, 8, "overlap", "S2")),
                            start_sample=0, end_sample=10)
    assert [(row.start_sample, row.end_sample, row.text) for row in rows] == [
        (0, 7, "early"), (7, 8, "overlap"), (8, 9, "later")]


def test_all_5xx_retry_but_4xx_other_than_429_do_not(monkeypatch):
    monkeypatch.setattr("moss_transcribe_diarize.app.gemini_provider.time.sleep", lambda _seconds: None)
    retried = FakeInteractions([RuntimeError("501"), response(word("ok", "spk:0", 0, 1))])
    usage = []
    provider = WindowDiarizer(SimpleNamespace(interactions=retried), lambda **row: usage.append(row))
    assert len(provider.diarize(bytes(32000), deadline=time.monotonic()+5).words) == 1
    assert usage[0]["retry_code"] == "501"
    refused = FakeInteractions([RuntimeError("400"), response(word("wrong", "spk:0", 0, 1))])
    provider = WindowDiarizer(SimpleNamespace(interactions=refused), lambda **row: usage.append(row))
    with pytest.raises(RuntimeError, match="400"):
        provider.diarize(bytes(32000), deadline=time.monotonic()+5)
    assert len(refused.requests) == 1 and usage[-1]["retry_code"] is None


def test_terminal_applies_selected_identity_and_word_gate_before_turns(tmp_path):
    fake = FakeInteractions([response(word("a", "spk:0", 0, 1),
                                      word("silent", "spk:1", 2, 3))])
    provider = WindowDiarizer(SimpleNamespace(interactions=fake), lambda **_row: None)
    tape = CompleteMixedTape(epoch=0, capacity_bytes=4*32000, storage_root=tmp_path)
    tape.append(start_sample=0, pcm=bytes(4*32000))
    seen = []
    class Policy:
        def remap(self, words, pcm):
            seen.append(("identity", len(pcm)))
            return tuple(type(w)(w.text, "one", w.start_sample, w.end_sample) for w in words)
    class Gate:
        def filter(self, pcm, words, **kwargs):
            seen.append(("gate", len(words)))
            return tuple(w for w in words if w.text != "silent")
    rows = TerminalTranscriber(provider, identity_policy=Policy(), word_gate=Gate()).transcribe(tape)
    assert seen == [("identity", 4*32000), ("gate", 2)]
    assert [(r.text, r.speaker) for r in rows] == [("a", "one")]
    assert len(fake.requests) == 1
    tape.release()
