import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from moss_transcribe_diarize.app.gemini_provider import WindowDiarizer, parse_words, TerminalTranscriber, GeminiWord, GeminiWords
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
    assert sum(row["output_cost_estimate_usd"] for row in usage) == pytest.approx(2 / 60 * .002)


@pytest.mark.parametrize("kind", ["rolling", "terminal"])
def test_batch_adapter_repairs_annotation_order_offsets_and_counts_them(kind):
    fake = FakeInteractions([response(word("before", "spk:0", 1, 1.2),
                                      word("wrong", "spk:0", 100, 101),
                                      word("after", "spk:0", 2, 2.2))])
    usage = []
    provider = WindowDiarizer(SimpleNamespace(interactions=fake), lambda **row: usage.append(row))
    result = provider.diarize(bytes(120*32000), deadline=time.monotonic()+5, kind=kind)
    assert [w.text for w in result.words] == ["before", "wrong", "after"]
    assert 1*16000 <= result.words[1].start_sample <= 2*16000
    assert result.words[1].end_sample <= 2*16000
    assert usage[0]["repaired_words"] == 1
    assert usage[0]["clamped_words"] == usage[0]["dropped_words"] == 0


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


def test_terminal_interval_sends_only_uncovered_tail_and_offsets_rows(tmp_path):
    seen = []
    class Diarizer:
        def diarize(self, pcm, *, deadline, kind, diarize=True):
            seen.append(len(pcm)//2)
            return GeminiWords((GeminiWord("tail", "spk:0", 16000, 32000),))
    tape = CompleteMixedTape(epoch=0, capacity_bytes=20*32000, storage_root=tmp_path)
    tape.append(start_sample=0, pcm=bytes(20*32000))
    terminal = TerminalTranscriber(Diarizer(), source_lane="system")
    rows = terminal.transcribe_interval(tape, 10*16000, 20*16000)
    assert seen == [10*16000]
    assert [(row.text, row.start_sample, row.end_sample, row.source_lane)
            for row in rows] == [("tail", 11*16000, 12*16000, "system")]
    assert [(row.start_sample, row.end_sample) for row in terminal.last_words] == [
        (11*16000, 12*16000)]
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


def test_terminal_keeps_gemini_annotation_order_for_small_backward_start(tmp_path):
    fake = FakeInteractions([response(word("one", "A", 0, 1),
                                      word("two", "B", 1.2, 1.3),
                                      word("three", "A", .9, 1.0))])
    provider = WindowDiarizer(SimpleNamespace(interactions=fake), lambda **_row: None)
    tape = CompleteMixedTape(epoch=0, capacity_bytes=2*32000, storage_root=tmp_path)
    tape.append(start_sample=0, pcm=bytes(2*32000))
    rows = TerminalTranscriber(provider).transcribe(tape)
    assert [row.text for row in rows] == ["one", "two", "three"]
    assert rows[0].speaker == rows[2].speaker != rows[1].speaker
    assert all(a.end_sample <= b.start_sample for a, b in zip(rows, rows[1:]))
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


def test_terminal_caps_calls_at_900_seconds_and_marks_chunked():
    class Tape:
        sample_count = 901*16000
        reads = []
        def read(self, *, start_sample, end_sample):
            self.reads.append((start_sample//16000, end_sample//16000))
            return bytes(2*(end_sample-start_sample))
    class Diarizer:
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            assert kind == "terminal"
            return GeminiWords(())
    usage = []
    tape = Tape()
    rows = TerminalTranscriber(Diarizer(), report_usage=lambda **row: usage.append(row)).transcribe(tape)
    assert rows == ()
    assert tape.reads[:2] == [(0, 900), (870, 901)]
    assert usage == [{"kind": "terminal", "count_call": False, "chunked": True}]


def test_terminal_skips_unvoiced_chunks_without_a_provider_call():
    class Tape:
        sample_count = 600*16000
        def read(self, *, start_sample=0, end_sample=None):
            return bytes(2*((self.sample_count if end_sample is None else end_sample)-start_sample))
    class Provider:
        def diarize(self, *_args, **_kwargs):
            raise AssertionError("digital silence must not reach Gemini")
    from moss_transcribe_diarize.app.gemini_lane_engine import WebRtcSpeechDetector
    terminal = TerminalTranscriber(Provider(), voiced_audio=WebRtcSpeechDetector())
    assert terminal.transcribe(Tape()) == ()
    assert terminal.last_words == ()


def test_terminal_voiced_gap_retries_and_exposes_live_fallback_interval():
    from moss_transcribe_diarize.app.gemini_live_runtime import GeminiSegment
    import wave
    from pathlib import Path
    from moss_transcribe_diarize.app.gemini_lane_engine import WebRtcSpeechDetector
    with wave.open(str(Path(__file__).parents[1] / "fixtures/idea_020_provider_smoke.wav"), "rb") as wav:
        voice = wav.readframes(16000)
    class Tape:
        sample_count = 20*16000
        def read(self, *, start_sample=0, end_sample=None):
            end = self.sample_count if end_sample is None else end_sample
            return voice * ((end-start_sample)//16000)
    class Diarizer:
        calls = 0
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            self.calls += 1
            return GeminiWords((GeminiWord("opening", "A", 0, 2*16000),))
    usage = []
    diarizer = Diarizer()
    terminal = TerminalTranscriber(diarizer, voiced_audio=WebRtcSpeechDetector(),
                                   report_usage=lambda **row: usage.append(row))
    terminal.set_witness((GeminiSegment(0, 20*16000, "live", "speaker-0001", "system"),))
    assert [row.text for row in terminal.transcribe(Tape())] == ["opening"]
    assert diarizer.calls == 2
    assert terminal.coverage_gaps == ((2*16000, 20*16000),)
    assert sum(row.get("coverage_retry", 0) for row in usage) == 1
    assert sum(row.get("terminal_coverage_fallbacks", 0) for row in usage) == 1


def test_terminal_audible_audio_without_live_words_has_no_coverage_retry():
    from moss_transcribe_diarize.app.gemini_lane_engine import WebRtcSpeechDetector
    import wave
    from pathlib import Path
    with wave.open(str(Path(__file__).parents[1] / "fixtures/idea_020_provider_smoke.wav"), "rb") as wav:
        audible = wav.readframes(16000)
    class Tape:
        sample_count = 15*16000
        def read(self, *, start_sample=0, end_sample=None):
            stop = self.sample_count if end_sample is None else end_sample
            return audible * ((stop-start_sample)//16000)
    class Empty:
        calls = 0
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            self.calls += 1
            return GeminiWords(())
    usage = []
    batch = Empty()
    terminal = TerminalTranscriber(batch, voiced_audio=WebRtcSpeechDetector(),
                                   report_usage=lambda **row: usage.append(row))
    assert terminal.transcribe(Tape()) == ()
    assert batch.calls == 1
    assert terminal.coverage_gaps == ()
    assert sum(row.get("coverage_retry", 0) for row in usage) == 0


def test_empty_terminal_response_retries_when_short_live_row_exists():
    from moss_transcribe_diarize.app.gemini_live_runtime import GeminiSegment
    class Tape:
        sample_count = 2*16000
        def read(self, *, start_sample=0, end_sample=None):
            stop = self.sample_count if end_sample is None else end_sample
            return bytes(2*(stop-start_sample))
    class Empty:
        calls = 0
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            self.calls += 1
            return GeminiWords(())
    batch = Empty()
    terminal = TerminalTranscriber(batch)
    terminal.set_witness((GeminiSegment(0, 2*16000, "live words", "speaker-0001"),))
    assert terminal.transcribe(Tape()) == ()
    assert batch.calls == 2
    assert terminal.coverage_gaps == ((0, 2*16000),)


def test_terminal_chunks_fetch_three_at_once_but_stitch_in_chunk_order():
    from moss_transcribe_diarize.app.gemini_lane_engine import SerializedDiarizer
    barrier = threading.Barrier(3, timeout=2)
    active = {"now": 0, "peak": 0}
    lock = threading.Lock()
    class Tape:
        sample_count = 10*16000
        def read(self, *, start_sample=0, end_sample=None):
            end = self.sample_count if end_sample is None else end_sample
            return bytes([start_sample//16000, 0]) + bytes(2*(end-start_sample)-2)
    class Provider:
        def diarize(self, pcm, *, deadline, kind, diarize=True):
            with lock:
                active["now"] += 1
                active["peak"] = max(active["peak"], active["now"])
            barrier.wait()
            with lock:
                active["now"] -= 1
            return GeminiWords((GeminiWord(f"part{pcm[0]}", "A", 0, 16000),))
    terminal = TerminalTranscriber(SerializedDiarizer(Provider()),
                                   chunk_seconds=4, overlap_seconds=1)
    rows = terminal.transcribe(Tape())
    assert active["peak"] == 3
    assert [row.text for row in rows] == ["part0", "part3", "part6"]


def test_terminal_rejects_explicit_call_cap_above_900_seconds():
    with pytest.raises(ValueError, match="900"):
        TerminalTranscriber(object(), chunk_seconds=901)


def test_terminal_midpoint_core_retains_later_chunk_word_at_seam(tmp_path):
    class Diarizer:
        calls = 0
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            self.calls += 1
            if self.calls == 1:
                return GeminiWords((GeminiWord("early", "A", 0, 16000),
                                    GeminiWord("old", "A", round(3.2*16000), round(3.4*16000))))
            return GeminiWords((GeminiWord("new", "B", round(.2*16000), round(.4*16000)),
                                GeminiWord("late", "B", round(1.2*16000), round(1.5*16000))))
    tape = CompleteMixedTape(epoch=0, capacity_bytes=5*32000, storage_root=tmp_path)
    tape.append(start_sample=0, pcm=bytes(5*32000))
    rows = TerminalTranscriber(Diarizer(), chunk_seconds=4, overlap_seconds=1).transcribe(tape)
    assert [row.text for row in rows] == ["early", "new late"]
    tape.release()


def test_chunked_terminal_uses_seam_stitch_before_word_gate(tmp_path):
    from moss_transcribe_diarize.app.gemini_long_final import LongFinalStitcher
    class Diarizer:
        calls = 0
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            self.calls += 1
            return GeminiWords((GeminiWord("before" if self.calls == 1 else "after",
                                           "A" if self.calls == 1 else "X", 0,
                                           4*16000 if self.calls == 1 else 2*16000),))
    class Encoder:
        def embed_intervals(self, path, intervals):
            return [(1.0, 0.0) if intervals[0][0] == 0 else (.8, .6)]
    class Identity:
        def remap(self, words, pcm):
            raise AssertionError("chunk identity is owned by the seam stitch")
    class Gate:
        def filter(self, pcm, words, **kwargs):
            assert len({w.speaker for w in words}) == 1
            return words
    tape = CompleteMixedTape(epoch=0, capacity_bytes=5*32000, storage_root=tmp_path)
    tape.append(start_sample=0, pcm=bytes(5*32000))
    rows = TerminalTranscriber(Diarizer(), chunk_seconds=4, overlap_seconds=1,
        identity_policy=Identity(), stitcher=LongFinalStitcher(Encoder()),
        word_gate=Gate()).transcribe(tape)
    assert [(row.text, row.speaker) for row in rows] == [("before after", "terminal-0001")]
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


def test_sdk_503_wire_attempts_match_adapter_error_and_retry_counters(monkeypatch):
    from moss_transcribe_diarize.app.phase2_web_cli import _gemini_client
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = b'{"error":{"code":503,"message":"injected"}}'
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr("moss_transcribe_diarize.app.gemini_provider.time.sleep", lambda _s: None)
    client = _gemini_client("local-test")
    usage = []
    try:
        provider = WindowDiarizer(client, lambda **row: usage.append(row), max_attempts=2)
        with pytest.raises(Exception):
            provider.diarize(bytes(32000), deadline=time.monotonic()+5)
        assert len(seen) == 2
        assert [row["error_code"] for row in usage] == ["503", "503"]
        assert [row["retry_code"] for row in usage] == ["503", None]
    finally:
        client.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


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
