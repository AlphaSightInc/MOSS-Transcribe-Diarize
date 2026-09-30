"""Locally generated (macOS `say`) Mandarin / code-switched speech with known text (throwaway)."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "tts"

ZH = [
    "我觉得这个方案可以，但是我们需要先把 API 的 latency 测一下。",
    "对，上周的 sprint review 里面我们已经讨论过这个问题了。",
    "好的，那我先把 deadline 定在下周五，大家有问题吗？",
    "这个 feature 的优先级比较高，我们下个版本一定要上线。",
    "我这边没有问题，可以按照这个 timeline 来推进。",
    "你能不能把那个 dashboard 的链接发到群里？",
    "其实用户反馈最多的就是登录太慢，这个要优先解决。",
    "我们今天就先到这里，会后我把 meeting notes 发给大家。",
    "嗯，我同意，不过预算这块还需要跟财务再确认一下。",
    "这个数据看起来有点奇怪，是不是 pipeline 哪里出错了？",
    "谢谢，我补充一点，客户那边希望月底之前能看到 demo。",
    "行，那就这么定了，我会跟进后面的测试。",
]


def say(text: str, voice: str, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    wav = OUT / f"{name}.wav"
    if not wav.exists():
        with tempfile.TemporaryDirectory() as tmp:
            aiff = Path(tmp) / "x.aiff"
            subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True)
            x, sr = sf.read(str(aiff), dtype="float32")
            if x.ndim > 1:
                x = x.mean(axis=1)
            y = resample_poly(x, 16000, sr) if sr != 16000 else x
            sf.write(str(wav), y.astype(np.float32), 16000, subtype="PCM_16")
    return wav


def load(path: Path) -> np.ndarray:
    x, sr = sf.read(str(path), dtype="float32")
    assert sr == 16000
    return x.astype(np.float64)


def zh_sentences(voice: str = "Tingting") -> list[tuple[str, np.ndarray]]:
    return [(text, load(say(text, voice, f"{voice}-{i:02d}"))) for i, text in enumerate(ZH)]

ZH_LOCAL_MORE = [
    "上个季度的收入增长了百分之十二，主要是海外市场带动的。",
    "我建议我们先做一个小范围的 A/B test，看看转化率有没有提升。",
    "服务器那边昨天晚上又报警了，CPU 一直在百分之九十以上。",
    "这个需求我觉得还不够清楚，能不能再写一个详细一点的文档？",
    "我们组下周要去客户那边做培训，大概需要两天时间。",
    "新的设计稿我已经看过了，整体风格不错，就是按钮有点小。",
    "关于招聘的事情，我们这个月还需要再招两个后端工程师。",
    "代码 review 的时候我发现有几个地方没有写单元测试。",
    "如果这个接口改了，前端那边也要同步修改，不然会报错。",
    "我先分享一下屏幕，大家看一下这个图表的趋势。",
    "这个问题我们上次开会也提过，但是一直没有人负责跟进。",
    "我觉得可以先上线一个简单的版本，然后根据反馈再迭代。",
]

ZH_SYSTEM = [
    "大家好，今天我们主要讨论一下第三季度的产品规划。",
    "首先我来介绍一下目前的进展，整体上还是按照计划在走。",
    "移动端的新版本已经提交审核了，预计下周可以发布。",
    "不过有一个风险，就是第三方支付的接口还没有完全对接好。",
    "市场部那边希望我们能配合做一次线上的推广活动。",
    "预算方面，我们今年还剩下大概三十万左右可以使用。",
    "我想听听大家的意见，看看优先级应该怎么排。",
    "另外，数据平台的迁移工作也要在九月底之前完成。",
    "运维团队反馈说，旧的集群维护成本越来越高了。",
    "所以我们考虑把一部分服务迁移到云上，这样更灵活一些。",
    "安全审计的报告也出来了，有几个中等风险需要修复。",
    "这些问题我会整理成一个清单，会后发给相关负责人。",
    "客户满意度调查的结果比上次好了一些，但是还有提升空间。",
    "特别是售后响应速度，很多用户觉得等待时间太长。",
    "我们计划增加一个智能客服的功能，先处理常见的问题。",
    "技术方案我们已经初步评估过了，用现有的模型就可以实现。",
    "时间上大概需要六到八周，包括测试和上线。",
    "如果大家没有其他问题，我们就进入下一个议题。",
    "下一个议题是关于团队协作工具的选择。",
    "现在大家用的工具太多了，信息很分散，找东西很麻烦。",
    "我们希望能统一到一个平台上，提高沟通效率。",
    "具体选哪一个，我们会做一个对比，然后再投票决定。",
    "最后提醒一下，下周三下午有全员大会，请大家准时参加。",
    "好，今天的会就先开到这里，谢谢大家。",
]

ZH_BACKCHANNEL = ["嗯。", "对。", "好的。", "是的。", "没问题。", "对对对。", "可以。", "明白。", "行。", "OK。"]
EN_BACKCHANNEL = ["Yeah.", "Right.", "Okay.", "Exactly.", "Sure.", "Got it.", "Makes sense.", "Totally.", "Yes.", "Uh-huh."]


def utterances(texts: list[str], voice: str, tag: str) -> list[tuple[str, np.ndarray]]:
    return [(text, load(say(text, voice, f"{voice}-{tag}-{i:02d}"))) for i, text in enumerate(texts)]
