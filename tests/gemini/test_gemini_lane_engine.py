import asyncio
from array import array

from moss_transcribe_diarize.app.gemini_lane_engine import (LaneGeminiEngine, TextEchoGuard,
    SystemWordLedger, LazyMicrophoneWords, AcousticEchoGuard, MicrophoneWordGate)
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiBase, GeminiRolling, GeminiSegment
from moss_transcribe_diarize.app.gemini_provider import GeminiWord


def test_two_lane_engines_publish_one_overlapping_forward_revision(tmp_path):
    updates = []
    received = {}
    class FakeLane:
        def __init__(self, lane, publish):
            self.lane, self.publish = lane, publish
        def push_audio(self, start_sample, pcm16):
            received[self.lane] = pcm16
            self.publish(GeminiBase(16000, ()))
            row = GeminiSegment(0 if self.lane == "system" else 4000,
                                12000 if self.lane == "system" else 14000,
                                self.lane, "speaker-0001" if self.lane == "system"
                                else "speaker-microphone", self.lane)
            self.publish(GeminiRolling(0, 16000, (row,)))
        async def drain_tail(self, deadline): return True
        async def finish(self, tape): return ()
        def close(self): pass
    engine = LaneGeminiEngine(
        updates.append,
        system_factory=lambda publish: FakeLane("system", publish),
        microphone_factory=lambda publish: FakeLane("microphone", publish),
        tape_root=tmp_path,
    )
    engine.push_audio(0, bytes(32000),
                      lane_pcm=(("system", b"\x01\x00" * 16000),
                                ("microphone", b"\x02\x00" * 16000)))
    assert received["system"][:2] == b"\x01\x00"
    assert received["microphone"][:2] == b"\x02\x00"
    bases = [u for u in updates if isinstance(u, GeminiBase)]
    rolls = [u for u in updates if isinstance(u, GeminiRolling)]
    assert len(bases) == len(rolls) == 1
    assert rolls[0].revision_lanes == ("system", "microphone")
    assert [(row.source_lane, row.start_sample) for row in rolls[0].segments] == [
        ("system", 0), ("microphone", 4000)]
    assert asyncio.run(engine.drain_tail(1.0))
    engine.close()


def test_exact_text_echo_guard_preserves_different_and_distant_words():
    guard = TextEchoGuard()
    system = (GeminiWord("They're", "s1", 16000, 24000),)
    mic = (GeminiWord("they're", "m", 16000, 24000),
           GeminiWord("local", "m", 16000, 24000),
           GeminiWord("they're", "m", 64000, 72000))
    assert [w.text for w in guard.filter(mic, system)] == ["local", "they're"]


def test_microphone_word_gate_uses_system_words_before_local_identity():
    ledger = SystemWordLedger()
    ledger.observe((GeminiWord("hello", "s", 0, 16000),), 16000)
    words = (GeminiWord("hello", "m", 0, 16000),
             GeminiWord("local", "m", 0, 16000))
    assert [w.text for w in ledger.filter_mic(words, through_sample=16000)] == ["local"]


def test_acoustic_guard_system_voice_ratio_lag_and_unvoiced_bypass():
    class Vad:
        def is_speech(self, frame, sample_rate):
            return any(memoryview(frame).cast("h"))
    # A 30 ms mic delay: 1000-amplitude system speech arrives as 100-amplitude echo.
    system = array("h", [0]*1600 + [1000]*3200 + [0]*1600).tobytes()
    mic = array("h", [0]*2080 + [100]*3200 + [0]*1120).tobytes()
    guard = AcousticEchoGuard(lambda start, end: system[start*2:end*2], vad=Vad())
    echoed = GeminiWord("echo", "m", 2080, 5280)
    quiet_source = GeminiWord("local", "m", 5280, 5920)
    assert guard.filter(mic, (echoed, quiet_source)) == (quiet_source,)
    loud = array("h", [0]*2080 + [200]*3200 + [0]*1120).tobytes()
    assert guard.filter(loud, (echoed,)) == (echoed,)


def test_microphone_gate_requires_acoustic_and_text_admission_with_separate_counts():
    class PassVoice:
        def filter(self, pcm, words, *, offset_sample=0): return tuple(words)
    class Acoustic:
        def filter(self, pcm, words, *, offset_sample=0):
            return tuple(w for w in words if w.text != "echo")
    ledger = SystemWordLedger()
    ledger.observe((GeminiWord("same", "s", 0, 16000),), 16000)
    counts = []
    gate = MicrophoneWordGate(PassVoice(), ledger, Acoustic(), counts.append)
    words = tuple(GeminiWord(text, "m", 0, 16000)
                  for text in ("echo", "same", "local"))
    assert [w.text for w in gate.filter(bytes(32000), words)] == ["local"]
    assert counts == [{"acoustic_gate_dropped_words": 1, "text_guard_dropped_words": 1}]
    assert [w.text for w in gate.filter_terminal(bytes(32000), words,
        (GeminiWord("same", "s", 0, 16000),))] == ["local"]
    assert counts[-1] == counts[0]


def test_lazy_microphone_preview_opens_on_voice_and_closes_after_60s_quiet():
    made = []
    observed = []
    class Source:
        def __init__(self):
            self.sent = []
            self.closed = False
            made.append(self)
        def bind(self, callback): self.callback = callback
        def push_audio(self, start, pcm):
            self.sent.append(start)
            self.callback("local", start, start+len(pcm)//2, True)
        def close(self): self.closed = True
        async def finish(self): self.closed = True
    lazy = LazyMicrophoneWords(Source, voiced_audio=lambda pcm: any(pcm))
    lazy.bind(lambda text, start, end, final: observed.append((text, start, end)))
    lazy.push_audio(0, bytes(32000))
    assert made == []
    lazy.push_audio(16000, b"\x01\x00"*16000)
    assert len(made) == 1 and observed[-1] == ("local", 16000, 32000)
    for second in range(2, 63):
        lazy.push_audio(second*16000, bytes(32000))
    assert made[0].closed
    lazy.push_audio(63*16000, b"\x01\x00"*16000)
    assert len(made) == 2 and observed[-1] == ("local", 63*16000, 64*16000)
    asyncio.run(lazy.finish())
