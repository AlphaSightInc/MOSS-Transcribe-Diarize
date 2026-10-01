"""R5-F1 T4 fixture ($0): a ~3.3 min synthetic Mandarin meeting lane (throwaway).

    PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python \
        prototypes/gemini-live/mic-speaker-echo/f1/build_zh.py

macOS `say` voices only (Tingting zh_CN, Meijia zh_TW); the text is written for this prototype. It
holds what a real Mandarin meeting holds and the 19 s recorded passage does not: turns longer than
two commit strides, short replies, a speaker who repeats himself (对对对 / 好的好的), sentences that open
with the same words (我们的这个...), a repeated name, digits and Latin names.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent)]
import build as r5d  # noqa: E402  (say(), rms(), db(); importing builds nothing)

RATE = 16000
OUT = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72/f1/fixtures"
A, B = "Tingting", "Meijia"
# (voice, pause before in seconds, text)
SCRIPT = [
    (A, 0.5, "大家好，今天我们主要讨论一下第三季度的产品规划，首先我来介绍一下目前的进展，整体上还是按照计划在走，"
             "移动端的新版本已经提交审核了，预计下周可以发布，不过有一个风险，就是第三方支付的接口还没有完全对接好，"
             "我们的工程师上周跟对方的技术团队开了两次视频会议，对方说他们的测试环境要到月底才能准备好，"
             "所以我们现在的方案是先用模拟数据把整个流程跑通，等对方的环境准备好以后再做一次完整的联调，"
             "这样的话上线时间大概会比原来的计划晚一个星期左右，我觉得这个风险是可以接受的。"),
    (B, 0.6, "对对对，我同意这个安排。"),
    (B, 0.4, "那预算方面呢，今年的预算大概还剩多少？"),
    (A, 0.7, "今年的预算大概还剩30万左右，其中12万已经分配给 Google Cloud 的服务器费用，"
             "剩下的18万我们打算用在市场推广上面，主要是跟 Microsoft 的合作项目。"),
    (B, 1.2, "我们的这个推广方案我看过了，写得很详细。我们的这个时间安排可能有一点紧张。"
             "我们的这个团队现在只有5个人，要同时做3个项目，我担心大家的精力不够。"),
    (A, 0.5, "好的好的，这个问题我也考虑过。"),
    (A, 0.3, "王小明，王小明你来讲一下人员方面的安排吧。"),
    (B, 0.9, "好的，没问题。人员方面我们计划在下个月再招两位工程师，一位负责后端的接口开发，另一位负责数据分析，"
             "面试已经在进行了，上周一共面试了8位候选人，其中有3位我们觉得比较合适，"
             "他们都有 Python 和 TensorFlow 的项目经验，有一位之前还在 OpenAI 实习过，"
             "如果一切顺利的话，月底之前就可以发出录用通知，新同事大概在下个月中旬入职，"
             "入职以后先安排两个星期的培训，然后再分配到具体的项目组里面去。"),
    (A, 0.8, "嗯，好。"),
    (B, 0.7, "另外我想问一下，测试的覆盖率现在是多少？"),
    (A, 0.6, "单元测试的覆盖率是百分之八十五，集成测试的覆盖率大概是百分之六十，"
             "我们的目标是年底之前都提高到百分之九十以上。"),
    (A, 0.6, "那我们最后再确认一下时间。下周三之前，移动端的新版本要完成发布。下周五之前，推广方案要定稿。"
             "月底之前，要完成跟第三方支付的联调。大家还有没有别的问题？"),
    (B, 1.0, "没有了，谢谢大家。"),
    (A, 0.5, "好，那今天的会议就到这里，辛苦各位了。"),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rate = int(sys.argv[1]) if len(sys.argv) > 1 else 166
    pieces, turns, at = [], [], 0.0
    for voice, pause, text in SCRIPT:
        x = r5d.say(text, voice, rate)
        x = x * (10 ** (-17 / 20) / max(r5d.rms(x), 1e-9))
        pieces.append(np.zeros(r5d.n(pause)))
        at += pause
        turns.append({"voice": voice, "start": round(at, 2), "end": round(at + len(x) / RATE, 2), "text": text})
        pieces.append(x)
        at += len(x) / RATE
    pieces.append(np.zeros(r5d.n(2.0)))
    lane = np.clip(np.concatenate(pieces), -1, 1)
    pcm = (lane * 32767).astype(np.int16)
    sf.write(str(OUT / "zh-long.wav"), pcm, RATE, subtype="PCM_16")
    manifest = {"file": "zh-long.wav", "seconds": round(len(pcm) / RATE, 2), "say_rate": rate, "voices": [A, B],
                "rms_dbfs": round(r5d.db(r5d.rms(lane)), 1), "sha256": hashlib.sha256(pcm.tobytes()).hexdigest(),
                "characters": sum(len(t[2]) for t in SCRIPT), "turns": turns,
                "source": "macOS say (synthetic speech), text written for this prototype; no human recording"}
    (OUT / "zh-long.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({k: v for k, v in manifest.items() if k != "turns"}, ensure_ascii=False))
    for turn in turns:
        print(f"  {turn['start']:6.1f}-{turn['end']:6.1f} {turn['voice']:9} {len(turn['text']):3} chars")


main()
