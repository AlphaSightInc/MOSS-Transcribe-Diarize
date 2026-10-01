import asyncio
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace
import pytest

from moss_transcribe_diarize.app.gemini_live_words import GeminiLiveWordSource


def test_system_voiced_live_words_skip_silence_then_open_and_reopen_promptly():
    from moss_transcribe_diarize.app.gemini_lane_engine import VoicedLiveWords, WebRtcSpeechDetector
    live = FakeLive()
    usage = []
    visible = threading.Event()
    events = []
    source = VoicedLiveWords(
        lambda: GeminiLiveWordSource(SimpleNamespace(aio=SimpleNamespace(live=live)),
                                     lambda **row: usage.append(row)),
        voiced_audio=WebRtcSpeechDetector())
    source.bind(lambda text, start, end, final:
                (events.append((text, start, end, time.monotonic())), visible.set()))
    for second in range(600):
        source.push_audio(second*16000, bytes(32000))
    assert not live.sessions and not usage
    with wave.open(str(Path(__file__).parents[1] / "fixtures/idea_020_provider_smoke.wav"), "rb") as wav:
        voice = wav.readframes(16000)
    opened = time.monotonic()
    source.push_audio(600*16000, voice)
    assert visible.wait(2)
    assert events[-1][:3] == ("hello", 600*16000, 601*16000)
    assert events[-1][3] - opened < 1.0
    assert len(live.sessions) == 1
    visible.clear()
    for second in range(601, 671):
        source.push_audio(second*16000, bytes(32000))
    assert source._active is None
    reopened = time.monotonic()
    source.push_audio(671*16000, voice)
    assert visible.wait(2)
    assert events[-1][:3] == ("hello", 671*16000, 672*16000)
    assert events[-1][3] - reopened < 1.0
    assert len(live.sessions) == 2
    asyncio.run(source.finish())


class FakeSession:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.audio_bytes = []
        self.stream_ends = 0

    async def receive(self):
        while True:
            message = await self.incoming.get()
            if message is None:
                return
            yield message

    async def send_realtime_input(self, *, audio=None, audio_stream_end=False):
        if audio is not None:
            self.audio_bytes.append(len(audio.data))
            if len(self.audio_bytes) == 1:
                await self.incoming.put(SimpleNamespace(
                    go_away=None, session_resumption_update=None, usage_metadata=None,
                    server_content=SimpleNamespace(
                        interim_input_transcription=SimpleNamespace(text="hello", finished=False),
                        input_transcription=None, model_turn=None)))
        if audio_stream_end:
            self.stream_ends += 1


class FakeContext:
    def __init__(self, session): self.session = session
    async def __aenter__(self): return self.session
    async def __aexit__(self, *_args):
        await self.session.incoming.put(None)


class FakeLive:
    def __init__(self):
        self.sessions = []
        self.configs = []
    def connect(self, *, model, config):
        assert model == "gemini-3.5-transcribe-live"
        self.configs.append(config)
        session = FakeSession()
        self.sessions.append(session)
        return FakeContext(session)


def test_goaway_reopens_with_handle_and_replays_five_second_buffer():
    class GoAwaySession(FakeSession):
        async def send_realtime_input(self, *, audio=None, audio_stream_end=False):
            await super().send_realtime_input(audio=audio, audio_stream_end=audio_stream_end)
            if audio is not None and len(self.audio_bytes) == 1:
                await self.incoming.put(SimpleNamespace(
                    go_away=SimpleNamespace(time_left="30s"),
                    session_resumption_update=SimpleNamespace(resumable=True, new_handle="handle-1"),
                    usage_metadata=None, server_content=None))
    class RotatingLive(FakeLive):
        def connect(self, *, model, config):
            assert model == "gemini-3.5-transcribe-live"
            self.configs.append(config)
            session = GoAwaySession() if not self.sessions else FakeSession()
            self.sessions.append(session)
            return FakeContext(session)
    live = RotatingLive()
    usage = []
    rotated = threading.Event()
    def report(**row):
        usage.append(row)
        if row.get("retry_code") == "go_away":
            rotated.set()
    source = GeminiLiveWordSource(SimpleNamespace(aio=SimpleNamespace(live=live)), report)
    source.bind(lambda *_args: None)
    source.push_audio(0, bytes(16000))
    assert rotated.wait(2)
    source.push_audio(8000, bytes(16000))
    until = time.monotonic() + 2
    while len(live.sessions) < 2 and time.monotonic() < until:
        time.sleep(0.01)
    asyncio.run(source.finish())
    assert len(live.sessions) == 2
    assert live.configs[1].session_resumption.handle == "handle-1"
    assert live.sessions[0].audio_bytes == [16000]
    assert live.sessions[1].audio_bytes[:2] == [16000, 16000]
    assert sum(row.get("audio_seconds_sent", 0) for row in usage) == 3.5


def test_voiced_preview_stall_restarts_socket_and_counts_it():
    class SilentSession(FakeSession):
        async def send_realtime_input(self, *, audio=None, audio_stream_end=False):
            if audio is not None:
                self.audio_bytes.append(len(audio.data))
            if audio_stream_end:
                self.stream_ends += 1
    class SilentLive(FakeLive):
        def connect(self, *, model, config):
            self.configs.append(config)
            session = SilentSession()
            self.sessions.append(session)
            return FakeContext(session)
    live = SilentLive()
    usage = []
    source = GeminiLiveWordSource(SimpleNamespace(aio=SimpleNamespace(live=live)),
                                  lambda **row: usage.append(row))
    source.bind(lambda *_args: None)
    with wave.open(str(Path(__file__).parents[1] / "fixtures/idea_020_provider_smoke.wav"), "rb") as wav:
        voice = wav.readframes(16000)
    for second in range(10):
        source.push_audio(second * 16000, voice)
    source.observe_batch_words(())  # Audible music with no batch words is no stall witness.
    source._tail.result(timeout=5)
    assert len(live.sessions) == 1
    source.observe_batch_words(tuple((second*16000, (second+1)*16000)
                                    for second in range(10)))
    source._tail.result(timeout=5)
    assert len(live.sessions) == 2
    assert sum(row.get("preview_stall_restarts", 0) for row in usage) == 1
    asyncio.run(source.finish())


def test_regular_interim_text_prevents_voiced_preview_stall_restart():
    class TalkingSession(FakeSession):
        async def send_realtime_input(self, *, audio=None, audio_stream_end=False):
            if audio is not None:
                self.audio_bytes.append(len(audio.data))
                await self.incoming.put(SimpleNamespace(
                    go_away=None, session_resumption_update=None,
                    server_content=SimpleNamespace(
                        interim_input_transcription=SimpleNamespace(text="hello", finished=False),
                        input_transcription=None, model_turn=None)))
    class TalkingLive(FakeLive):
        def connect(self, *, model, config):
            self.configs.append(config)
            session = TalkingSession()
            self.sessions.append(session)
            return FakeContext(session)
    live = TalkingLive()
    usage = []
    source = GeminiLiveWordSource(SimpleNamespace(aio=SimpleNamespace(live=live)),
                                  lambda **row: usage.append(row))
    source.bind(lambda *_args: None)
    with wave.open(str(Path(__file__).parents[1] / "fixtures/idea_020_provider_smoke.wav"), "rb") as wav:
        voice = wav.readframes(16000)
    for second in range(10):
        source.push_audio(second * 16000, voice)
    source.observe_batch_words(tuple((second*16000, (second+1)*16000)
                                    for second in range(10)))
    source._tail.result(timeout=5)
    assert len(live.sessions) == 1
    assert sum(row.get("preview_stall_restarts", 0) for row in usage) == 0
    asyncio.run(source.finish())


def test_live_words_publish_interim_and_count_list_price_audio():
    live = FakeLive()
    usage = []
    updates = []
    visible = threading.Event()
    source = GeminiLiveWordSource(SimpleNamespace(aio=SimpleNamespace(live=live)),
                                  lambda **row: usage.append(row))
    def on_text(text, start, end, final):
        updates.append((text, start, end, final))
        visible.set()
    source.bind(on_text)
    source.push_audio(0, bytes(16000))
    assert visible.wait(2)
    assert updates == [("hello", 0, 8000, False)]
    asyncio.run(source.finish())
    assert live.configs[0].response_modalities == ["TEXT"]
    assert live.configs[0].realtime_input_config.automatic_activity_detection.silence_duration_ms == 500
    assert live.sessions[0].audio_bytes == [16000, 64000]  # 0.5 s source + 2 s tail silence.
    assert live.sessions[0].stream_ends == 1
    sent = sum(row.get("audio_seconds_sent", 0) for row in usage)
    estimate = sum(row.get("cost_usd", 0) for row in usage)
    output_estimate = sum(row.get("output_cost_estimate_usd", 0) for row in usage)
    assert sent == 2.5
    assert abs(estimate - 2.5 * 0.005 / 60) < 1e-10
    assert all("cost_basis" not in row or row["cost_basis"] == "list_price_estimate" for row in usage)
    assert output_estimate == pytest.approx(sent / 60 * .004)


def test_slow_live_socket_bounds_preview_backlog_without_blocking_capture():
    class SlowSession(FakeSession):
        async def send_realtime_input(self, *, audio=None, audio_stream_end=False):
            if audio is not None:
                await asyncio.sleep(1)
            await super().send_realtime_input(audio=audio, audio_stream_end=audio_stream_end)
    class SlowLive(FakeLive):
        def connect(self, *, model, config):
            self.configs.append(config)
            session = SlowSession()
            self.sessions.append(session)
            return FakeContext(session)
    usage = []
    live = SlowLive()
    source = GeminiLiveWordSource(SimpleNamespace(aio=SimpleNamespace(live=live)),
                                  lambda **row: usage.append(row))
    source.bind(lambda *_args: None)
    started = time.monotonic()
    for sequence in range(70):
        source.push_audio(sequence*160, bytes(320))
    assert time.monotonic() - started < 0.5
    assert any(row.get("error_code") == "preview_backpressure" for row in usage)
    source.close()
    source._thread.join(2)
    assert not source._thread.is_alive()


def test_preview_backlog_sheds_chunks_and_resumes_once_the_socket_drains():
    """R4 #1: a capture replaying 60-110 s of queued audio while the socket reconnects
    overflowed the 64-chunk backlog; closing the source then kept preview off for the rest
    of a meeting in which people kept talking."""
    gate = threading.Event()

    class GatedSession(FakeSession):
        async def send_realtime_input(self, *, audio=None, audio_stream_end=False):
            while audio is not None and not gate.is_set():
                await asyncio.sleep(0.01)
            await super().send_realtime_input(audio=audio, audio_stream_end=audio_stream_end)

    class GatedLive(FakeLive):
        def connect(self, *, model, config):
            session = GatedSession()
            self.sessions.append(session)
            return FakeContext(session)

    usage = []
    live = GatedLive()
    source = GeminiLiveWordSource(SimpleNamespace(aio=SimpleNamespace(live=live)),
                                  lambda **row: usage.append(row))
    source.bind(lambda *_args: None)
    for sequence in range(70):
        source.push_audio(sequence * 160, bytes(320))
    assert sum(row.get("error_code") == "preview_backpressure" for row in usage) == 6
    gate.set()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and (not live.sessions or len(live.sessions[0].audio_bytes) < 64):
        time.sleep(0.01)
    source.push_audio(70 * 160, bytes(320))
    while time.monotonic() < deadline and (not live.sessions or len(live.sessions[0].audio_bytes) < 65):
        time.sleep(0.01)
    assert len(live.sessions[0].audio_bytes) == 65  # The live chunk after the backlog is sent.
    assert len(live.sessions) == 1
    source.close()
    source._thread.join(2)
    assert not source._thread.is_alive()


def test_failed_live_preview_connection_does_not_block_terminal_path():
    class FailingLive:
        def __init__(self): self.attempts = 0
        def connect(self, *, model, config):
            self.attempts += 1
            raise RuntimeError("503 provider unavailable")
    live = FailingLive()
    usage = []
    source = GeminiLiveWordSource(SimpleNamespace(aio=SimpleNamespace(live=live)),
                                  lambda **row: usage.append(row))
    source.bind(lambda *_args: None)
    source.push_audio(0, bytes(16000))
    asyncio.run(source.finish())
    assert live.attempts == 3
    assert [row.get("error_code") for row in usage] == ["503", "503", "503"]
    assert [row.get("retry_code") for row in usage] == ["503", "503", None]


def test_model_turn_text_is_preview_fallback():
    class ModelTurnSession(FakeSession):
        async def send_realtime_input(self, *, audio=None, audio_stream_end=False):
            if audio is not None:
                self.audio_bytes.append(len(audio.data))
            if audio_stream_end:
                self.stream_ends += 1
            if audio is not None and len(self.audio_bytes) == 1:
                await self.incoming.put(SimpleNamespace(
                    go_away=None, session_resumption_update=None,
                    server_content=SimpleNamespace(
                        interim_input_transcription=None, input_transcription=None,
                        model_turn=SimpleNamespace(parts=[SimpleNamespace(text="from model")]),
                        turn_complete=False)))
    class Live(FakeLive):
        def connect(self, *, model, config):
            self.configs.append(config)
            self.sessions.append(ModelTurnSession())
            return FakeContext(self.sessions[-1])
    updates = []
    source = GeminiLiveWordSource(SimpleNamespace(aio=SimpleNamespace(live=Live())),
                                  lambda **_row: None)
    source.bind(lambda *row: updates.append(row))
    source.push_audio(0, bytes(16000))
    until = time.monotonic() + 2
    while not updates and time.monotonic() < until:
        time.sleep(.01)
    asyncio.run(source.finish())
    assert updates == [("from model", 0, 8000, False)]
