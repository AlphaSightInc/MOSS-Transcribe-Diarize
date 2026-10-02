"""R5-F1 T1 ($0): script cells + adversarial cases at the production publication seam (throwaway).

    PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python \
        prototypes/gemini-live/mic-speaker-echo/f1/s1.py [arm ...]        # default: base A B C

Every case goes through `GeminiLiveRuntime.publish_update` (commit, then preview) with the arm
patched in place of `gemini_live_runtime._trim_committed_preview`. First asserts that R5-D's
unpatched replay prints R5-D's recorded table.
"""
from __future__ import annotations

import contextlib
import io
import json
import runpy
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import trim as arms  # noqa: E402
from trim import runtime  # noqa: E402

EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72"
S = 16000

buffer = io.StringIO()
with contextlib.redirect_stdout(buffer):
    D = runpy.run_path(str(HERE.parent / "s1_trim_replay.py"))        # R5-D's harness, unpatched
recorded = (EV / "mic-speaker-echo/runs/s1-trim-replay.txt").read_text()
assert buffer.getvalue() == recorded, "unpatched harness no longer prints R5-D's table"
print(f"reproduced R5-D s1-trim-replay.txt ({len(recorded.splitlines()) - 1} rows identical)")
units, repeated = D["units"], D["repeated"]


def publish(solid: dict[str, str], previews: list[tuple[str, str]], frontier: int = 15, now: int = 20) -> list[dict]:
    """Solid text per lane committed to `frontier`, then one preview publication; returns the grey rows."""
    with tempfile.TemporaryDirectory() as tmp:
        rt = runtime.GeminiLiveRuntime(descriptor=D["descriptor"](), tape_storage_root=tmp,
                                       engine_factory=lambda _id, publish, _usage: runtime.ScriptedGeminiEngine(
                                           publish, batches=(), terminal=()))
        rt.create(session_id="one")
        for second in range(now):
            rt.accept_frame("one", D["AudioFrame"](sequence=second, pcm=b"\0" * 2 * S, sample_count=S))
        rt.publish_update("one", runtime.GeminiBase(frontier * S, ()))
        rt.publish_update("one", runtime.GeminiRolling(0, frontier * S, tuple(
            runtime.GeminiSegment(0, frontier * S, text, "speaker-0001" if lane == "system" else "local-0001", lane)
            for lane, text in solid.items() if text), revision_lanes=("system", "microphone")))
        rt.publish_update("one", runtime.GeminiPreview(now * S, tuple(
            runtime.GeminiSegment(frontier * S + i, now * S, text, source_lane=lane)
            for i, (lane, text) in enumerate(previews))))
        provisional = rt.snapshot("one").to_dict()["session"]["provisional"]
        return provisional["segments"] if provisional else []


def zh(text: str) -> str:
    """Solid text as a rolling commit writes it: one provider word per character, joined by join_text."""
    return D["rolling_text"](D["zh_words"](text))


# (name, solid text, preview text, the fresh part every arm must keep / None if the whole preview is a repeat)
ADVERSARIAL = [
    # --- genuine repetition by the speaker
    ("zh speaker repeats 对: solid ends 对对对, new turn 对对对 我同意",
     zh("这个方案我们下周再讨论。 对对对"), "对对对，我同意这个安排。", "对对对，我同意这个安排。"),
    ("zh speaker repeats 对 x6: solid ends 对对对对对对, new turn 对对对对对对 那就这样",
     zh("这个方案我们下周再讨论。 对对对对对对"), "对对对对对对，那就这样。", "对对对对对对，那就这样。"),
    ("en speaker repeats yes x3", "We can talk about the plan next week. Yes yes yes",
     "Yes yes yes, I agree with that.", "Yes yes yes, I agree with that."),
    ("en speaker repeats yes x6", "We can talk about the plan next week. Yes yes yes yes yes yes",
     "Yes yes yes yes yes yes, so be it.", "Yes yes yes yes yes yes, so be it."),
    ("zh repeated name: solid ends with the name, new turn starts with it",
     zh("下面请产品部的王小明"), "王小明，你来讲一下进度。", "王小明，你来讲一下进度。"),
    ("zh repeated long name (6 chars)",
     zh("下面有请欧阳娜娜老师"), "欧阳娜娜老师，请开始。", "欧阳娜娜老师，请开始。"),
    ("en repeated name", "Next we will hear from Grace Hopper", "Grace Hopper, please go ahead.",
     "Grace Hopper, please go ahead."),
    # --- coincidence: new speech starting with words equal to the END of the solid text
    ("zh anaphora 5 chars: 我们的这个方案… / 我们的这个接口…",
     zh("我觉得我们的这个方案是可以的"), "我们的这个接口还没有对接好。", "我们的这个接口还没有对接好。"),
    ("zh coincidence 5 chars exactly at the tail: …已经提交审核了 / 提交审核了以后…",
     zh("移动端的新版本已经提交审核了"), "提交审核了以后还要等一周。", "提交审核了以后还要等一周。"),
    ("zh coincidence 4 chars at the tail", zh("移动端的新版本已经提交审核"), "提交审核以后还要等一周。", "提交审核以后还要等一周。"),
    ("zh coincidence 8 chars at the tail", zh("我们需要先把接口的延迟测一下"), "把接口的延迟测一下再决定上线时间。",
     "把接口的延迟测一下再决定上线时间。"),
    ("en coincidence 5 words at the tail", "the new mobile version has already been submitted for review",
     "has been submitted for review, and then we wait a week.", "has been submitted for review, and then we wait a week."),
    ("en coincidence 4 words at the tail", "the new mobile version has already been submitted for review",
     "submitted for review means we wait a week.", "submitted for review means we wait a week."),
    # --- very short previews
    ("zh 1 char preview", zh("大家好今天我们主要讨论一下第三季度的产品规划"), "好", "好"),
    ("zh 2 char preview that equals the tail", zh("大家好今天我们主要讨论一下第三季度的产品规划"), "规划", "规划"),
    ("zh 4 char preview that equals the tail", zh("大家好今天我们主要讨论一下第三季度的产品规划"), "产品规划", "产品规划"),
    ("zh 6 char preview: whole preview repeats the tail", zh("大家好今天我们主要讨论一下第三季度的产品规划"), "季度的产品规划", None),
    ("zh short fresh reply 好的没问题", zh("大家好今天我们主要讨论一下第三季度的产品规划"), "好的，没问题。", "好的，没问题。"),
    # --- digits and punctuation runs
    ("zh digits: solid 30万 as digits, preview 三十万 as characters, then fresh",
     zh("我们今年的预算大概是 30 万左右"), "我们今年的预算大概是三十万左右，明年会增加到五十万。", "明年会增加到五十万。"),
    ("zh digits same form", zh("我们今年的预算大概是 30 万左右"), "我们今年的预算大概是30万左右，明年会增加到50万。", "明年会增加到50万。"),
    ("digit run only: phone number repeated then continued", "The number is 4 1 5 5 5 5 0 1 4 2",
     "4 1 5 5 5 5 0 1 4 2 and the extension is 7 7", "and the extension is 7 7"),
    ("fresh digits after digits: 1 2 3 4 5 / 6 7 8 9 10", "count with me 1 2 3 4 5", "6 7 8 9 10 11", "6 7 8 9 10 11"),
    ("punctuation only preview", zh("大家好今天我们主要讨论一下"), "……。", "……。"),
    ("zh preview with heavy punctuation over a repeat", zh("首先我来介绍一下目前的进展整体上还是按照计划在走"),
     "首先，我来介绍一下：目前的进展——整体上，还是按照计划在走。然后是风险。", "然后是风险。"),
    # --- same audio, different wording between the two models (recorded: 逼近/比进, 视频/视讯, another Latin name)
    ("zh homophones in the repeat: 视讯/视频, 问提/问题, 逼近/比进",
     zh("他跟公司的人开了一次视讯会议讨论这个问提目标是逼近去年的水平"),
     "他跟公司的人开了一次视频会议，讨论这个问题，目标是比进去年的水平，然后再看预算。", "然后再看预算。"),
    ("zh+Latin: a different Latin name for the same audio (Computerphile / Computer File)",
     zh("这是科技频道 Computerphile 十月初上架的专访"), "这是科技频道 Computer File 10 月初上架的专访，他从头讲那次会议。",
     "他从头讲那次会议。"),
    ("zh+Latin: name missing in the preview", zh("合作者 Grace Hopper 在 Microsoft 上班已经八九年"),
     "合作者在 Microsoft 上班已经八九年，后来去了别的公司。", "后来去了别的公司。"),
    # --- simplified vs traditional for the same speech
    ("solid traditional, preview simplified (recorded shape)",
     zh("一直在研究這個問題的是麻省理工學院的計算機教授。 他研究神經網絡的訓練方法已經八九年"),
     "一直在研究这个问题的是麻省理工学院的计算机教授。他研究神经网络的训练方法已经八九年，合作者在一家软件公司上班。",
     "合作者在一家软件公司上班。"),
    ("solid simplified, preview traditional",
     zh("一直在研究这个问题的是麻省理工学院的计算机教授。 他研究神经网络的训练方法已经八九年"),
     "一直在研究這個問題的是麻省理工學院的計算機教授。他研究神經網絡的訓練方法已經八九年，合作者在一家軟件公司上班。",
     "合作者在一家軟件公司上班。"),
    ("solid traditional, preview simplified, dense variant characters (说话时间长这个问题还没实现)",
     zh("對於這個問題來說還沒實現時間會議頻道專訪從頭講為什麼開"),
     "对于这个问题来说还没实现时间会议频道专访从头讲为什么开，后面再说。", "后面再说。"),
    # --- spaced scripts other than English
    ("ko spacing differs between the two models", "먼저 현재 진행 상황을 설명드리면 전체적으로 계획대로 진행되고 있습니다",
     "먼저 현재 진행상황을 설명 드리면 전체적으로 계획대로 진행되고 있습니다. 모바일 새 버전은 심사에 제출했습니다.",
     "모바일 새 버전은 심사에 제출했습니다."),
    ("ko short fresh reply", "오늘은 삼분기 제품 계획에 대해 논의하겠습니다", "네, 알겠습니다.", "네, 알겠습니다."),
    ("ko coincidence: new sentence starts with the 2 words the solid text ends with",
     "모바일 새 버전은 심사에 제출했습니다", "제출했습니다 그리고 다음 주에 발표합니다.", "제출했습니다 그리고 다음 주에 발표합니다."),
    ("de with ß before the cut (casefold lengthens the string)",
     "Die Straße ist heute wegen der großen Baustelle leider geschlossen",
     "Die Straße ist heute wegen der großen Baustelle leider geschlossen. Wir fahren außen herum.",
     "Wir fahren außen herum."),
    ("de with three ß before the cut (today's cut position is computed on the casefolded, longer string)",
     "Die Straße vor dem großen Haus ist außen leider geschlossen",
     "Die Straße vor dem großen Haus ist außen leider geschlossen. Wir fahren herum.", "Wir fahren herum."),
    # --- ja
    ("ja kana+kanji repeat then fresh", "".join(D["CASES"][next(k for k in D["CASES"] if k.startswith("ja"))][0][:40]),
     "本日は第三四半期の製品計画について話し合います。まず、現在の進捗をご説明しますと、次はリスクです。", "次はリスクです。"),
]


def cut_report(solid: str, preview: str, shown: str, fresh) -> dict:
    p, s = units(preview), units(shown)
    lost = max(0, len(units(fresh)) - len(s)) if fresh is not None else 0
    return {"preview_units": len(p), "shown_units": len(s), "removed_units": len(p) - len(s),
            "fresh_units_lost": lost, "repeat_left": repeated(s, units(solid)), "shown": shown}


def main():
    names = sys.argv[1:] or ["base", "A", "B", "C"]
    out: dict = {"cells": {}, "adversarial": {}, "cross_lane": {}}
    for name in names:
        runtime._trim_committed_preview = arms.ARMS[name]
        rows = [D["run"](case, words, preview, spaced=False) for case, (words, preview) in D["CASES"].items()]
        rows += [D["run"](case, words, preview, spaced=False, lane="microphone")
                 for case, (words, preview) in D["CASES"].items() if case in ("zh only", "en control")]
        out["cells"][name] = rows
        out["adversarial"][name] = {}
        for case, solid, preview, fresh in ADVERSARIAL:
            for lane in ("system", "microphone"):
                shown = "".join(row["text"] for row in publish({lane: solid}, [(lane, preview)]))
                out["adversarial"][name][f"{case} [{lane}]"] = cut_report(solid, preview, shown, fresh)
        # G4: the other lane's solid text is identical to this lane's preview; this lane has no solid text
        cross = {}
        for case, (words, preview) in D["CASES"].items():
            solid = D["rolling_text"](words)
            for mine, other in (("microphone", "system"), ("system", "microphone")):
                shown = "".join(row["text"] for row in publish({other: solid}, [(mine, preview)]))
                cross[f"{case}: {mine} preview vs {other} solid"] = len(units(preview)) - len(units(shown))
                both = publish({other: solid}, [(other, preview), (mine, preview)])
                kept = "".join(row["text"] for row in both if row["source_lane"] == mine)
                cross[f"{case}: {mine} preview vs {other} solid + {other} preview"] = len(units(preview)) - len(units(kept))
        out["cross_lane"][name] = cross
    runtime._trim_committed_preview = arms.BASE

    cols = ["case", "preview_units", "preview_units_already_committed", "grey_units_shown", "grey_units_repeating_solid",
            "fresh_units_expected", "trimmed"]
    for name in names:
        print(f"\n== cells, arm {name}")
        print(" | ".join(cols))
        for row in out["cells"][name]:
            print(" | ".join(str(row[c]) for c in cols))
    print("\n== G2 cells: shown text identical to base")
    for name in names[1:]:
        for b, r in zip(out["cells"]["base"], out["cells"][name]):
            if b["case"].startswith(("en", "ko")):
                print(f"{name:10} {b['case'][:40]:40} identical={b['grey_units_shown'] == r['grey_units_shown'] and b['trimmed'] == r['trimmed']}"
                      f" base shown {b['grey_units_shown']} arm shown {r['grey_units_shown']}")
    print("\n== adversarial (removed units / fresh units lost / repeated units left), system lane; microphone lane identical unless listed")
    for case, _solid, _preview, _fresh in ADVERSARIAL:
        line = f"{case[:78]:78}"
        for name in names:
            r = out["adversarial"][name][f"{case} [system]"]
            m = out["adversarial"][name][f"{case} [microphone]"]
            mark = "" if (r["removed_units"], r["shown"]) == (m["removed_units"], m["shown"]) else "!"
            line += f" | {name}: -{r['removed_units']} lost {r['fresh_units_lost']} left {r['repeat_left']}{mark}"
        print(line)
    print("\n== adversarial, what each arm shows")
    for case, _solid, preview, _fresh in ADVERSARIAL:
        print(f"- {case}\n    preview: {preview}")
        for name in names:
            print(f"    {name:5}: {out['adversarial'][name][f'{case} [system]']['shown']!r}")
    print("\n== G4 cross lane: units trimmed (must be 0)")
    for name in names:
        print(name, "max", max(out["cross_lane"][name].values()), "cases", len(out["cross_lane"][name]),
              {k: v for k, v in out["cross_lane"][name].items() if v})
    (EV / "f1").mkdir(parents=True, exist_ok=True)
    (EV / "f1/s1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")


main()
