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
        GeminiSegment(2*16000, 3*16000, "the far end keeps talking", source_lane="system"),)))
    engine._on_update("microphone", GeminiPreview(10*16000, (
        GeminiSegment(4*16000, 5*16000, "local words", source_lane="microphone"),)))
    for second in range(46):
        engine.push_lanes(second*16000,
            (("system", bytes(32000)), ("microphone", bytes(32000))))
    degraded = [row for row in updates if isinstance(row, GeminiBase) and row.degraded]
    assert len(degraded) == 1
    assert [(row.text, row.source_lane, row.speaker) for row in degraded[0].segments] == [
        ("the far end keeps talking", "system", None), ("local words", "microphone", None)]
    engine.close()


def _preview_composer(tmp_path):
    updates = []
    class IdleLane:
        def __init__(self, publish): self.publish = publish
        def push_audio(self, start_sample, pcm16): pass
        def close(self): pass
    engine = LaneGeminiEngine(updates.append, system_factory=IdleLane,
                              microphone_factory=IdleLane, tape_root=tmp_path)
    def shown(lane="microphone"):
        previews = [u for u in updates if isinstance(u, GeminiPreview)]
        return [row.text for row in previews[-1].segments if row.source_lane == lane]
    return engine, shown


def test_mic_preview_drops_speaker_echo_of_committed_system_speech(tmp_path):
    # r4 smoke S5: under speaker echo one W3 mic turn grew to ~400 words; its row is clipped
    # to the mic frontier while the system preview only holds the uncommitted suffix, so the
    # old preview-only test showed the far end twice. Committed system words are compared too.
    engine, shown = _preview_composer(tmp_path)
    sec = lambda value: round(value * 16000)
    committed = ("After researching NVIDIA for something like 500 hours over the last two years, "
                 "we flew down to NVIDIA headquarters to sit down with Jensen himself.")
    engine._on_update("system", GeminiRolling(0, sec(90), (
        GeminiSegment(sec(50), sec(80), committed, "speaker-0001", "system"),), ()))
    engine._on_update("system", GeminiPreview(sec(100), (
        GeminiSegment(sec(90), sec(99), "And Jensen, of course, is the founder and CEO of NVIDIA.",
                      source_lane="system"),)))
    mic_turn = ("After researching NVIDIA for something like 500 hours over the last two years, we "
                "flew down to NVIDIA headquarters to sit down with Jensen himself. Deference to "
                "authority is not blind submission. And Jensen, of course, is the founder and CEO of NVIDIA.")
    engine._on_update("microphone", GeminiPreview(sec(100), (
        GeminiSegment(sec(90), sec(100), mic_turn, source_lane="microphone"),)))
    assert shown() == ["Deference to authority is not blind submission"]
    engine.close()


def test_mic_preview_echo_in_chinese_keeps_local_speech_and_short_shared_words(tmp_path):
    engine, shown = _preview_composer(tmp_path)
    sec = lambda value: round(value * 16000)
    remote = "首先我来介绍一下目前的进展，整体上还是按照计划在走。"
    engine._on_update("system", GeminiRolling(0, sec(30), (
        GeminiSegment(sec(20), sec(28), remote, "speaker-0001", "system"),), ()))
    engine._on_update("microphone", GeminiPreview(sec(32), (
        GeminiSegment(sec(30), sec(32), remote + "我觉得这个方案可以先上线。", source_lane="microphone"),)))
    assert shown() == ["我觉得这个方案可以先上线"]
    # Four shared characters (目前的进) are ordinary language, not echo: the row stays whole.
    local = "我们目前的进度有点慢，需要再加两个人。"
    engine._on_update("microphone", GeminiPreview(sec(32), (
        GeminiSegment(sec(30), sec(32), local, source_lane="microphone"),)))
    assert shown() == [local]
    engine.close()


def test_mic_preview_without_echo_is_unchanged_and_echo_row_drops_own_committed_words(tmp_path):
    engine, shown = _preview_composer(tmp_path)
    sec = lambda value: round(value * 16000)
    remote = "so we want to wind the clock all the way back to nineteen ninety seven"
    engine._on_update("system", GeminiRolling(0, sec(60), (
        GeminiSegment(sec(40), sec(55), remote, "speaker-0001", "system"),), ()))
    engine._on_update("microphone", GeminiRolling(0, sec(60), (
        GeminiSegment(sec(50), sec(53), "in exchange for some deference", "local-0001", "microphone"),), ()))
    own = "We should ship the beta to the pilot customers next week."
    engine._on_update("microphone", GeminiPreview(sec(64), (
        GeminiSegment(sec(60), sec(64), own, source_lane="microphone"),)))
    assert shown() == [own]
    # A W3 turn that held echo and the local phrase committed above: nothing new to show.
    engine._on_update("microphone", GeminiPreview(sec(64), (
        GeminiSegment(sec(60), sec(64), remote + " in exchange for some differenceMV", source_lane="microphone"),)))
    assert shown() == []
    engine.close()


def test_mic_preview_echo_is_found_when_the_far_end_repeats_itself(tmp_path):
    # Two-voice Mandarin echo replay at 221 s (reduced): the far end repeats sentences it said
    # 140 s earlier, and its own preview lags, so the echoed row holds [passage only in the
    # preview] then [passage only in the earlier committed rows]. One in-order alignment could
    # match just one of them (72 of 228 units); each run is now matched wherever it occurs.
    engine, shown = _preview_composer(tmp_path)
    sec = lambda value: round(value * 16000)
    engine._on_update("system", GeminiRolling(0, sec(210), (
        GeminiSegment(sec(164), sec(170), "这些问题我会整理成一个清单，会后发给相关负责人。", "speaker-0001", "system"),
        GeminiSegment(sec(170), sec(176), "客户满意度调查的结果比上次好了一些，但是还有提升空间。", "speaker-0001", "system")), ()))
    engine._on_update("microphone", GeminiRolling(0, sec(210), (), ()))
    engine._on_update("system", GeminiPreview(sec(221), (
        GeminiSegment(sec(210), sec(221), "预算方面, 我们今年还剩下大概 30万左右可以使用。 我想听听 大家的意见, 看看 优先级应该怎么排。",
                      source_lane="system"),)))
    engine._on_update("microphone", GeminiPreview(sec(221), (
        GeminiSegment(sec(210), sec(221), "代码 review 的时候我 发现有几个地方没有写 单元测试。 我们今年还剩大概 30 万 左右可以使用。 "
                      "我想听听大家的 意见，看看优先级应该 怎么排。这些 问题我会整理成一个 清单，会后发给 相关负责人。 "
                      "客户满意度调查的结果 比上次好了一些", source_lane="microphone"),)))
    assert shown() == ["代码 review 的时候我 发现有几个地方没有写 单元测试"]
    engine.close()


def test_mic_preview_hides_short_words_in_a_script_the_meeting_has_not_used(tmp_path):
    # P69 run c: in a Mandarin meeting the grey mic preview showed "さんね。" and "क्या?".
    engine, shown = _preview_composer(tmp_path)
    sec = lambda value: round(value * 16000)
    engine._on_update("system", GeminiRolling(0, sec(30), (
        GeminiSegment(sec(10), sec(28), "大家好，今天我们主要讨论一下第三季度的产品规划。", "speaker-0001", "system"),), ()))
    engine._on_update("microphone", GeminiRolling(0, sec(30), (), ()))
    def mic(text):
        engine._on_update("microphone", GeminiPreview(sec(34), (
            GeminiSegment(sec(30), sec(34), text, source_lane="microphone"),)))
        return shown()
    assert mic("さんね。") == []
    assert mic("Wait. क्या? 好的。") == ["好的。"]
    # A short reply in the meeting's own script, and an English term inside a real sentence, stay.
    assert mic("对，没问题。") == ["对，没问题。"]
    sentence = "我觉得这个方案可以，但是我们需要先把 API 的 latency 测一下。"
    assert mic(sentence) == [sentence]
    engine.close()


def test_new_language_shows_once_sustained_and_short_replies_follow(tmp_path):
    # A real switch: the first short reply waits for its commit; four words (seven CJK
    # characters) in one preview row establish the script for the rest of the meeting.
    engine, shown = _preview_composer(tmp_path)
    sec = lambda value: round(value * 16000)
    engine._on_update("system", GeminiPreview(sec(8), (
        GeminiSegment(0, sec(8), "So we want to start with story time today.", source_lane="system"),)))
    def mic(text):
        engine._on_update("microphone", GeminiPreview(sec(9), (
            GeminiSegment(sec(6), sec(9), text, source_lane="microphone"),)))
        return shown()
    assert mic("Sounds good.") == ["Sounds good."]
    assert mic("好的。") == []
    assert mic("其实用户反馈最多的就是登录太慢。") == ["其实用户反馈最多的就是登录太慢。"]
    assert mic("好的。") == ["好的。"]
    engine.close()


def test_committed_words_establish_a_script_only_in_bulk(tmp_path):
    engine, shown = _preview_composer(tmp_path)
    sec = lambda value: round(value * 16000)
    # One stray committed token (the saved "кве" shape) does not make Cyrillic the meeting's script.
    engine._on_update("system", GeminiRolling(0, sec(15), (
        GeminiSegment(sec(1), sec(14), "运维团队反 кве 说，旧的集群维护成本越来越高了。", "speaker-0001", "system"),), ()))
    engine._on_update("microphone", GeminiRolling(0, sec(15), (), ()))
    engine._on_update("microphone", GeminiPreview(sec(18), (
        GeminiSegment(sec(15), sec(18), "Спасибо.", source_lane="microphone"),)))
    assert shown() == []
    engine._on_update("microphone", GeminiRolling(sec(15), sec(30), (
        GeminiSegment(sec(16), sec(20), "Спасибо большое за вашу помощь", "local-0001", "microphone"),), ()))
    engine._on_update("system", GeminiRolling(sec(15), sec(30), (), ()))
    engine._on_update("microphone", GeminiPreview(sec(33), (
        GeminiSegment(sec(30), sec(33), "Спасибо.", source_lane="microphone"),)))
    assert shown() == ["Спасибо."]
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


class _LocalVad:
    def is_speech(self, pcm, rate):
        import numpy as np
        return bool(np.abs(np.frombuffer(pcm, dtype='<i2')).max(initial=0) >= 50)


def _local_fixture(bursts=((8, 9.1),), *, echo=10, seconds=30):
    import numpy as np
    system = np.full(round(seconds*16000), 1000, dtype='<i2')
    mic = np.full_like(system, echo)
    for start, end in bursts:
        mic[round(start*16000):round(end*16000)] += 100
    return mic.tobytes(), system.tobytes()


def _local_gate(system, counts, tab_words=()):
    from moss_transcribe_diarize.app.gemini_lane_engine import LocalVoiceEvidence
    class PassVoice:
        def filter(self, pcm, words, **kwargs): return tuple(words)
    ledger = SystemWordLedger()
    ledger.observe(tab_words, len(system)//2)
    read = lambda a, b: system[a*2:b*2]
    class PassEchoVoice:
        def filter_mic(self, words, vectors, **kwargs): return tuple(words)
        def filter_terminal(self, words, *args): return tuple(words)
    return MicrophoneWordGate(PassVoice(), ledger, AcousticEchoGuard(read, vad=_LocalVad()),
                              counts.append, voice_guard=PassEchoVoice(),
                              embedding_source=lambda *args: {},
                              local_voice=LocalVoiceEvidence(read, vad_factory=_LocalVad))


def _local_phrase(text='Can you elaborate on that?', start=8.4, end=9.2, label='local'):
    tokens = text.split()
    step = (end-start)/len(tokens)
    return tuple(GeminiWord(t, label, round((start+i*step)*16000),
                            round((start+(i+1)*step)*16000)) for i, t in enumerate(tokens))


def test_local_voice_frames_use_the_measured_echo_return_not_a_fixed_level():
    mic, system = _local_fixture((), echo=316)
    gate = _local_gate(system, [])
    assert gate.local_voice.local_words(mic, _local_phrase()) == {}
    assert gate.local_voice.sustained_seconds == 0
    mic, system = _local_fixture()
    gate = _local_gate(system, [])
    assert len(gate.local_voice.local_words(mic, _local_phrase())) == 5
    assert gate.local_voice.sustained_seconds >= .4


def test_short_local_phrase_with_no_two_second_span_is_published_live():
    mic, system = _local_fixture()
    counts = []
    gate = _local_gate(system, counts)
    echo = _local_phrase(' '.join(['remote']*29), 3, 15, 'echo')
    local = _local_phrase()
    assert gate.filter(mic, echo+local) == local
    assert not gate.local_speech_seen
    assert counts[-1]['mic_words_kept_unanchored_by_local_voice'] == 5
    assert 'unanchored_window_dropped_words' not in counts[-1]


def test_listen_only_echo_window_publishes_nothing_with_local_voice_enabled():
    mic, system = _local_fixture((), echo=56)
    counts = []
    gate = _local_gate(system, counts)
    assert gate.filter(mic, _local_phrase(' '.join(['remote']*63), 3, 15)) == ()
    assert counts[-1]['acoustic_gate_dropped_words'] == 63


def test_words_on_a_noise_event_are_not_local_speech():
    mic, system = _local_fixture(((8, 8.6),))
    for text in ('Think about', '后 一 个。'):
        gate = _local_gate(system, [])
        assert gate.filter(mic, _local_phrase(text, 8, 8.6)) == ()


def test_residue_fragments_are_not_a_sustained_stretch():
    mic, system = _local_fixture(((8, 8.2), (8.7, 8.9), (9.4, 9.6)))
    gate = _local_gate(system, [])
    assert gate.filter(mic, _local_phrase('Oh about the words', 8, 9.6)) == ()
    assert gate.local_voice.sustained_seconds == 0


def test_echoed_voice_overlapping_local_speech_is_not_rescued():
    mic, system = _local_fixture(echo=56)
    counts = []
    gate = _local_gate(system, counts)
    assert gate.filter(mic, _local_phrase(' '.join(['remote']*31), 3, 15)) == ()
    assert counts[-1]['acoustic_gate_dropped_words'] == 31
    assert counts[-1]['mic_words_kept_by_local_voice_level'] == 0


def test_quiet_local_turn_under_the_tab_passes_the_level_gate():
    mic, system = _local_fixture(((6, 12.1),))
    counts = []
    gate = _local_gate(system, counts)
    words = _local_phrase(' '.join(['local']*24), 6.2, 12)
    assert gate.filter(mic, words) == words
    assert gate.local_speech_seen
    assert counts[-1]['mic_words_kept_by_local_voice_level'] == 24


def test_local_words_lose_only_echo_phrases_to_the_text_guard():
    mic, system = _local_fixture()
    words = _local_phrase('好 的， 没 问 题。')
    gate = _local_gate(system, [], _local_phrase('的', 8.5, 8.6, 'remote'))
    assert gate.filter(mic, words) == words
    gate = _local_gate(system, [], _local_phrase('没 问', 8.7, 9, 'remote'))
    assert gate.filter(mic, words) == ()


def test_saved_pass_keeps_local_runs_without_opening_the_lane():
    mic, system = _local_fixture(((8, 9.1), (23, 24.1), (38, 39.1)), seconds=45)
    counts = []
    gate = _local_gate(system, counts)
    words = sum((_local_phrase(start=s+.4, end=s+1.2) for s in (8, 23, 38)), ())
    assert gate.filter_terminal(mic, words+_local_phrase('No.', 42, 42.1), (), system_pcm16=system) == words
    # Stray outside voice is dropped by the level gate; a voiced one is withheld by the run bar.
    mic, system = _local_fixture(((8, 9.1), (23, 24.1), (38, 39.1), (42, 42.6)), seconds=45)
    gate = _local_gate(system, [])
    class PassLevel:
        def filter(self, pcm, words, **kwargs): return tuple(words)
    gate.acoustic_gate = PassLevel()
    assert gate.filter_terminal(mic, words+_local_phrase('No.', 42, 42.1), (), system_pcm16=system) == words
    assert gate.lane_withheld_words == 1
    assert not gate.local_speech_seen


def test_one_and_two_word_replies_stay_withheld_without_other_evidence():
    mic, system = _local_fixture()
    for text in ('Yeah.', 'Thanks everyone.'):
        gate = _local_gate(system, [])
        class PassLevel:
            def filter(self, pcm, words, **kwargs): return tuple(words)
        gate.acoustic_gate = PassLevel()
        assert gate.filter(mic, _local_phrase(text)) == ()


def test_saved_pass_and_live_window_judge_the_same_stretch_alike():
    mic, system = _local_fixture()
    live, saved = _local_gate(system, []), _local_gate(system, [])
    words = _local_phrase()
    assert live.filter(mic, words) == saved.filter_terminal(mic, words, (), system_pcm16=system) == words


def test_local_run_interface_judges_restore_candidate_on_its_own():
    mic, system = _local_fixture()
    gate = _local_gate(system, [])
    gate.local_speech_seen = True
    assert gate.local_voice.is_local_run(mic, _local_phrase(), whole_lane=True)
    assert not gate.local_voice.is_local_run(mic, _local_phrase('invented stray words', 20, 20.8), whole_lane=True)
    assert not gate.local_voice.is_local_run(mic, _local_phrase('No.'), whole_lane=True)
    echo = _local_phrase(' '.join(['remote']*31), 3, 15, 'echo')
    assert not gate.local_voice.is_local_run(mic, echo+_local_phrase(), whole_lane=True)


def test_saved_local_run_keeps_sustained_audio_across_context_boundary():
    # The word pad reaches a stretch mostly in the preceding 15 s context.
    mic, system = _local_fixture(((14.5, 15.1),), seconds=45)
    gate = _local_gate(system, [])
    words = _local_phrase(start=15.25, end=15.3)
    assert len(gate.local_voice.local_words(mic, words, whole_lane=True)) == 5
