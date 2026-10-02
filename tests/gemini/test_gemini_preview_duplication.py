"""J8: the preview never re-shows words the reader already sees in the same lane.

Texts are from recorded gemini-3.5-transcribe-live (W3) streams replayed at $0
(round-3 diagnosis): long W3 chunks restart 40-100 words before the committed frontier,
and an interim often restates the final before it.
"""
import hashlib

import pytest

from moss_transcribe_diarize.app.gemini_live_runtime import (
    GeminiBase, GeminiLiveRuntime, GeminiPreview, GeminiRolling, GeminiSegment, ScriptedGeminiEngine)
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds, LiveServiceConfigHashes, LiveServiceDescriptor)
from moss_transcribe_diarize.app.live_session import AudioFrame

R = 16000


def _runtime(tmp_path, seconds=60, lanes=False):
    descriptor = LiveServiceDescriptor(
        source_revision="test", provider_name="gemini", provider_revision="phase1-fake",
        provider_manifest_hash=hashlib.sha256(b"gemini").hexdigest(),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={}, identity_config={}, decoder_config={}),
        bounds=LiveServiceBounds(max_frame_samples=16000, max_queue_depth=4,
                                 max_retained_samples=32000, max_identity_speakers=8,
                                 max_events=64, max_tape_bytes=seconds * 32000),
        frame_samples=16000)
    rt = GeminiLiveRuntime(descriptor=descriptor, tape_storage_root=tmp_path,
                           engine_factory=lambda _id, publish, _usage: ScriptedGeminiEngine(
                               publish, batches=(), terminal=()))
    rt.create(session_id="one")
    for second in range(seconds):
        pcm = b"\0" * 32000
        rt.accept_frame("one", AudioFrame(second, pcm, 16000, lane_pcm=(
            (("system", pcm), ("microphone", pcm)) if lanes else ())))
    return rt


def _advance_audio(rt, seconds):
    start = rt.snapshot("one").to_dict()["session"]["accepted_samples"] // R
    for second in range(start, seconds):
        rt.accept_frame("one", AudioFrame(second, b"\0" * 32000, R))


INTRO = "Thank you for subscribing to this channel. And now, dear friends, here's Keyu Jin. "
COMMITTED = (
    INTRO +
    "What is the single biggest misconception the West has about China's economy today? The "
    "biggest misunderstanding is somehow that a group of people or even just one person runs "
    "the entire Chinese economy. It is far from the reality. It is a very complex, large "
    "economy, and even if there is an extreme form of political centralization, the economy is "
    "totally decentralized. The role that the local")
FRESH = ("mayors, I call this the mayor economy, plays in reforms but also driving the "
         "technological innovation that we're seeing right now.")


def _commit(rt, text, through_s=45, lane="system"):
    rt.publish_update("one", GeminiBase(through_s * R, ()))
    rt.publish_update("one", GeminiRolling(0, through_s * R, (
        GeminiSegment(0, through_s * R, text, "speaker-0001", lane),),
        revision_lanes=(lane,)))


def _preview(rt, *texts, now_s=60):
    start = rt.snapshot("one").to_dict()["session"]["committed_samples"]
    rt.publish_update("one", GeminiPreview(now_s * R, tuple(
        GeminiSegment(start + i, now_s * R, text, source_lane="system")
        for i, text in enumerate(texts))))
    return " ".join(s["text"] for s in
                    rt.snapshot("one").to_dict()["session"]["provisional"]["segments"])


def test_preview_trims_committed_head_longer_than_sixty_words(tmp_path):
    rt = _runtime(tmp_path)
    _commit(rt, COMMITTED)
    head = COMMITTED[len(INTRO):]  # 65 committed words repeated by one W3 chunk
    assert _preview(rt, head + " " + FRESH) == FRESH


def test_preview_trims_head_when_frontier_words_differ_between_models(tmp_path):
    # W3 fuses/drops words right at the frontier ("isdecentralized", "Therole", "thelocal").
    rt = _runtime(tmp_path)
    _commit(rt, COMMITTED)
    w3 = (COMMITTED[len(INTRO):].replace("is totally decentralized. The role that the local",
                                         "isdecentralized. Therole that thelocal"))
    shown = _preview(rt, w3 + " " + FRESH)
    assert "single biggest misconception" not in shown
    assert shown.endswith(FRESH)
    assert len(shown.split()) <= len(FRESH.split()) + 4  # at most the fused frontier words


def test_preview_does_not_repeat_a_final_that_the_next_interim_restates(tmp_path):
    rt = _runtime(tmp_path)
    _commit(rt, "Earlier words that are already settled in the transcript.", through_s=10)
    final = ("existence of monopolies concentrated structures and according to traditional "
             "neoclassical economic theory the presence of monopolies is not a good thing.")
    shown = _preview(rt, final, final + " Let's")
    assert shown.count("neoclassical") == 1 and shown.endswith("Let's")


def test_restated_final_keeps_fresh_words_after_a_fused_frontier_word(tmp_path):
    # Recorded (acquired_rolex): the interim fuses "the very" -> "thevery"; the lone "the" of
    # "in the world" is chance, not repetition, and must not take the fresh words with it.
    rt = _runtime(tmp_path)
    _commit(rt, "Over a million people a year actually do buy one, and for an average price of",
            through_s=10)
    final = ("$13,000 each. That is until you walk out of the store and then they instantly "
             "become worth more, at least for a lot of the models these days. To your point "
             "about paradoxes of Rolex, this is one of the greatest ones. It is absolutely one "
             "of the")
    shown = _preview(rt, final, final + "very top top tier luxury brands in the")
    assert shown.count("paradoxes") == 1
    assert shown.endswith("top top tier luxury brands in the")


def test_new_interim_sharing_a_phrase_with_shown_text_is_kept_whole(tmp_path):
    # Recorded (lex_bill_ackman 5 m): the new interim's last five words also occur in the
    # preview kept before it; a match that leaves the head unmatched is not a repeated head.
    rt = _runtime(tmp_path)
    _commit(rt, "And basically, he says that you have to understand the difference between "
                "price and value, right? Price is what you pay, value is what you get.")
    earlier = ("makes you a great offer, you can take it. And that's the stock market. And the "
               "key is to figure out what something's worth, and you have to kind of weigh it.")
    new = "talked about the difference between between the stock market and the"
    assert _preview(rt, earlier, new) == earlier + " " + new


def test_preview_trims_head_when_it_dropped_a_committed_phrase(tmp_path):
    # Recorded (round-3 re-check, E1 at 250 s): the preview heard "Only Murders" where the
    # committed words say "only eight were going to work? We should have I" -- a 9-word gap on
    # the committed side only -- and re-showed 22 committed words.
    rt = _runtime(tmp_path)
    _commit(rt, "And you have to convince the market to buy it, and you got to convince "
                "developers not to use anything but those eight blend modes. Walk us through "
                "what that felt like. The other 24 weren't that important. Okay, so wait, wait. "
                "First question. Was that the plan all along? Like when when did you realize "
                "that only eight were going to work? We should have I realized I didn't learn "
                "about it until it was too")
    fresh = ("late. We should have implemented all 32. Yeah. But But we built what we built "
             "and so we had to make the best of it. That was really an extraordinary time.")
    assert _preview(rt, "the plan all along? When When did you realize that Only MurdersI "
                        "realized I didn't learn about it until it was too " + fresh) == fresh


def test_degraded_commit_keeps_lanes_so_preview_and_rolling_replace_it(tmp_path):
    # R1: preview words committed by the lag fallback carry their capture lane.
    rt = _runtime(tmp_path, lanes=True)
    said = ("Andrew Scull has spent decades studying how societies have understood madness "
            "and its treatment")
    rt.publish_update("one", GeminiBase(20 * R, (
        GeminiSegment(0, 20 * R, said, None, "system"),), degraded=True))
    rows = rt.snapshot("one").to_dict()["session"]["effective_transcript"]
    assert [(row["text"], row["source_lane"]) for row in rows] == [(said, "system")]
    # The same W3 chunk is still in the preview: only its new words are shown.
    rt.publish_update("one", GeminiPreview(25 * R, (GeminiSegment(
        20 * R, 25 * R, said + ". In this conversation we trace", source_lane="system"),)))
    assert [row["text"] for row in
            rt.snapshot("one").to_dict()["session"]["provisional"]["segments"]] == [
        "In this conversation we trace"]
    # Rolling later covers that audio with a named speaker: no unattributed copy remains.
    rt.publish_update("one", GeminiBase(30 * R, ()))
    rt.publish_update("one", GeminiRolling(0, 30 * R, (
        GeminiSegment(0, 20 * R, said, "speaker-0001", "system"),),
        revision_lanes=("system", "microphone")))
    rows = rt.snapshot("one").to_dict()["session"]["effective_transcript"]
    assert [(row["text"], row["canonical_speaker"]) for row in rows] == [(said, "speaker-0001")]


# Captured 188 s Mandarin stream: traditional window at 60 s, then one 50 s turn
# across three frontiers. Text and expected suffixes frozen from F1 arm C.
ZH_FRONTIERS = (
    (60, (
        '大家好，今天我们主要讨论一下第三季度的产品规划。首先我来介绍一下目前的进展，整体上还是按照计划在走，移动端的新版本已经提交审核了。 预计下周可以发布。不过有一个风险，就是第三方支付'
        '的接口还没有完全对接好。我们的工程师上周跟对方的技术团队开了两次视频会议，对方说他们的 测试环境要到月底才能准备好，所以我们现在的方案是先用模拟数据把整个流程跑通，等对方的环境准备'
        '好以后再做一次完整的联调，这样的话上线时间 大概會比原來的計劃晚一個星期左右，我覺得這個風險是可以接受的。 對對對，我同意這個安排。那預算方面呢？今年的預算大概還剩多少？ 今年的預'
    ), (
        '对方的 技术 团队 开了两次 视频 会议, 对方说 他们 的 测试 环境 要到 月底 才能 准备好, 所以 我们 现在 的 方案 是 先 用 模拟 数据 把 整个 流程 跑通, 等'
        ' 对方 的 环境 准备好 以后 再 做 一次 完整 的 联调, 这样 的话 上线 时间 大概 会 比 原来 的 计划 晚 一个 星期 左右, 我 觉得 这个 风险。是可以接受的。对'
        ' 对对对, 我 同意这个安排。那预算 方面呢? 今年的 预算大概还剩多少? 今年的预算大概 还剩 30 万左 右,'
    ), '预算大概 还剩 30 万左 右,'),
    (90, (
        '我们的这个推广方案我看过了，写的很详细，我们的这个时间安排可能有一点紧张，我们的这个团队现在只有五个人，要同时做三个项目，我担心大家的'
    ), (
        '我 们 的 这 个 推 广 方 案 我 看 过 了 , 写 得 很 详 细 。 我 们 的 这 个 时 间 安 排 可 能 有 一 点 紧 张 。 我 们 的 这 个 团 队 现 '
        '在 只 有 五 个 人 , 要 同 时 做 三 个 项 目 , 我 担 心 大 家 的 精 力 不 够 。 好 的 好 的 , 这 个'
    ), '精 力 不 够 。 好 的 好 的 , 这 个'),
    (105, (
        '我们的这个推广方案我看过了，写的很详细，我们的这个时间安排可能有一点紧张，我们的这个团队现在只有五个人，要同时做三个项目，我担心大家的 精力不够。 好的好的，这个问题我也考虑过。王'
        '小明，王小明你来讲一下人员方面的安排吧。 好的，没问题。人员方面我们计划在下个月再招'
    ), (
        '我 们 的 这 个 推 广 方 案 我 看 过 了 , 写 得 很 详 细 。 我 们 的 这 个 时 间 安 排 可 能 有 一 点 紧 张 。 我 们 的 这 个 团 队 现 '
        '在 只 有 五 个 人 , 要 同 时 做 三 个 项 目 , 我 担 心 大 家 的 精 力 不 够 。 好 的 好 的 , 这 个 问 题 我 也 考 虑 过 。 王 小 明 '
        ', 王 小 明 你 来 讲 一 下 人 员 方 面 的 安 排 吧 。好的, 没问题, 人员方面我们计划在下个月再招两位工程师, 一位负责 后端的'
    ), '两位工程师, 一位负责 后端的'),
    (120, (
        '我们的这个推广方案我看过了，写的很详细，我们的这个时间安排可能有一点紧张，我们的这个团队现在只有五个人，要同时做三个项目，我担心大家的 精力不够。 好的好的，这个问题我也考虑过。王'
        '小明，王小明你来讲一下人员方面的安排吧。 好的，没问题。人员方面我们计划在下个月再招 两位工程师，一位负责后端的接口开发，另一位负责数据分析。面试已经在进行了，上周一共面试了八位候'
        '选人，其中有三位我们觉得比较合适，他们都'
    ), (
        '我 们 的 这 个 推 广 方 案 我 看 过 了 , 写 得 很 详 细 。 我 们 的 这 个 时 间 安 排 可 能 有 一 点 紧 张 。 我 们 的 这 个 团 队 现 '
        '在 只 有 五 个 人 , 要 同 时 做 三 个 项 目 , 我 担 心 大 家 的 精 力 不 够 。 好 的 好 的 , 这 个 问 题 我 也 考 虑 过 。 王 小 明 '
        ', 王 小 明 你 来 讲 一 下 人 员 方 面 的 安 排 吧 。好的, 没问题, 人员方面我们计划在下个月再招两位工程师, 一位负责后端的接口开发,另一位负责数据分析, 面试'
        '已经在进行了, 上周一共面试了八位候选人, 其中有三位我们觉得比较合适, 他们都有 Python 和 TensorFlow 的项目'
    ), '有 Python 和 TensorFlow 的项目'),
)

ZH_RESTATED_SOLID = (
    '大家好，今天我们主要讨论一下第三季度的产品规划。首先我来介绍一下目前的进展，整体上还是按照计划在走，移动端的新版本已经提交审核了。 预计下周可以发布。不过有一个风险，就是第三方支付'
    '的接口还没有完全对接好。我们的工程师上周跟对方的技术团队开了两次视频会议，对方说他们的 测试环境要到月底才能准备好，所以我们现在的方案是先用模拟数据把整个流程跑通，等对方的环境准备'
    '好以后再做一次完整的联调，这样的话上线时间 大概會比原來的計劃晚一個星期左右，我覺得這個風險是可以接受的。 對對對，我同意這個安排。那預算方面呢？今年的預算大概還剩多少？ 今年的預'
)
ZH_RESTATED_FINAL = (
    '对方的技术团队开了两次视频会议，对方说他们的测试环境要到月底才能准备好，所以我们现在的方案是先用模拟数据把整个流程跑通，等对方的环境准备好以后再做一次完整的联调，这样的话上线时间大'
    '概会比原来的计划晚一个星期左右，我觉得这个风险是可以接受的。对对对，我同意这个安排。那预算方面呢？今年的预算大概还剩多少？今年的预算大概还剩30万左右，其中12万已经分配给Goog'
    'le Cloud的服务器费用，剩下的18万我'
)
ZH_RESTATED_INTERIM = (
    '是可以接受的。对 对对对, 我 同意这个安排。那预算 方面呢? 今年的 预算大概还剩多少? 今年的预算大概 还剩 30 万左右, 其中 12 万已经 分配给 Google Clou'
    'd 的 服务费费用, 剩下的 18 万打算'
)


ZH_SOLID = (
    "大家好今天我们主要讨论一下第三季度的产品规划。首先我来介绍一下目前的进展整体上还是按照计划在走。"
    "移动端的新版本已经提交审核了")
ZH_FRESH = "预计下周可以发布。不过有一个风险，就是第三方支付的接口还没有完全对接好。"


def test_preview_trims_committed_head_in_chinese(tmp_path):
    rt = _runtime(tmp_path)
    _commit(rt, ZH_SOLID)
    preview = ("大家好，今天我们主要讨论一下第三季度的产品规划。首先我来介绍一下目前的进展，"
               "整体上还是按照计划在走。移动端的新版本已经提交审核了，" + ZH_FRESH)
    assert _preview(rt, preview) == ZH_FRESH


def test_preview_trims_chinese_head_with_latin_names(tmp_path):
    rt = _runtime(tmp_path)
    _commit(rt, "一直在研究这个问提的是麻省理工学院Media Lab的计算机教授Alan Turing。"
                "他研究神经网络的训练方法已经八九年合作者Grace Hopper在Microsoft上班。"
                "Google宣布之前他跟Google的人开了一次视讯会议。这是科技频道Computerphile")
    fresh = "10 月初上架的专访，他从头讲那次会议，也讲学术界为什么开始不愿公开自己的研究问题。"
    preview = ("一直在研究这个问题的是麻省理工学院 Media Lab 的计算机教授 Alan Turing。"
               "他研究神经网络的训练方法已经八九年，合作者 Grace Hopper 在 Microsoft 上班。"
               "Google 宣布之前，他跟 Google 的人开了一次视频会议。这是科技频道 Computerphile " + fresh)
    shown = _preview(rt, preview)
    assert shown == fresh
    assert "Media Lab" not in shown


def test_preview_trims_head_written_with_spaces_between_chinese_words(tmp_path):
    rt = _runtime(tmp_path)
    solid = "对方的技术团队开了两次视频会议，对方说他们的测试环境要到月底才能准备好"
    fresh = "所以我们现在的方案是先用模拟数据把整个流程跑通。"
    _commit(rt, solid)
    assert _preview(rt, "对方的 技术 团队 开了两次 视频 会议, 对方说 他们 的 测试 环境 "
                        "要到 月底 才能 准备好, " + fresh) == fresh


def test_preview_trim_holds_when_committed_window_is_traditional(tmp_path):
    _, solid, preview, expected = ZH_FRONTIERS[0]
    rt = _runtime(tmp_path)
    _commit(rt, solid)
    assert _preview(rt, preview) == expected
    assert expected.startswith("预算")  # at most four solid units remain (预/預 differs)


def test_chinese_turn_crossed_by_three_frontiers_never_reshows(tmp_path):
    from moss_transcribe_diarize.app.gemini_lane_engine import _preview_units

    previous_cut = 0
    for frontier, solid, preview, expected in ZH_FRONTIERS[1:]:
        # Each captured frontier is re-based to this test's audio span; trim is stateless.
        rt = _runtime(tmp_path / str(frontier))
        _commit(rt, solid)
        shown = _preview(rt, preview)
        assert shown == expected
        cut = len(_preview_units(preview)) - len(_preview_units(shown))
        assert cut >= previous_cut
        previous_cut = cut


def test_interim_restating_a_chinese_final_is_shown_once(tmp_path):
    rt = _runtime(tmp_path)
    _commit(rt, ZH_RESTATED_SOLID, through_s=60)
    _advance_audio(rt, 70)
    shown = _preview(rt, ZH_RESTATED_FINAL, ZH_RESTATED_INTERIM, now_s=70)
    assert shown == "预算大概还剩30万左右，其中12万已经分配给Google Cloud的服务器费用，剩下的18万我 打算"
    assert shown.count("Google Cloud") == 1


def test_short_chinese_repetition_is_kept(tmp_path):
    cases = (
        ("这个方案我们下周再讨论。对对对对对对", "对对对对对对，那就这样。"),
        ("下面有请欧阳娜娜老师", "欧阳娜娜老师，请开始。"),
        ("我觉得我们的这个方案是可以的", "我们的这个接口还没有对接好。"),
        ("移动端的新版本已经提交审核了", "提交审核了以后还要等一周。"),
        ("我们需要先把接口的延迟测一下", "接口的延迟测一下再决定上线时间。"),
    )
    for index, (solid, preview) in enumerate(cases):
        rt = _runtime(tmp_path / str(index))
        _commit(rt, solid)
        assert _preview(rt, preview) == preview


def test_nine_character_repeat_is_trimmed_eight_is_not(tmp_path):
    text = "移动端的新版本已经提交审核了"
    for length in (8, 9):
        rt = _runtime(tmp_path / str(length))
        _commit(rt, text[-length:])
        fresh = "以后还要等一周。"
        preview = text[-length:] + "，。；：！？、" + fresh
        assert _preview(rt, preview) == (preview if length == 8 else fresh)


def test_preview_is_trimmed_only_against_its_own_lane(tmp_path):
    said = ZH_SOLID + "，" + ZH_FRESH
    for mine, other in (("microphone", "system"), ("system", "microphone")):
        rt = _runtime(tmp_path / mine, lanes=True)
        _commit(rt, said, lane=other)
        for with_other in (False, True):
            rows = ((GeminiSegment(45 * R, 60 * R, said, source_lane=other),)
                    if with_other else ())
            rt.publish_update("one", GeminiPreview(60 * R, rows + (
                GeminiSegment(45 * R, 60 * R, said, source_lane=mine),)))
            shown = rt.snapshot("one").to_dict()["session"]["provisional"]["segments"]
            assert [row["text"] for row in shown if row["source_lane"] == mine] == [said]


def test_homophones_and_a_different_latin_name_do_not_stop_the_trim(tmp_path):
    cases = (
        ("他跟公司的人开了一次视讯会议讨论这个问提目标是逼近去年的水平",
         "他跟公司的人开了一次视频会议，讨论这个问题，目标是比进去年的水平，然后再看预算。",
         "然后再看预算。"),
        ("这是科技频道Computerphile十月初上架的专访",
         "这是科技频道 Computer File 10 月初上架的专访，他从头讲那次会议。", "他从头讲那次会议。"),
    )
    for index, (solid, preview, fresh) in enumerate(cases):
        rt = _runtime(tmp_path / str(index))
        _commit(rt, solid)
        assert _preview(rt, preview) == fresh


def test_number_words_and_digits_align_in_chinese(tmp_path):
    rt = _runtime(tmp_path)
    _commit(rt, "我们今年的预算大概是30万左右")
    assert _preview(rt, "我们今年的预算大概是三十万左右，明年会增加到五十万。") == "明年会增加到五十万。"


def test_cut_position_with_letters_whose_casefold_is_longer(tmp_path):
    rt = _runtime(tmp_path)
    said = "Die Straße vor dem großen Haus ist außen leider geschlossen"
    _commit(rt, said)
    assert _preview(rt, said + ". Wir fahren herum.") == "Wir fahren herum."


def test_japanese_and_korean_heads(tmp_path):
    cases = (
        ("本日は第三四半期の製品計画について話し合います。まず現在の進捗をご説明しますと",
         "本日は第三四半期の製品計画について話し合います。まず、現在の進捗をご説明しますと、次はリスクです。",
         "次はリスクです。"),
        ("먼저 현재 진행 상황을 설명드리면 전체적으로 계획대로 진행되고 있습니다",
         "먼저 현재 진행상황을 설명 드리면 전체적으로 계획대로 진행되고 있습니다. 모바일 새 버전은 심사에 제출했습니다.",
         "모바일 새 버전은 심사에 제출했습니다."),
    )
    for index, (solid, preview, fresh) in enumerate(cases):
        rt = _runtime(tmp_path / str(index))
        _commit(rt, solid)
        assert _preview(rt, preview) == fresh


def test_units_are_todays_tokens_without_cjk():
    import re
    from moss_transcribe_diarize.app.gemini_lane_engine import _preview_units
    from moss_transcribe_diarize.app.gemini_live_runtime import _PREVIEW_NUMBERS

    for text in ("China's economy today?", "isdecentralized. Therole that thelocal", "x.Y 32 6 six",
                 "$13,000 each. That's the plan", "Only MurdersI realized I didn't learn about it"):
        tokens = [(_PREVIEW_NUMBERS.get(m.group(), m.group()), m.start(), m.end())
                  for m in re.finditer(r"[^\W_\d]+|\d+", text.casefold())]
        assert _preview_units(text) == tokens


# R5B-A2: the stress streams insert >8 preview units / >16 solid units inside
# one continuous turn. Keep a cut already witnessed before that divergence.
A2_GAP = ("two different people are talking over one another and their overlapped words "
          "are returned only in the rolling transcript during this long window")


def _a2_append_commit(rt, text, through_s):
    start = rt.snapshot("one").session.committed_samples
    rt.publish_update("one", GeminiBase(through_s * R, ()))
    rt.publish_update("one", GeminiRolling(start, through_s * R, (
        GeminiSegment(start, through_s * R, text, "speaker-0001", "system"),),
        revision_lanes=("system",)))


def test_preview_remembers_proven_cut_after_a_long_solid_omission(tmp_path):
    rt = _runtime(tmp_path)
    _commit(rt, COMMITTED, through_s=40)
    raw = COMMITTED + " " + FRESH
    assert _preview(rt, raw, now_s=55) == FRESH
    _a2_append_commit(rt, A2_GAP, through_s=50)
    assert _preview(rt, raw, now_s=60) == FRESH


def test_preview_remembers_proven_cut_after_a_long_preview_insertion(tmp_path):
    rt = _runtime(tmp_path)
    _commit(rt, COMMITTED, through_s=40)
    assert _preview(rt, COMMITTED + " " + FRESH, now_s=55) == FRESH
    # A growing turn keeps the same removed prefix, but its later words diverge.
    _a2_append_commit(rt, A2_GAP + " entirely different rolling ending", through_s=50)
    fresh = "Sit me down say it straight another story on the way. " + FRESH
    assert _preview(rt, COMMITTED + " " + fresh, now_s=60) == fresh


def test_proven_preview_cut_does_not_flicker_across_many_frontiers(tmp_path):
    rt = _runtime(tmp_path)
    _commit(rt, COMMITTED, through_s=40)
    assert _preview(rt, COMMITTED + " " + FRESH, now_s=55) == FRESH
    for through in range(50, 500, 15):
        _advance_audio(rt, through + 16)
        _a2_append_commit(rt, A2_GAP, through_s=through)
        fresh = FRESH + " " + "new speech " * (through // 15)
        assert _preview(rt, COMMITTED + " " + fresh, now_s=through + 16) == fresh


def test_degraded_growing_paragraph_commits_only_its_new_suffix(tmp_path):
    rt = _runtime(tmp_path)
    _commit(rt, "earlier settled words", through_s=15)
    paragraph = COMMITTED
    _preview(rt, paragraph, now_s=55)
    for i in range(4):
        raw = paragraph + " " + "fresh extension " * i
        start = (20 + i * 5) * R
        rt.publish_update("one", GeminiBase(start, (
            GeminiSegment((15 + i * 5) * R, start, raw, source_lane="system"),), degraded=True))
    rows = rt.snapshot("one").session.effective_transcript
    assert " ".join(r.text for r in rows).count("single biggest misconception") == 1
    assert " ".join(r.text for r in rows).count("fresh extension") == 3


def test_degraded_single_word_is_committed_once_with_witnessed_extent(tmp_path):
    rt = _runtime(tmp_path, lanes=True)
    _commit(rt, "earlier settled words", through_s=15)
    rt.publish_update("one", GeminiPreview(55 * R, (
        GeminiSegment(15 * R, 55 * R, "Right.", source_lane="microphone"),)))
    for i in range(5):
        rt.publish_update("one", GeminiBase((20 + i * 5) * R, (
            GeminiSegment((15 + i * 5) * R, (20 + i * 5) * R,
                          "Right.", source_lane="microphone"),), degraded=True))
    assert [r.text for r in rt.snapshot("one").session.effective_transcript
            if r.source_lane == "microphone"] == ["Right."]


def test_remembered_cut_preserves_a_new_turn_repeating_the_same_words(tmp_path):
    rt = _runtime(tmp_path)
    _commit(rt, COMMITTED, through_s=40)
    assert _preview(rt, COMMITTED + " " + FRESH, now_s=45) == FRESH
    # The new turn does not overlap the witnessed preview extent. Its words can
    # really repeat the previous sentence, as the c6 microphone fixture does.
    _a2_append_commit(rt, A2_GAP, through_s=50)
    assert _preview(rt, COMMITTED + " " + FRESH, now_s=60) == COMMITTED + " " + FRESH


def test_remembered_cut_resets_when_provider_rewrites_the_prefix(tmp_path):
    rt = _runtime(tmp_path)
    _commit(rt, COMMITTED, through_s=40)
    _preview(rt, COMMITTED + " " + FRESH, now_s=55)
    _a2_append_commit(rt, A2_GAP, through_s=50)
    rewritten = "The provider now starts this turn with a completely different explanation. " + FRESH
    assert _preview(rt, rewritten, now_s=60) == rewritten


def test_remembered_cut_is_isolated_by_lane_and_cleared_with_preview(tmp_path):
    rt = _runtime(tmp_path, lanes=True)
    _commit(rt, COMMITTED, through_s=40)
    _preview(rt, COMMITTED + " " + FRESH, now_s=55)
    rt.publish_update("one", GeminiPreview(60 * R, (
        GeminiSegment(40 * R, 60 * R, COMMITTED + " " + FRESH, source_lane="microphone"),)))
    assert rt.snapshot("one").session.provisional.segments[0]["text"] == COMMITTED + " " + FRESH
    rt.publish_update("one", GeminiPreview(60 * R, ()))
    assert rt._sessions["one"].preview_cuts == []


def test_remembered_cut_does_not_hide_a_later_repeated_chorus(tmp_path):
    rt = _runtime(tmp_path)
    old = "one settled introduction about the previous meeting then finish with a chorus now"
    _commit(rt, old, through_s=40)
    raw = ("one settled introduction about the previous meeting fresh unrevised speech has never "
           "been committed and this completely different lengthy passage belongs to the new "
           "chorus occurrence today then finish with a chorus now")
    shown = _preview(rt, raw, now_s=55)
    assert "fresh unrevised speech" in shown
    assert shown.endswith("then finish with a chorus now")


@pytest.mark.parametrize("lane", ("system", "microphone"))
@pytest.mark.parametrize("empty", (False, True))
def test_rolling_replacement_forgets_cut_backed_by_removed_solid(tmp_path, lane, empty):
    # R5-F1: fallback solid contains 81 words, rolling keeps only 20 (or none).
    from moss_transcribe_diarize.app.gemini_live_runtime import _trim_committed_preview

    rt = _runtime(tmp_path, lanes=True)
    _commit(rt, "Earlier settled discussion before this long turn", through_s=15, lane=lane)
    _advance_audio(rt, 61)
    rt.publish_update("one", GeminiPreview(55 * R, (
        GeminiSegment(15 * R, 55 * R, COMMITTED, source_lane=lane),)))
    rt.publish_update("one", GeminiBase(21 * R, (
        GeminiSegment(15 * R, 21 * R, COMMITTED, source_lane=lane),), degraded=True))
    assert rt._sessions["one"].preview_cuts[0][2]
    rt.publish_update("one", GeminiBase(30 * R, ()))
    replacement = " ".join(COMMITTED.split()[:20])
    rt.publish_update("one", GeminiRolling(15 * R, 30 * R,
        () if empty else (GeminiSegment(15 * R, 30 * R, replacement, "speaker-0001", lane),),
        revision_lanes=(lane,)))
    raw = COMMITTED + " " + FRESH
    preview = GeminiSegment(30 * R, 60 * R, raw, source_lane=lane)
    expected = _trim_committed_preview((preview,), rt.snapshot("one").session.effective_transcript)
    rt.publish_update("one", GeminiPreview(60 * R, (preview,)))
    shown = rt.snapshot("one").session.provisional.segments[0]["text"]
    assert shown == expected[0].text
    assert len(shown.split()) == (81 if empty else 61) + len(FRESH.split())


def test_stop_clears_remembered_preview_cut(tmp_path):
    import asyncio

    rt = _runtime(tmp_path)
    _commit(rt, COMMITTED, through_s=40)
    assert _preview(rt, COMMITTED + " " + FRESH, now_s=55) == FRESH
    assert rt._sessions["one"].preview_cuts[0][2]
    stopped = asyncio.run(rt.stop("one", 1))
    assert stopped.session.provisional is None
    assert rt._sessions["one"].preview_cuts == []
    rt.create(session_id="two")
    assert rt._sessions["two"].preview_cuts == []


def test_other_lane_rolling_keeps_remembered_cut(tmp_path):
    rt = _runtime(tmp_path, lanes=True)
    _commit(rt, "earlier settled words", through_s=15)
    rt.publish_update("one", GeminiPreview(55 * R, (
        GeminiSegment(15 * R, 55 * R, "Right.", source_lane="microphone"),)))
    rt.publish_update("one", GeminiBase(21 * R, (
        GeminiSegment(15 * R, 21 * R, "Right.", source_lane="microphone"),), degraded=True))
    rt.publish_update("one", GeminiBase(30 * R, ()))
    rt.publish_update("one", GeminiRolling(15 * R, 30 * R, (
        GeminiSegment(15 * R, 30 * R, "independent system discussion", "speaker-0001", "system"),),
        revision_lanes=("system",)))
    rt.publish_update("one", GeminiPreview(60 * R, (
        GeminiSegment(30 * R, 60 * R, "Right. Can you elaborate please?", source_lane="microphone"),)))
    # One word is below stateless evidence; only the retained same-lane proof hides it.
    assert rt.snapshot("one").session.provisional.segments[0]["text"] == "Can you elaborate please?"
