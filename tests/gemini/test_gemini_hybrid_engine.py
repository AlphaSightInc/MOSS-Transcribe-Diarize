import asyncio
import threading
from types import SimpleNamespace

from moss_transcribe_diarize.app.gemini_hybrid_engine import FixedWindowScheduler, GrowingContextWindowScheduler, GeminiHybridEngine, OverlapRegistry
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiBase, GeminiPreview, GeminiRolling, GeminiSegment
from moss_transcribe_diarize.app.gemini_provider import GeminiWord, GeminiWords
from moss_transcribe_diarize.app.gemini_continuity_registry import ContinuityRegistry
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


def test_rolling_turns_keep_annotation_order_after_timestamp_repair():
    updates = []
    engine = make_engine(updates)
    engine._publish_window(0, 2*16000, bytes(2*32000), (
        GeminiWord("one", "A", 0, 16000),
        GeminiWord("two", "B", 19200, 20800),
        GeminiWord("three", "A", 14400, 16000)))
    rows = [row for update in updates if isinstance(update, GeminiRolling)
            for row in update.segments]
    assert [row.text for row in rows] == ["one", "two", "three"]
    assert rows[0].speaker == rows[2].speaker != rows[1].speaker
    engine.close()


def test_continuity_registry_uses_full_observation_overlap_with_end_owned_words():
    updates = []
    class TailWords:
        calls = 0
        def diarize(self, _pcm, *, deadline, kind, diarize=True):
            del deadline, kind, diarize
            self.calls += 1
            if self.calls == 1:
                return GeminiWords((GeminiWord("a", "A", 9*16000, round(11.1*16000)),))
            return GeminiWords((GeminiWord("b", "B", round(10.2*16000),
                                           round(12.3*16000)),))
    registry = ContinuityRegistry(embedding_threshold=.46, within_window_threshold=.60,
                                  birth_min_seconds=2)
    engine = GeminiHybridEngine(updates.append, word_source=FakeWords(),
        window_scheduler=FixedWindowScheduler(), registry=registry,
        diarizer=TailWords(), terminal=FakeTerminal())
    for second in range(30):
        engine.push_audio(second*16000, bytes(32000))
        if second in {19, 29}:
            engine._future.result(timeout=5)
    rolls = [update for update in updates if isinstance(update, GeminiRolling)]
    assert len(rolls) == 2
    assert rolls[0].segments == ()
    assert rolls[1].segments[0].speaker == "speaker-0001"
    engine.close()


def test_silent_microphone_skips_batch_calls_then_births_one_local_speaker():
    from moss_transcribe_diarize.app.gemini_hybrid_engine import SingleMicrophoneRegistry
    calls = []
    updates = []
    class MicDiarizer:
        def diarize(self, pcm, *, deadline, kind, diarize=True):
            calls.append((len(pcm)//32000, diarize))
            return GeminiWords((GeminiWord("local", "spk:?", 10*16000, 11*16000),))
    engine = GeminiHybridEngine(updates.append, word_source=FakeWords(),
        window_scheduler=GrowingContextWindowScheduler(max_seconds=30, stride_seconds=10),
        registry=SingleMicrophoneRegistry(), diarizer=MicDiarizer(), terminal=FakeTerminal(),
        source_lane="microphone", voiced_audio=lambda pcm: any(pcm),
        diarize_windows=False)
    engine.push_audio(0, bytes(10*32000))
    engine._future.result(timeout=5)
    assert calls == []
    assert all(not row.segments for row in updates if isinstance(row, GeminiRolling))
    engine.push_audio(10*16000, b"\x01\x00"*(10*16000))
    engine._future.result(timeout=5)
    assert calls == [(20, False)]
    mic = [row for update in updates if isinstance(update, GeminiRolling)
           for row in update.segments]
    assert [(row.text, row.speaker, row.source_lane) for row in mic] == [
        ("local", "speaker-microphone", "microphone")]
    engine.close()


def test_silent_system_window_advances_frontier_without_gemini_call():
    from moss_transcribe_diarize.app.gemini_lane_engine import WebRtcSpeechDetector
    updates = []
    class ForbiddenDiarizer:
        def diarize(self, *_args, **_kwargs):
            raise AssertionError("unvoiced rolling audio must not reach Gemini")
    engine = GeminiHybridEngine(
        updates.append, word_source=FakeWords(),
        window_scheduler=GrowingContextWindowScheduler(max_seconds=180, stride_seconds=15),
        registry=OverlapRegistry(), diarizer=ForbiddenDiarizer(), terminal=FakeTerminal(),
        voiced_audio=WebRtcSpeechDetector(), source_lane="system")
    engine.push_audio(0, bytes(15*32000))
    engine._future.result(timeout=5)
    rolls = [row for row in updates if isinstance(row, GeminiRolling)]
    assert len(rolls) == 1
    assert rolls[0].end_sample == 15*16000 and rolls[0].segments == ()
    engine.close()


def test_microphone_short_windows_open_only_on_new_voiced_audio_and_drain_quiet_tail():
    from moss_transcribe_diarize.app.gemini_hybrid_engine import SingleMicrophoneRegistry
    calls = []
    updates = []
    class Source:
        def bind(self, listener): pass
        def push_audio(self, start_sample, pcm16): pass
        async def finish(self): pass
        def close(self): pass
    class MicDiarizer:
        def diarize(self, pcm, *, deadline, kind, diarize=True):
            calls.append((len(pcm)//32000, diarize))
            return GeminiWords(())
    engine = GeminiHybridEngine(updates.append, word_source=Source(),
        window_scheduler=GrowingContextWindowScheduler(max_seconds=30, stride_seconds=15),
        registry=SingleMicrophoneRegistry(), diarizer=MicDiarizer(), terminal=FakeTerminal(),
        source_lane="microphone", voiced_audio=lambda pcm: any(pcm),
        diarize_windows=False)
    engine.push_audio(0, b"\x01\x00"*(15*16000))
    engine._future.result(timeout=5)
    assert calls == [(15, False)]
    engine.push_audio(15*16000, bytes(15*32000))
    engine._future.result(timeout=5)
    assert calls == [(15, False)]  # Old voice in the 30 s overlap is not new speech.
    engine.push_audio(30*16000, b"\x01\x00"*(15*16000))
    engine._future.result(timeout=5)
    assert calls == [(15, False), (30, False)]
    engine.push_audio(45*16000, bytes(5*32000))
    assert asyncio.run(engine.drain_tail(1.0))
    assert calls == [(15, False), (30, False)]
    assert engine._rolling_frontier == 50*16000
    assert [row.end_sample for row in updates if isinstance(row, GeminiRolling)] == [
        15*16000, 30*16000, 45*16000, 50*16000]
    engine.close()


def test_registry_and_account_observation_receive_same_vector():
    updates = []
    class SpyRegistry(OverlapRegistry):
        seen = None
        def observe_window(self, start, words, embeddings=None, *, committed_through_sample=None):
            self.seen = embeddings
            return super().observe_window(start, words, embeddings,
                                          committed_through_sample=committed_through_sample)
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


def test_wespeaker_window_source_uses_prototype_continuous_intervals():
    from moss_transcribe_diarize.app.gemini_hybrid_engine import WeSpeakerWindowEmbeddings
    calls = []
    class Encoder:
        spec = SimpleNamespace(embedding_dimension=2)
        def embed(self, _path, intervals):
            calls.append(intervals)
            return [0.6, 0.8]
    S = 16000
    words = tuple(GeminiWord(str(i), "A", round(start*S), round(end*S))
                  for i, (start, end) in enumerate(((1.5, 3.5), (4.0, 7.0),
                                                     (7.6, 12.5), (14.0, 16.5))))
    result = WeSpeakerWindowEmbeddings(Encoder())(bytes(20*32000), 0, words)
    assert calls == [[(1.5, 11.5), (14.0, 16.5)]]
    assert result == {"A": ((0.6, 0.8), 12.5)}


def test_rolling_owns_words_by_end_and_bridges_same_speaker_frontier_gap():
    from moss_transcribe_diarize.app.gemini_live_runtime import GeminiTurnBridge
    updates = []
    engine = make_engine(updates)
    S = 16000
    engine._publish_window(0, 15*S, bytes(15*32000), (
        GeminiWord("before", "A", 14*S, round(14.5*S)),
        GeminiWord("bank", "A", round(14.9*S), round(15.2*S))))
    engine._publish_window(0, 30*S, bytes(30*32000), (
        GeminiWord("bank", "A", round(14.9*S), round(15.2*S)),
        GeminiWord("next", "A", 16*S, round(16.4*S))))
    rolls = [row for row in updates if isinstance(row, GeminiRolling)]
    assert [[s.text for s in roll.segments] for roll in rolls] == [["before"], ["bank next"]]
    assert rolls[1].segments[0].start_sample == 15*S
    assert [row.new_end_sample for row in updates if isinstance(row, GeminiTurnBridge)] == [15*S]
    engine.close()


def test_rolling_word_gate_runs_before_registry_and_publication():
    updates = []
    class Gate:
        def filter(self, pcm, words, *, offset_sample):
            assert offset_sample == 10*16000
            assert len(pcm) == 10*32000
            assert [w.text for w in words] == ["silent", "voiced"]
            return tuple(w for w in words if w.text == "voiced")
    class Registry(OverlapRegistry):
        def observe_window(self, start, words, embeddings=None, *, committed_through_sample=None):
            assert [w.text for w in words] == ["voiced"]
            return super().observe_window(start, words, embeddings,
                                          committed_through_sample=committed_through_sample)
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


def test_growing_context_scheduler_uses_latest_stride_tick_and_variable_start():
    scheduler = GrowingContextWindowScheduler(max_seconds=30, stride_seconds=10)
    assert scheduler.next_window(9*16000, 0) is None
    assert scheduler.next_window(10*16000, 0) == (0, 10*16000, 10*16000)
    assert scheduler.next_window(20*16000, 10*16000) == (0, 20*16000, 20*16000)
    assert scheduler.next_window(35*16000, 30*16000) is None
    assert scheduler.next_window(50*16000, 20*16000) == (20*16000, 50*16000, 50*16000)
    long = GrowingContextWindowScheduler(max_seconds=300, stride_seconds=10)
    assert long.next_window(310*16000, 300*16000) == (10*16000, 310*16000, 310*16000)
    assert long.cache_seconds == 310


def test_growing_window_cache_reads_three_hundred_seconds_after_delayed_tick():
    engine = GeminiHybridEngine(lambda _update: None, word_source=FakeWords(),
        window_scheduler=GrowingContextWindowScheduler(max_seconds=300, stride_seconds=10),
        registry=OverlapRegistry(), diarizer=FakeDiarizer(), terminal=FakeTerminal())
    engine.push_audio(0, bytes(621*16000))  # 310.5 s, deliberately between ticks.
    assert engine._future.result(timeout=5) is None
    assert len(engine._recent_audio) == 310*32000
    assert len(engine._read_locked(10*16000, 310*16000)) == 300*32000
    engine.close()


def test_growing_window_skips_busy_ticks_and_counts_them_once():
    started = threading.Event()
    release = threading.Event()
    calls = []
    usage = []
    active = {"now": 0, "peak": 0}
    class SlowDiarizer:
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            active["now"] += 1
            active["peak"] = max(active["peak"], active["now"])
            try:
                calls.append(len(pcm16)//32000)
                if len(calls) == 1:
                    started.set()
                    release.wait(2)
                return GeminiWords(())
            finally:
                active["now"] -= 1
    class Source:
        def bind(self, listener): pass
        def push_audio(self, start_sample, pcm16): pass
        async def finish(self): pass
        def close(self): pass
    engine = GeminiHybridEngine(lambda _update: None, word_source=Source(),
        window_scheduler=GrowingContextWindowScheduler(max_seconds=30, stride_seconds=10),
        registry=OverlapRegistry(), diarizer=SlowDiarizer(), terminal=FakeTerminal(),
        report_usage=lambda **row: usage.append(row))
    engine.push_audio(0, bytes(10*32000))
    assert started.wait(2)
    engine.push_audio(10*16000, bytes(25*32000))
    release.set()
    engine._future.result(timeout=5)
    assert calls == [10, 30]  # t=20 was skipped; one call at t=30.
    assert active["peak"] == 1
    assert usage == [{"kind": "rolling", "count_call": False, "skipped_window_ticks": 1}]
    engine.close()


def test_growing_idle_window_uses_exact_unrevised_suffix():
    import time
    calls = []
    class Source:
        def bind(self, listener): pass
        def push_audio(self, start_sample, pcm16): pass
        async def finish(self): pass
        def close(self): pass
    class Diarizer:
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            calls.append(len(pcm16)//32000)
            return GeminiWords(())
    scheduler = GrowingContextWindowScheduler(max_seconds=30, stride_seconds=20)
    scheduler.idle_seconds = .05  # Compress only the idle wait, not window geometry.
    engine = GeminiHybridEngine(lambda _update: None, word_source=Source(),
        window_scheduler=scheduler, registry=OverlapRegistry(),
        diarizer=Diarizer(), terminal=FakeTerminal())
    engine.push_audio(0, bytes(45*32000))
    until = time.monotonic() + 2
    while engine._rolling_frontier < 45*16000 and time.monotonic() < until:
        time.sleep(.01)
    assert engine._rolling_frontier == 45*16000
    assert calls == [30, 5]  # t40 [10,40], exact idle suffix [40,45].
    engine.close()


def test_c4_stop_drain_sends_only_unrevised_suffix():
    calls = []
    class Source:
        def bind(self, listener): pass
        def push_audio(self, start_sample, pcm16): pass
        async def finish(self): pass
        def close(self): pass
    class Diarizer:
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            calls.append(len(pcm16)//32000)
            return GeminiWords(())
    engine = GeminiHybridEngine(lambda _update: None, word_source=Source(),
        window_scheduler=GrowingContextWindowScheduler(max_seconds=180, stride_seconds=15),
        registry=OverlapRegistry(), diarizer=Diarizer(), terminal=FakeTerminal())
    engine.push_audio(0, bytes(195*32000))
    engine._future.result(timeout=5)
    engine.push_audio(195*16000, bytes(5*32000))
    assert asyncio.run(engine.drain_tail(2))
    assert calls == [180, 5]
    assert engine._rolling_frontier == 200*16000
    engine.close()


def test_idle_window_counts_ticks_skipped_while_prior_call_was_busy():
    import time
    started = threading.Event()
    release = threading.Event()
    usage = []
    class Source:
        def bind(self, listener): pass
        def push_audio(self, start_sample, pcm16): pass
        async def finish(self): pass
        def close(self): pass
    class SlowDiarizer:
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            if not started.is_set():
                started.set()
                release.wait(2)
            return GeminiWords(())
    scheduler = GrowingContextWindowScheduler(max_seconds=30, stride_seconds=10)
    scheduler.idle_seconds = .05
    engine = GeminiHybridEngine(lambda _update: None, word_source=Source(),
        window_scheduler=scheduler, registry=OverlapRegistry(),
        diarizer=SlowDiarizer(), terminal=FakeTerminal(),
        report_usage=lambda **row: usage.append(row))
    engine.push_audio(0, bytes(10*32000))
    assert started.wait(2)
    engine.push_audio(10*16000, bytes(25*32000))
    time.sleep(.08)  # t20 and t30 pass while t10 is in flight.
    release.set()
    engine._future.result(timeout=5)
    assert engine._rolling_frontier == 35*16000
    assert usage == [{"kind": "rolling", "count_call": False, "skipped_window_ticks": 1}]
    engine.close()
