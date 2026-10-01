import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
from array import array

from moss_transcribe_diarize.app.gemini_lane_engine import (LaneGeminiEngine, TextEchoGuard,
    SystemWordLedger, VoicedLiveWords, AcousticEchoGuard, MicrophoneWordGate,
    SerializedDiarizer, CrossLaneVoiceEchoGuard)
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiBase, GeminiRolling, GeminiRelabel, GeminiSegment, GeminiTurnBridge
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiPreview
from moss_transcribe_diarize.app.gemini_provider import GeminiWord


def test_two_lane_engines_publish_one_overlapping_forward_revision(tmp_path):
    updates = []
    received = {}
    class FakeLane:
        def __init__(self, lane, publish):
            self.lane, self.publish = lane, publish
            self.terminal_coverage_gaps = ((lane, 12000, 14000),)
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
    assert asyncio.run(engine.finish(None)) == ()
    assert engine.terminal_coverage_gaps == (("system", 12000, 14000),
                                             ("microphone", 12000, 14000))
    engine.close()


def test_lag_fallback_commits_current_preview_words_from_both_lanes(tmp_path):
    updates = []
    class StalledLane:
        def __init__(self, publish): self.publish = publish
        def push_audio(self, start_sample, pcm16): pass
        def close(self): pass
    engine = LaneGeminiEngine(updates.append, system_factory=StalledLane,
                              microphone_factory=StalledLane, tape_root=tmp_path)
    engine._on_update("system", GeminiPreview(10*16000, (
        GeminiSegment(2*16000, 3*16000, "remote words", source_lane="system"),)))
    engine._on_update("microphone", GeminiPreview(10*16000, (
        GeminiSegment(4*16000, 5*16000, "local words", source_lane="microphone"),)))
    for second in range(46):
        engine.push_lanes(second*16000,
            (("system", bytes(32000)), ("microphone", bytes(32000))))
    degraded = [row for row in updates if isinstance(row, GeminiBase) and row.degraded]
    assert len(degraded) == 1
    assert [(row.text, row.source_lane, row.speaker) for row in degraded[0].segments] == [
        ("remote words", "system", None), ("local words", "microphone", None)]
    engine.close()


def test_system_and_microphone_batch_calls_overlap_but_each_lane_serializes():
    from moss_transcribe_diarize.app.phase2_web_cli import _serialize_gemini_lanes
    active = 0
    peak = 0
    lock = threading.Lock()
    both_started = threading.Barrier(2)

    class SlowProvider:
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            both_started.wait(timeout=1)
            with lock:
                active -= 1
            return ()

    system, microphone = _serialize_gemini_lanes(SlowProvider(), SlowProvider())
    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(system.diarize, b"", deadline=1, kind="rolling")
        right = pool.submit(microphone.diarize, b"", deadline=1, kind="rolling")
        left.result()
        right.result()
    assert peak == 2

    lane_peak = 0
    lane_active = 0
    class OneLane:
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            nonlocal lane_peak, lane_active
            with lock:
                lane_active += 1
                lane_peak = max(lane_peak, lane_active)
            threading.Event().wait(.02)
            with lock:
                lane_active -= 1
            return ()
    one = SerializedDiarizer(OneLane())
    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = [pool.submit(one.diarize, b"", deadline=1, kind="rolling") for _ in range(2)]
        for call in calls:
            call.result()
    assert lane_peak == 1


def test_lane_engine_forwards_system_turn_bridge_after_both_lanes_commit(tmp_path):
    updates = []
    class FakeLane:
        def __init__(self, publish): self.publish = publish
        def push_audio(self, start_sample, pcm16): pass
        async def drain_tail(self, deadline): return True
        async def finish(self, tape): return ()
        def close(self): pass
    engine = LaneGeminiEngine(
        updates.append, system_factory=FakeLane, microphone_factory=FakeLane,
        tape_root=tmp_path)
    prior = GeminiSegment(0, 9*16000, "one", "speaker-0001", "system")
    following = GeminiSegment(10*16000, 11*16000, "two", "speaker-0001", "system")
    engine._on_update("system", GeminiRolling(0, 10*16000, (prior,)))
    engine._on_update("microphone", GeminiRolling(0, 10*16000, ()))
    engine._on_update("system", GeminiRolling(10*16000, 20*16000, (following,)))
    bridge = GeminiTurnBridge(0, 9*16000, 10*16000, "system")
    engine._on_update("system", bridge)
    assert not any(isinstance(row, GeminiTurnBridge) for row in updates)
    engine._on_update("microphone", GeminiRolling(10*16000, 20*16000, ()))
    assert [row for row in updates if isinstance(row, GeminiTurnBridge)] == [bridge]
    engine.close()


def test_relabel_updates_only_the_originating_lane(tmp_path):
    updates = []
    class FakeLane:
        def __init__(self, publish): pass
        def push_audio(self, start_sample, pcm16): pass
        async def drain_tail(self, deadline): return True
        async def finish(self, tape): return ()
        def close(self): pass
    engine = LaneGeminiEngine(updates.append, system_factory=FakeLane,
                              microphone_factory=FakeLane, tape_root=tmp_path)
    system = GeminiSegment(0, 8000, "remote", None, "system")
    mic = GeminiSegment(0, 8000, "local", "local-0001", "microphone")
    engine._on_update("system", GeminiRolling(0, 16000, (system,)))
    engine._on_update("microphone", GeminiRolling(0, 16000, (mic,)))
    known = GeminiSegment(0, 8000, "remote", "speaker-0001", "system")
    engine._on_update("system", GeminiRelabel(0, 8000, (known,)))
    relabel = [row for row in updates if isinstance(row, GeminiRelabel)]
    assert len(relabel) == 1
    assert relabel[0].segments == (known,)
    engine.close()


def test_lane_turn_bridge_waits_when_microphone_frontier_lags(tmp_path):
    updates = []
    class FakeLane:
        def __init__(self, publish): pass
        def push_audio(self, start_sample, pcm16): pass
        async def drain_tail(self, deadline): return True
        async def finish(self, tape): return ()
        def close(self): pass
    engine = LaneGeminiEngine(updates.append, system_factory=FakeLane,
                              microphone_factory=FakeLane, tape_root=tmp_path)
    prior = GeminiSegment(0, 9*16000, "one", "speaker-0001", "system")
    following = GeminiSegment(10*16000, 11*16000, "two", "speaker-0001", "system")
    engine._on_update("system", GeminiRolling(0, 10*16000, (prior,)))
    engine._on_update("system", GeminiRolling(10*16000, 20*16000, (following,)))
    engine._on_update("system", GeminiTurnBridge(0, 9*16000, 10*16000, "system"))
    engine._on_update("microphone", GeminiRolling(0, 10*16000, ()))
    first = next(row for row in updates if isinstance(row, GeminiRolling))
    assert first.end_sample == 10*16000
    assert first.segments == (prior,)
    assert not any(isinstance(row, GeminiTurnBridge) for row in updates)
    engine._on_update("microphone", GeminiRolling(10*16000, 20*16000, ()))
    assert [row.end_sample for row in updates if isinstance(row, GeminiRolling)][-1] == 20*16000
    assert sum(isinstance(row, GeminiTurnBridge) for row in updates) == 1
    engine.close()


def test_exact_text_echo_guard_preserves_different_and_distant_words():
    guard = TextEchoGuard()
    system = (GeminiWord("They're", "s1", 16000, 24000),)
    mic = (GeminiWord("they're", "m", 16000, 24000),
           GeminiWord("local", "m", 16000, 24000),
           GeminiWord("they're", "m", 64000, 72000))
    assert [w.text for w in guard.filter(mic, system)] == ["local", "they're"]


def test_voice_aware_text_echo_guard_keeps_single_local_match_and_drops_phrase():
    guard = TextEchoGuard()
    system = (GeminiWord("same", "A", 0, 4000),
              GeminiWord("phrase", "A", 4000, 8000),
              GeminiWord("another", "A", 8000, 12000))
    mic = (GeminiWord("same", "C", 0, 4000),
           GeminiWord("phrase", "C", 4000, 8000),
           GeminiWord("another", "D", 8000, 12000),
           GeminiWord("same", "vectorless", 0, 4000))
    assert guard.filter_voice_aware(mic, system, {"C": ((0., 1.), 3.),
                                                 "D": ((0., 1.), 3.)}) == (mic[2],)


def test_microphone_word_gate_uses_system_words_before_local_identity():
    ledger = SystemWordLedger()
    ledger.observe((GeminiWord("hello", "s", 0, 16000),), 16000)
    words = (GeminiWord("hello", "m", 0, 16000),
             GeminiWord("local", "m", 0, 16000))
    assert [w.text for w in ledger.filter_mic(words, through_sample=16000)] == ["local"]


def test_voice_echo_requires_matching_voice_and_time_not_just_overlap():
    guard = CrossLaneVoiceEchoGuard(threshold=.60)
    system = (GeminiWord("remote", "A", 0, 16000),)
    guard.observe_system(system, {"A": ((1., 0.), 3.)}, frontier=16000)
    microphone = (
        GeminiWord("different echo words", "echo", 1000, 9000),
        GeminiWord("local overlap", "C", 1000, 9000),
        GeminiWord("late remote", "echo", 32000, 40000),
    )
    vectors = {"echo": ((.8, .6), 3.), "C": ((0., 1.), 3.)}
    kept = guard.filter_mic(microphone, vectors, through_sample=16000)
    assert [word.text for word in kept] == ["local overlap", "late remote"]
    assert guard.dropped == 1


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
    # Two seconds of attributed speech: the live window has local speech context.
    words = tuple(GeminiWord(text, "m", 0, 32000)
                  for text in ("echo", "same", "local"))
    assert [w.text for w in gate.filter(bytes(32000), words)] == ["local"]
    assert counts == [{"acoustic_gate_dropped_words": 1, "text_guard_dropped_words": 1}]
    assert [w.text for w in gate.filter_terminal(bytes(32000), words,
        (GeminiWord("same", "s", 0, 16000),))] == ["local"]
    assert counts[-1] == counts[0]


def test_microphone_word_gate_reports_voice_echo_drops_after_existing_guards():
    class PassVoice:
        def filter(self, pcm, words, *, offset_sample=0): return tuple(words)
    ledger = SystemWordLedger()
    ledger.observe((GeminiWord("remote", "A", 0, 16000),), 16000)
    voice = CrossLaneVoiceEchoGuard(threshold=.60)
    voice.observe_system((GeminiWord("remote", "A", 0, 16000),),
                         {"A": ((1., 0.), 3.)}, frontier=16000)
    def embed(pcm, start, words):
        return {label: ((1., 0.) if label == "echo" else (0., 1.), 3.)
                for label in {word.speaker for word in words}}
    counts = []
    gate = MicrophoneWordGate(PassVoice(), ledger, report_drops=counts.append,
                              voice_guard=voice, embedding_source=embed)
    words = (GeminiWord("different", "echo", 0, 8000),
             GeminiWord("local", "C", 0, 32000))
    assert gate.filter(bytes(32000), words) == (words[1],)
    assert counts == [{"acoustic_gate_dropped_words": 0,
                       "text_guard_dropped_words": 0,
                       "mic_echo_dropped_by_voice": 1}]


def test_microphone_gate_keeps_single_matching_word_from_distinct_local_voice():
    class PassVoice:
        def filter(self, pcm, words, *, offset_sample=0): return tuple(words)
    ledger = SystemWordLedger()
    system = (GeminiWord("shared", "A", 0, 16000),)
    ledger.observe(system, 16000)
    voice = CrossLaneVoiceEchoGuard(threshold=.60)
    voice.observe_system(system, {"A": ((1., 0.), 3.)}, frontier=16000)
    mic = (GeminiWord("shared", "C", 0, 32000),)
    gate = MicrophoneWordGate(PassVoice(), ledger, voice_guard=voice,
                              embedding_source=lambda pcm, start, words: {"C": ((0., 1.), 3.)})
    assert gate.filter(bytes(32000), mic) == mic


def _passing_microphone_gate(counts):
    class PassVoice:
        def filter(self, pcm, words, *, offset_sample=0): return tuple(words)
    ledger = SystemWordLedger()
    ledger.observe((), 30*16000)
    return MicrophoneWordGate(PassVoice(), ledger, report_drops=counts.append)


def test_microphone_live_window_without_local_speech_context_publishes_no_words():
    # Measured (prototypes/gemini-live/mic-hallucination): in a 30 s mic window holding only
    # room noise or echo residue, Gemini returns isolated short words, often in another
    # language, that pass every echo and voice gate.
    counts = []
    gate = _passing_microphone_gate(counts)
    noise_words = (GeminiWord("Oui.", "spk:0", 16000, 17600),
                   GeminiWord("はい。", "spk:0", 80000, 81600),
                   GeminiWord("Mamma", "spk:1", 160000, 161600),
                   GeminiWord("mia!", "spk:1", 161600, 163200),
                   GeminiWord("好。", "spk:0", 240000, 241600))
    assert gate.filter(bytes(30*32000), noise_words) == ()
    assert counts == [{"acoustic_gate_dropped_words": 0, "text_guard_dropped_words": 0,
                       "unanchored_window_dropped_words": 5}]


def test_local_speech_context_keeps_short_and_mixed_language_words_in_the_window():
    counts = []
    gate = _passing_microphone_gate(counts)
    # A 2.4 s Mandarin run (per-character words, as Gemini returns them) anchors the
    # window; an English backchannel and a code-switched term 10 s later are kept.
    sentence = tuple(GeminiWord(ch, "spk:0", 16000 + i*3200, 16000 + (i+1)*3200)
                     for i, ch in enumerate("我觉得这个方案可以先上线。"[:12]))
    later = (GeminiWord("OK.", "spk:0", 200000, 204800),
             GeminiWord("API", "spk:0", 300000, 304800))
    kept = gate.filter(bytes(30*32000), sentence + later)
    assert kept == sentence + later
    assert counts == [{"acoustic_gate_dropped_words": 0, "text_guard_dropped_words": 0}]


def test_short_joined_words_under_two_seconds_are_not_local_speech_context():
    counts = []
    gate = _passing_microphone_gate(counts)
    # Three words 0.5 s apart span 1.9 s: the voiceprint evidence needs 2 s joined by <= 0.6 s.
    words = tuple(GeminiWord(text, "spk:0", 16000 + i*12800, 16000 + i*12800 + 4800)
                  for i, text in enumerate(("stop", "two", "say")))
    assert gate.filter(bytes(30*32000), words) == ()
    assert counts[-1]["unanchored_window_dropped_words"] == 3


def test_saved_mic_words_keep_todays_behaviour_once_the_meeting_had_local_speech():
    # A live window with a 2.4 s local run proves local speech; a later lone backchannel
    # in the saved pass (or a Stop tail) stays, as before this rule.
    counts = []
    gate = _passing_microphone_gate(counts)
    sentence = tuple(GeminiWord(ch, "spk:0", 16000 + i*3200, 16000 + (i+1)*3200)
                     for i, ch in enumerate("我觉得这个方案可以先上线"))
    assert gate.filter(bytes(30*32000), sentence) == sentence
    word = (GeminiWord("Yeah.", "spk:0", 16000, 24000),)
    assert gate.filter_terminal(bytes(32000), word, ()) == word
    assert gate.lane_withheld_words == 0
    assert "unanchored_lane_withheld_words" not in counts[-1]


def test_saved_mic_words_are_withheld_when_the_meeting_never_had_local_speech():
    # Measured listen-only speaker lanes: whole-lane saved words of echo residue and room
    # noise whose longest attributed run is under 2 s.
    counts = []
    gate = _passing_microphone_gate(counts)
    noise = (GeminiWord("¿Ya?", "spk:0", 48000, 49600),
             GeminiWord("stop", "spk:0", 160000, 163200),
             GeminiWord("two", "spk:0", 172800, 176000),
             GeminiWord("say", "spk:0", 185600, 188800),
             GeminiWord("这。", "spk:1", 320000, 321600))
    assert gate.filter_terminal(bytes(30*32000), noise, ()) == ()
    assert gate.lane_withheld_words == 5
    assert counts[-1]["unanchored_lane_withheld_words"] == 5


def test_saved_pass_keeps_every_mic_word_when_its_own_words_show_local_speech():
    # No live window was anchored (e.g. cleanup ran over a meeting whose live view lagged):
    # one 2 s run anywhere in the saved lane keeps all of its words, short ones included.
    gate = _passing_microphone_gate([])
    turn = tuple(GeminiWord(text, "spk:0", 16000 + i*8000, 16000 + (i+1)*8000)
                 for i, text in enumerate(("we", "should", "ship", "it", "today")))
    later = (GeminiWord("OK.", "spk:0", 400000, 404800),)
    assert gate.filter_terminal(bytes(30*32000), turn + later, ()) == turn + later
    assert gate.local_speech_seen and gate.lane_withheld_words == 0


def test_terminal_microphone_voice_check_uses_diarized_words():
    class PassVoice:
        def filter(self, pcm, words, *, offset_sample=0): return tuple(words)
    def embed(pcm, start, words):
        return {label: ((1., 0.) if label in {"A", "echo"} else (0., 1.), 3.)
                for label in {word.speaker for word in words}}
    counts = []
    gate = MicrophoneWordGate(
        PassVoice(), SystemWordLedger(), report_drops=counts.append,
        voice_guard=CrossLaneVoiceEchoGuard(threshold=.60), embedding_source=embed)
    system = (GeminiWord("remote", "A", 0, 16000),)
    mic = (GeminiWord("different", "echo", 0, 8000),
           GeminiWord("local", "C", 0, 32000))
    assert gate.filter_terminal(bytes(32000), mic, system,
                                system_pcm16=bytes(32000)) == (mic[1],)
    assert counts[0]["mic_echo_dropped_by_voice"] == 1


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
    lazy = VoicedLiveWords(Source, voiced_audio=lambda pcm: any(pcm))
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
