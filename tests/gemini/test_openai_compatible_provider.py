import hashlib
import inspect
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from moss_transcribe_diarize.app.gemini_final_policy import WebRtcWordGate
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiLiveRuntime
from moss_transcribe_diarize.app.openai_compatible_provider import (
    OpenAICompatibleDiarizer, OpenAICompatibleError, probe)
from tests._openai_fake import FakeTranscriptionServer

S = 16000
MODULE = "moss_transcribe_diarize.app.openai_compatible_provider"


def voice() -> bytes:
    with wave.open(str(Path(__file__).parents[1] / "fixtures/idea_020_provider_smoke.wav")) as wav:
        return wav.readframes(wav.getnframes())  # 2.1 s of real speech


def blocks(count: int) -> bytes:
    """One 2.1 s voice block every 3 s; refresh boundaries (15 s) fall in the gaps."""
    return (voice() + bytes(2 * round(.9 * S))) * count


def diarized(form, seconds):
    """Block b = speaker A/B alternating, relative to the request start."""
    del form
    rows = [{"type": "transcript.text.segment", "id": f"seg_{b}", "speaker": "AB"[b % 2],
             "start": 3.0 * b, "end": min(3.0 * b + 2.1, seconds), "text": f"b{b} one two"}
            for b in range(20) if 3.0 * b < seconds]
    return {"task": "transcribe", "duration": seconds, "text": " ".join(r["text"] for r in rows),
            "segments": rows, "usage": {"type": "duration", "seconds": round(seconds)}}


def verbose(form, seconds):
    del form
    segments, words = [], []
    for b in range(20):
        if 3.0 * b >= seconds:
            break
        start = 3.0 * b
        segments.append({"id": b, "start": start, "end": start + 2.1, "text": f" b{b} one two"})
        words += [{"word": f"b{b}", "start": start, "end": start + .6},
                  {"word": "one", "start": start + .7, "end": start + 1.4},
                  {"word": "two", "start": start + 1.5, "end": start + 2.1}]
    return {"task": "transcribe", "language": "english", "duration": seconds,
            "text": "".join(s["text"] for s in segments), "words": words, "segments": segments,
            "usage": {"type": "duration", "seconds": round(seconds)}}


def words_of(result):
    return [(w.text, w.speaker, w.start_sample, w.end_sample) for w in result.words]


def accepted_by_runtime(rows):
    signature = inspect.signature(GeminiLiveRuntime.record_engine_call)
    for row in rows:
        signature.bind(None, "session", **row)  # TypeError on an unknown usage field
    return True


def test_diarized_json_keeps_model_speakers_and_places_words_on_voice():
    with FakeTranscriptionServer(default=diarized) as server:
        usage = []
        adapter = OpenAICompatibleDiarizer(server.url, "gpt-4o-transcribe-diarize", "sk-test",
                                           lambda **row: usage.append(row))
        pcm = blocks(2)
        result = adapter.diarize(pcm, deadline=time.monotonic() + 10)
    form = server.requests[0]["form"]
    assert form["model"] == ["gpt-4o-transcribe-diarize"]
    assert form["response_format"] == ["diarized_json"]
    assert form["chunking_strategy"] == ["auto"]
    assert "timestamp_granularities[]" not in form
    assert form["_wav_format"] == ["(1, 2, 16000)"]
    assert [(w.text, w.speaker) for w in result.words] == [
        ("b0", "spk:A"), ("one", "spk:A"), ("two", "spk:A"),
        ("b1", "spk:B"), ("one", "spk:B"), ("two", "spk:B")]
    assert all(0 <= w.start_sample < w.end_sample <= round(2.1 * S) for w in result.words[:3])
    assert all(3 * S <= w.start_sample < w.end_sample <= round(5.1 * S) for w in result.words[3:])
    # Text-only timing lands on voiced frames, so the production word gate keeps every word.
    assert WebRtcWordGate().filter(pcm, result.words) == result.words
    assert usage == [{"kind": "rolling", "clamped_words": 0, "dropped_words": 0,
                      "audio_seconds_sent": 6.0, "cost_usd": 0.0}]


def test_verbose_json_keeps_word_times_with_one_label_per_segment():
    with FakeTranscriptionServer(default=verbose) as server:
        adapter = OpenAICompatibleDiarizer(server.url, "whisper-1", None, lambda **_row: None)
        result = adapter.diarize(blocks(2), deadline=time.monotonic() + 10, kind="terminal")
    form = server.requests[0]["form"]
    assert form["response_format"] == ["verbose_json"]
    assert form["timestamp_granularities[]"] == ["word", "segment"]
    assert "chunking_strategy" not in form
    assert words_of(result) == [
        ("b0", "seg:0", 0, round(.6 * S)), ("one", "seg:0", round(.7 * S), round(1.4 * S)),
        ("two", "seg:0", round(1.5 * S), round(2.1 * S)),
        ("b1", "seg:1", 3 * S, round(3.6 * S)), ("one", "seg:1", round(3.7 * S), round(4.4 * S)),
        ("two", "seg:1", round(4.5 * S), round(5.1 * S))]


def test_segments_without_words_are_spread_inside_their_segment():
    reply = {"text": "hello there general", "segments": [
        {"id": 0, "start": 0.0, "end": 2.1, "text": "hello there"},
        {"id": 1, "start": 3.0, "end": 5.1, "text": "general"}]}
    with FakeTranscriptionServer(default=reply) as server:
        result = OpenAICompatibleDiarizer(server.url, "whisper-large-v3", None,
                                          lambda **_row: None).diarize(
            blocks(2), deadline=time.monotonic() + 10)
    assert [(w.text, w.speaker) for w in result.words] == [
        ("hello", "seg:0"), ("there", "seg:0"), ("general", "seg:1")]
    assert result.words[1].end_sample <= round(2.1 * S) <= 3 * S <= result.words[2].start_sample


def test_format_refusal_falls_back_once_to_json_and_stays_there():
    refusal = (400, {"error": {"message": "response_format 'verbose_json' is not compatible with "
                                          "model 'gpt-4o-transcribe'. Use 'json' or 'text' instead.",
                               "type": "invalid_request_error", "param": "response_format"}})
    with FakeTranscriptionServer(replies=[refusal], default={"text": "only text here"}) as server:
        usage = []
        adapter = OpenAICompatibleDiarizer(server.url, "gpt-4o-transcribe", "k",
                                           lambda **row: usage.append(row))
        first = adapter.diarize(blocks(1), deadline=time.monotonic() + 10)
        adapter.diarize(blocks(1), deadline=time.monotonic() + 10)
    assert [r["form"]["response_format"] for r in server.requests] == [["verbose_json"], ["json"], ["json"]]
    assert [(w.text, w.speaker) for w in first.words] == [
        ("only", "seg:0"), ("text", "seg:0"), ("here", "seg:0")]
    assert all(w.end_sample <= round(2.3 * S) for w in first.words)  # voice, not the 0.9 s gap
    assert usage[0] == {"kind": "rolling", "error_code": "400", "retry_code": "response_format",
                        "audio_seconds_sent": 3.0}
    assert accepted_by_runtime(usage)


def test_bearer_header_is_sent_only_when_a_key_is_given():
    with FakeTranscriptionServer(default={"text": "hi"}) as server:
        OpenAICompatibleDiarizer(server.url, "m", "sk-secret", lambda **_r: None).diarize(
            blocks(1), deadline=time.monotonic() + 10)
        OpenAICompatibleDiarizer(server.url + "/", "m", "", lambda **_r: None).diarize(
            blocks(1), deadline=time.monotonic() + 10)
    assert [r["authorization"] for r in server.requests] == ["Bearer sk-secret", None]
    assert [r["path"] for r in server.requests] == ["/v1/audio/transcriptions"] * 2


def test_http_errors_map_to_counted_codes_and_only_transient_ones_retry(monkeypatch):
    monkeypatch.setattr(f"{MODULE}.time.sleep", lambda _seconds: None)
    usage = []
    with FakeTranscriptionServer(require_key="right") as server:
        adapter = OpenAICompatibleDiarizer(server.url, "m", "sk-wrong-key",
                                           lambda **row: usage.append(row))
        with pytest.raises(OpenAICompatibleError) as refused:
            adapter.diarize(blocks(1), deadline=time.monotonic() + 10)
    assert refused.value.code == "401" and len(server.requests) == 1
    assert "sk-wrong-key" not in str(refused.value) and "key" in str(refused.value)
    assert usage[-1] == {"kind": "rolling", "error_code": "401", "retry_code": None,
                         "audio_seconds_sent": 3.0}

    replies = [(500, {"error": {"message": "boom"}}), (503, "unavailable"), {"text": "ok"}]
    with FakeTranscriptionServer(replies=replies) as server:
        usage.clear()
        result = OpenAICompatibleDiarizer(server.url, "m", None, lambda **row: usage.append(row)
                                          ).diarize(blocks(1), deadline=time.monotonic() + 10,
                                                    kind="terminal")
    assert [w.text for w in result.words] == ["ok"] and len(server.requests) == 3
    assert [(r.get("error_code"), r.get("retry_code")) for r in usage] == [
        ("500", "500"), ("503", "503"), (None, None)]
    assert accepted_by_runtime(usage)

    for reply, code in (((400, {"error": {"message": "Invalid file format."}}), "400"),
                        ((404, {"error": {"message": "model not found"}}), "404"),
                        ("not json", "bad_response")):
        with FakeTranscriptionServer(replies=[(200, reply)] if code == "bad_response"
                                     else [reply]) as server:
            with pytest.raises(OpenAICompatibleError) as failed:
                OpenAICompatibleDiarizer(server.url, "whisper-1", None, lambda **_r: None
                                         ).diarize(blocks(1), deadline=time.monotonic() + 10)
        assert failed.value.code == code and len(server.requests) == 1


def test_slow_server_times_out_inside_the_caller_deadline():
    usage = []
    with FakeTranscriptionServer(default=("sleep", 3, {"text": "late"})) as server:
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            OpenAICompatibleDiarizer(server.url, "m", None, lambda **row: usage.append(row)
                                     ).diarize(blocks(1), deadline=time.monotonic() + .5)
        assert time.monotonic() - started < 2
    assert usage[0]["error_code"] == "timeout" and len(server.requests) == 1


def test_unreachable_server_is_a_connection_error_without_retry():
    usage = []
    with FakeTranscriptionServer() as server:
        url = server.url
    with pytest.raises(OpenAICompatibleError) as failed:
        OpenAICompatibleDiarizer(url, "m", None, lambda **row: usage.append(row)).diarize(
            blocks(1), deadline=time.monotonic() + 5)
    assert failed.value.code == "connection_error" and len(usage) == 1


def test_requests_above_the_upload_limit_split_into_prefixed_pieces(monkeypatch):
    monkeypatch.setattr(f"{MODULE}.MAX_REQUEST_SECONDS", 4)
    with FakeTranscriptionServer(default=diarized) as server:
        usage = []
        result = OpenAICompatibleDiarizer(server.url, "gpt-4o-transcribe-diarize", None,
                                          lambda **row: usage.append(row)).diarize(
            blocks(3), deadline=time.monotonic() + 10, kind="terminal")
    assert [r["seconds"] for r in server.requests] == [3.0, 3.0, 3.0]
    assert sum(row["audio_seconds_sent"] for row in usage) == 9.0
    assert [(w.text, w.speaker) for w in result.words][::3] == [
        ("b0", "p0:spk:A"), ("b0", "p1:spk:A"), ("b0", "p2:spk:A")]
    assert [w.start_sample // (3 * S) for w in result.words][::3] == [0, 1, 2]


def test_undiarized_call_collapses_labels():
    with FakeTranscriptionServer(default=diarized) as server:
        result = OpenAICompatibleDiarizer(server.url, "gpt-4o-transcribe-diarize", None,
                                          lambda **_r: None).diarize(
            blocks(2), deadline=time.monotonic() + 10, kind="preview", diarize=False)
    assert {w.speaker for w in result.words} == {"spk:?"}


def test_probe_reports_reachability_key_and_listed_model():
    with FakeTranscriptionServer(models=("whisper-1", "gpt-4o-transcribe-diarize"),
                                 require_key="k") as server:
        assert probe(server.url, "whisper-1", "k") is None
        assert "API key" in probe(server.url, "whisper-1", "bad")
        assert "not offered" in probe(server.url, "other-model", "k")
        assert "/v1" in probe(server.url.removesuffix("/v1"), "whisper-1", "k")
        url = server.url
    assert "reach" in probe(url, "whisper-1", "k", timeout=1)


# ---- end to end: production engines publish committed, speaker-attributed rows ----

def _descriptor():
    from moss_transcribe_diarize.app.live_service_runtime import (
        LiveServiceBounds, LiveServiceConfigHashes, LiveServiceDescriptor)
    return LiveServiceDescriptor(
        source_revision="test", provider_name="openai-compatible", provider_revision="fake",
        provider_manifest_hash=hashlib.sha256(b"openai").hexdigest(),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={}, identity_config={}, decoder_config={}),
        bounds=LiveServiceBounds(
            max_frame_samples=S, max_queue_depth=4, max_retained_samples=60 * S,
            max_identity_speakers=8, max_events=512, max_tape_bytes=50 * 2 * S),
        frame_samples=S)


def test_live_lane_engine_commits_model_speakers_through_the_runtime(tmp_path):
    from moss_transcribe_diarize.app.gemini_continuity_registry import ContinuityRegistry
    from moss_transcribe_diarize.app.gemini_hybrid_engine import (
        GeminiHybridEngine, GrowingContextWindowScheduler)
    from moss_transcribe_diarize.app.gemini_lane_engine import LaneGeminiEngine, WebRtcSpeechDetector
    from moss_transcribe_diarize.app.gemini_provider import TerminalTranscriber
    from moss_transcribe_diarize.app.live_session import AudioFrame
    from moss_transcribe_diarize.app.openai_compatible_provider import NoPreviewWords

    def engine_factory(_sid, publish, report_usage, _settings=None):
        def lane(name, seconds, registry):
            def report(**row):
                report_usage(**{**row, "kind": f"{name}_{row['kind']}"})
            adapter = OpenAICompatibleDiarizer(server.url, "gpt-4o-transcribe-diarize",
                                               "sk-live", report)
            return lambda lane_publish: GeminiHybridEngine(
                lane_publish, word_source=NoPreviewWords(),
                window_scheduler=GrowingContextWindowScheduler(max_seconds=seconds,
                                                               stride_seconds=15),
                registry=registry, diarizer=adapter,
                terminal=TerminalTranscriber(adapter, source_lane=name, report_usage=report),
                word_gate=WebRtcWordGate(), report_usage=report, source_lane=name,
                voiced_audio=WebRtcSpeechDetector())
        registry = lambda prefix: ContinuityRegistry(  # noqa: E731
            embedding_threshold=.46, within_window_threshold=.6, birth_min_seconds=2,
            id_prefix=prefix)
        return LaneGeminiEngine(publish, system_factory=lane("system", 90, registry("speaker")),
                                microphone_factory=lane("microphone", 30, registry("local")),
                                tape_root=tmp_path / "lanes")

    with FakeTranscriptionServer(default=diarized) as server:
        rt = GeminiLiveRuntime(descriptor=_descriptor(), engine_factory=engine_factory,
                               tape_storage_root=tmp_path / "tapes")
        rt.create(session_id="one")
        system = blocks(15)  # 45 s
        for second in range(45):
            pcm = system[second * 2 * S:(second + 1) * 2 * S]
            rt.accept_frame("one", AudioFrame(second, pcm, S, lane_pcm=(
                ("system", pcm), ("microphone", bytes(2 * S)))))
        until = time.monotonic() + 20
        while (rt.snapshot("one").session.canonical_through_sample < 45 * S
               and time.monotonic() < until):
            time.sleep(.02)
        rows = rt.snapshot("one").to_dict()["session"]["effective_transcript"]
        diagnostics = rt.engine_diagnostics("one")
        rt._sessions["one"].engine.close()
    assert [row["text"] for row in rows] == [f"b{b} one two" for b in range(15)]
    assert {row["source_lane"] for row in rows} == {"system"}
    speakers = [row["canonical_speaker"] for row in rows]
    assert speakers[0] is not None and speakers[1] is not None and speakers[0] != speakers[1]
    assert speakers == [speakers[b % 2] for b in range(15)]
    assert {r["authorization"] for r in server.requests} == {"Bearer sk-live"}
    assert {r["form"]["response_format"][0] for r in server.requests} == {"diarized_json"}
    assert diagnostics["calls_by_kind"].get("system_rolling", 0) >= 1
    assert "microphone_rolling" not in diagnostics["calls_by_kind"]  # silent mic: no request
    assert diagnostics["errors_by_code"] == {} and diagnostics["cost_usd"] == 0.0
    assert diagnostics["audio_seconds_sent"] >= 45.0


def test_file_runner_links_per_segment_labels_by_voice(tmp_path):
    from moss_transcribe_diarize.app.gemini_file_runner import GeminiFileRunner
    from moss_transcribe_diarize.subtitle import subtitle_segments_from_transcript

    class ParityEncoder:
        """Stand-in voiceprints: even 3 s blocks are one voice, odd blocks another."""
        spec = SimpleNamespace(provider="wespeaker", revision="pinned", state_sha256="ab" * 32)

        def embed_intervals(self, _path, intervals):
            return [(1.0, 0.0) if int(start // 3) % 2 == 0 else (0.0, 1.0)
                    for start, _end in intervals]

    audio = tmp_path / "meeting.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(S)
        wav.writeframes(blocks(4))
    with FakeTranscriptionServer(default=verbose) as server:
        usage = []
        runner = GeminiFileRunner(
            OpenAICompatibleDiarizer(server.url, "whisper-1", None, lambda **row: usage.append(row)),
            ParityEncoder())
        result = runner.transcribe(audio)
    rows = subtitle_segments_from_transcript(result.text, postprocess=False)
    assert [(row.speaker, row.text) for row in rows] == [
        ("S01", "b0 one two"), ("S02", "b1 one two"), ("S01", "b2 one two"), ("S02", "b3 one two")]
    assert len(server.requests) == 1 and usage[0]["kind"] == "terminal"
