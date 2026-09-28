import asyncio
import threading
from types import SimpleNamespace

from moss_transcribe_diarize.app.gemini_hybrid_engine import FixedWindowScheduler, GeminiHybridEngine, OverlapRegistry
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiBase, GeminiPreview, GeminiRolling, GeminiSegment
from moss_transcribe_diarize.app.gemini_provider import GeminiWord, GeminiWords
from moss_transcribe_diarize.app.live_tape import CompleteMixedTape


class FakeDiarizer:
    def diarize(self, pcm16, *, deadline, kind, diarize=True):
        del deadline, kind, diarize
        return GeminiWords((GeminiWord("hello", "spk:0", 0, min(len(pcm16)//2, 3*16000)),))


class FakeWords:
    def words(self, pcm16, *, deadline):
        del deadline
        return (GeminiWord("hello", "spk:?", 0, min(len(pcm16)//2, 16000)),)


class FakeTerminal:
    def transcribe(self, tape):
        return (GeminiSegment(0, tape.sample_count, "hello", "terminal-0001"),)


def make_engine(updates):
    return GeminiHybridEngine(updates.append, word_source=FakeWords(),
        window_scheduler=FixedWindowScheduler(), registry=OverlapRegistry(),
        diarizer=FakeDiarizer(), terminal=FakeTerminal())


def test_normal_frontier_and_preview_are_separate(tmp_path):
    updates = []
    engine = make_engine(updates)
    for second in range(30):
        engine.push_audio(second*16000, bytes(32000))
        if second in {9, 19, 29}:
            engine._future.result(timeout=5)
    assert not any(isinstance(row, GeminiBase) and row.degraded for row in updates)
    rolls = [row for row in updates if isinstance(row, GeminiRolling)]
    assert [(row.start_sample, row.end_sample) for row in rolls] == [(0, 160000), (160000, 320000)]
    assert any(isinstance(row, GeminiPreview) for row in updates)
    tape = CompleteMixedTape(epoch=0, capacity_bytes=30*32000, storage_root=tmp_path)
    tape.append(start_sample=0, pcm=bytes(30*32000))
    assert asyncio.run(engine.finish(tape))[0].end_sample == 30*16000
    tape.release()


def test_stop_drain_requests_and_publishes_remaining_rolling_window():
    updates = []
    class TailDiarizer:
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            del deadline, kind, diarize
            end = len(pcm16) // 2
            return GeminiWords((GeminiWord("tail", "spk:0", end-2*16000, end-16000),))
    engine = GeminiHybridEngine(
        updates.append, word_source=FakeWords(), window_scheduler=FixedWindowScheduler(),
        registry=OverlapRegistry(), diarizer=TailDiarizer(), terminal=FakeTerminal())
    for second in range(30):
        engine.push_audio(second*16000, bytes(32000))
        if second in {9, 19, 29}:
            engine._future.result(timeout=5)
    assert engine._rolling_frontier == 20*16000
    assert asyncio.run(engine.drain_tail(1.0))
    tail = [row for row in updates if isinstance(row, GeminiRolling)
            and row.start_sample == 20*16000 and row.end_sample == 30*16000]
    assert len(tail) == 1
    assert [(row.text, row.start_sample, row.end_sample) for row in tail[0].segments] == [
        ("tail", 28*16000, 29*16000)]
    engine.close()


def test_slow_rolling_activates_degraded_base_before_retention(tmp_path):
    updates = []
    engine = make_engine(updates)
    started = threading.Event()
    release = threading.Event()
    original = engine.diarizer.diarize
    def slow(*args, **kwargs):
        started.set()
        release.wait(timeout=5)
        return original(*args, **kwargs)
    engine.diarizer.diarize = slow
    for second in range(20):
        engine.push_audio(second*16000, bytes(32000))
    assert started.wait(timeout=5)
    for second in range(20, 50):
        engine.push_audio(second*16000, bytes(32000))
    degraded = [row for row in updates if isinstance(row, GeminiBase) and row.degraded]
    assert degraded
    assert 50*16000 - degraded[-1].through_sample <= 45*16000
    release.set()
    tape = CompleteMixedTape(epoch=0, capacity_bytes=50*32000, storage_root=tmp_path)
    tape.append(start_sample=0, pcm=bytes(50*32000))
    asyncio.run(engine.finish(tape))
    tape.release()


def test_delayed_window_remains_in_cache_between_stride_boundaries():
    updates = []
    engine = make_engine(updates)
    started = threading.Event()
    release = threading.Event()
    original = engine.diarizer.diarize
    def slow(*args, **kwargs):
        started.set()
        release.wait(timeout=5)
        return original(*args, **kwargs)
    engine.diarizer.diarize = slow
    for half_second in range(40):
        engine.push_audio(half_second*8000, bytes(16000))
    assert started.wait(timeout=5)
    for half_second in range(40, 139):
        engine.push_audio(half_second*8000, bytes(16000))
    assert len(engine._recent_audio) == 69.5*32000
    release.set()
    engine._future.result(timeout=5)
    assert any(isinstance(row, GeminiRolling) and row.end_sample == 50*16000 for row in updates)
    engine.close()


def test_overlap_registry_keeps_id_when_local_label_changes():
    registry = OverlapRegistry()
    one, _ = registry.observe_window(0, (GeminiWord("a", "spk:0", 0, 32000),))
    two, _ = registry.observe_window(1, (GeminiWord("a", "spk:9", 16000, 48000),))
    assert one["spk:0"] == two["spk:9"] == "speaker-0001"


def test_registry_and_account_observation_receive_same_vector():
    updates = []
    class SpyRegistry(OverlapRegistry):
        seen = None
        def observe_window(self, start, words, embeddings=None):
            self.seen = embeddings
            return super().observe_window(start, words, embeddings)
    registry = SpyRegistry()
    spec = SimpleNamespace(provider="wespeaker", revision="test", state_sha256="ab"*32)
    engine = GeminiHybridEngine(updates.append, word_source=FakeWords(),
        window_scheduler=FixedWindowScheduler(), registry=registry,
        diarizer=FakeDiarizer(), terminal=FakeTerminal(),
        embedding_source=lambda pcm, start, words: {"spk:0": ((0.6, 0.8), 3.0)},
        encoder_spec=spec)
    for second in range(20):
        engine.push_audio(second*16000, bytes(32000))
    engine._future.result(timeout=5)
    observations = [obs for update in updates for obs in getattr(update, "observations", ())]
    assert len(observations) == 1
    assert observations[0].speaker_label == "speaker-0001"
    assert observations[0].centroid == registry.seen["spk:0"][0]
    engine.close()


def test_abort_closes_idle_engine_without_provider_call():
    engine = make_engine([])
    engine.close()
    assert engine._closed and engine._executor._shutdown


def test_wespeaker_window_source_uses_attributed_two_second_interval():
    import wave
    from moss_transcribe_diarize.app.gemini_hybrid_engine import WeSpeakerWindowEmbeddings
    class Encoder:
        spec = SimpleNamespace(embedding_dimension=2)
        def embed(self, path, intervals):
            with wave.open(path, "rb") as wav:
                assert wav.getnframes() == 5*16000 and wav.getframerate() == 16000
            assert intervals == [(1.0, 4.0)]
            return [0.6, 0.8]
    words = (GeminiWord("a", "spk:0", 16000, 32000),
             GeminiWord("b", "spk:0", 32000, 64000),
             GeminiWord("short", "spk:1", 64000, 72000))
    result = WeSpeakerWindowEmbeddings(Encoder())(bytes(5*32000), 0, words)
    assert result == {"spk:0": ((0.6, 0.8), 3.0)}


def test_rolling_word_gate_runs_before_registry_and_publication():
    updates = []
    class Gate:
        def filter(self, pcm, words, *, offset_sample):
            assert offset_sample == 10*16000
            assert len(pcm) == 10*32000
            assert [w.text for w in words] == ["silent", "voiced"]
            return tuple(w for w in words if w.text == "voiced")
    class Registry(OverlapRegistry):
        def observe_window(self, start, words, embeddings=None):
            assert [w.text for w in words] == ["voiced"]
            return super().observe_window(start, words, embeddings)
    engine = GeminiHybridEngine(updates.append, word_source=FakeWords(),
        window_scheduler=FixedWindowScheduler(), registry=Registry(),
        diarizer=FakeDiarizer(), terminal=FakeTerminal(), word_gate=Gate())
    engine._publish_window(10*16000, 20*16000, bytes(10*32000), (
        GeminiWord("silent", "s0", 0, 16000),
        GeminiWord("voiced", "s1", 16000, 32000)))
    rolls = [u for u in updates if isinstance(u, GeminiRolling)]
    assert len(rolls) == 1 and [r.text for r in rolls[0].segments] == ["voiced"]
    engine.close()


def test_stop_promotes_inflight_window_covering_accepted_tail():
    updates = []
    started = threading.Event()
    release = threading.Event()
    calls = []
    class SlowDiarizer:
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            calls.append(len(pcm16))
            started.set()
            release.wait(2)
            return GeminiWords((GeminiWord("tail", "s0", 45*16000, 49*16000),))
    engine = GeminiHybridEngine(updates.append, word_source=FakeWords(),
        window_scheduler=FixedWindowScheduler(), registry=OverlapRegistry(),
        diarizer=SlowDiarizer(), terminal=FakeTerminal())
    with engine._lock:
        engine._recent_audio = bytearray(50*32000)
        engine._accepted = 50*16000
        engine._last_window_end = 40*16000
        engine._rolling_frontier = engine._committed = 30*16000
    engine._future = engine._executor.submit(engine._work)
    assert started.wait(2)
    async def stop():
        task = asyncio.create_task(engine.drain_tail(2))
        await asyncio.sleep(.02)
        release.set()
        return await task
    assert asyncio.run(stop())
    assert engine._rolling_frontier == 50*16000
    assert len(calls) == 1
    engine.close()


def test_idle_drain_promotes_inflight_window_without_second_call(monkeypatch):
    import time
    monkeypatch.setattr(GeminiHybridEngine, "_IDLE_SECONDS", .05)
    started = threading.Event()
    release = threading.Event()
    calls = []
    class Source:
        def bind(self, listener): pass
        def push_audio(self, start_sample, pcm16): pass
        async def finish(self): pass
        def close(self): pass
    class SlowDiarizer:
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            calls.append(len(pcm16))
            started.set()
            release.wait(2)
            return GeminiWords((GeminiWord("tail", "s0", 18*16000, 19*16000),))
    engine = GeminiHybridEngine(lambda _update: None, word_source=Source(),
        window_scheduler=FixedWindowScheduler(), registry=OverlapRegistry(),
        diarizer=SlowDiarizer(), terminal=FakeTerminal())
    for second in range(20):
        engine.push_audio(second*16000, bytes(32000))
    assert started.wait(2)
    time.sleep(.08)
    assert engine._rolling_frontier == 0  # In-flight request is still pending.
    release.set()
    engine._future.result(timeout=2)
    assert engine._rolling_frontier == 20*16000
    assert calls == [20*32000]
    engine.close()
