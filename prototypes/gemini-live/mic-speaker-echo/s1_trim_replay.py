"""S1 ($0): does the grey preview of a lane repeat that lane's committed text?  (throwaway)

Runs the production publication path (GeminiLiveRuntime.publish_update -> LiveSession) with
scripted updates shaped like the bug: one W3 turn that started before the commit frontier, so
its row carries the whole turn's text, and a rolling commit of the turn's first part.

    PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-d.venv/bin/python \
        prototypes/gemini-live/mic-speaker-echo/s1_trim_replay.py

Text is synthetic (written for this prototype), with the measured differences between the two
models on the same speech: rolling returns one word per Chinese character joined without
spaces (F1 rule) and little punctuation; W3 writes its own string with commas and spaces
around Latin words; a few homophones and names differ.
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from functools import reduce
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT)]
from moss_transcribe_diarize.app.gemini_lane_engine import _preview_units  # noqa: E402
from moss_transcribe_diarize.app.gemini_live_runtime import (  # noqa: E402
    GeminiBase, GeminiLiveRuntime, GeminiPreview, GeminiRolling, GeminiSegment, ScriptedGeminiEngine)
from moss_transcribe_diarize.app.live_service_runtime import (  # noqa: E402
    LiveServiceBounds, LiveServiceConfigHashes, LiveServiceDescriptor)
from moss_transcribe_diarize.app.live_session import AudioFrame  # noqa: E402
from moss_transcribe_diarize.app.transcript_text import join_text  # noqa: E402

S = 16000


def descriptor():
    return LiveServiceDescriptor(
        source_revision="proto", provider_name="gemini", provider_revision="r5d",
        provider_manifest_hash=hashlib.sha256(b"gemini").hexdigest(),
        config_hashes=LiveServiceConfigHashes.from_parts(endpoint_config={}, identity_config={}, decoder_config={}),
        bounds=LiveServiceBounds(max_frame_samples=S, max_queue_depth=4, max_retained_samples=2 * S,
                                 max_identity_speakers=8, max_events=64, max_tape_bytes=40 * 2 * S),
        frame_samples=S)


def rolling_text(words: list[str], *, spaced: bool = False) -> str:
    """How a rolling commit joins provider words: join_text (since 694212f8), a space before."""
    return " ".join(words) if spaced else reduce(join_text, words, "")


def zh_words(text: str) -> list[str]:
    """One provider word per Chinese character; Latin words whole; punctuation rides on the word before."""
    out: list[str] = []
    for token in text.split(" "):
        if token.isascii():
            out.append(token)
            continue
        for ch in token:
            if ch in "。，？！" and out:
                out[-1] += ch
            else:
                out.append(ch)
    return out


CASES = {
    # (rolling words of the committed first part, W3 string of the whole turn so far)
    "zh+latin names": (
        zh_words("一直在研究这个问提的是麻省理工学院 Media Lab 的计算机教授 Alan Turing。 他研究神经网络的训练方法已经八九年合作者 "
                 "Grace Hopper 在 Microsoft 上班。 Google 宣布之前他跟 Google 的人开了一次视讯会议。 这是科技频道 Computerphile"),
        "一直在研究这个问题的是麻省理工学院 Media Lab 的计算机教授 Alan Turing。他研究神经网络的训练方法已经八九年，合作者 Grace Hopper 在 "
        "Microsoft 上班。Google 宣布之前，他跟 Google 的人开了一次视频会议。这是科技频道 Computerphile 10 月初上架的专访，他从头讲那次会议，"
        "也讲学术界为什么开始不愿公开自己的研究问题。"),
    "zh only": (
        zh_words("大家好今天我们主要讨论一下第三季度的产品规划。 首先我来介绍一下目前的进展整体上还是按照计划在走。 移动端的新版本已经提交审核了"),
        "大家好，今天我们主要讨论一下第三季度的产品规划。首先我来介绍一下目前的进展，整体上还是按照计划在走。移动端的新版本已经提交审核了，"
        "预计下周可以发布。不过有一个风险，就是第三方支付的接口还没有完全对接好。"),
    "en control": (
        "and you guys have about 6 months of cash left. And so you decide to do the entire testing in simulation rather "
        "than ever receiving a physical prototype. You commission the production run sight unseen with the rest of the "
        "company's money. So you're betting it all right here on the".split(),
        "you guys have about six months of cash left. And so you decide to do the entire testing in simulation rather than "
        "ever receiving a physical prototype. You commission the production run sight unseen with the rest of the "
        "company's money. So you're betting it all right here on the Rivian 120"),
}


def units(text: str) -> list[str]:
    return [unit for unit, _, _ in _preview_units(text)]


def repeated(shown: list[str], committed: list[str]) -> int:
    """Units of the grey row that sit in a run of >= 5 units also present, in order, in the committed text."""
    import difflib
    return sum(block.size for block in difflib.SequenceMatcher(None, committed, shown, autojunk=False)
               .get_matching_blocks() if block.size >= 5)


def run(name: str, committed_words: list[str], preview: str, *, spaced: bool, frontier: int = 15, now: int = 20):
    committed = rolling_text(committed_words, spaced=spaced)
    with tempfile.TemporaryDirectory() as tmp:
        rt = GeminiLiveRuntime(descriptor=descriptor(), tape_storage_root=tmp,
                               engine_factory=lambda _id, publish, _usage: ScriptedGeminiEngine(
                                   publish, batches=(), terminal=()))
        rt.create(session_id="one")
        for second in range(now):
            rt.accept_frame("one", AudioFrame(sequence=second, pcm=b"\0" * 2 * S, sample_count=S))
        rt.publish_update("one", GeminiBase(frontier * S, ()))
        rt.publish_update("one", GeminiRolling(0, frontier * S, (
            GeminiSegment(0, frontier * S, committed, "speaker-0001", "system"),), revision_lanes=("system",)))
        # The hybrid engine clips the open W3 turn's row to the frontier; its text is the whole turn.
        rt.publish_update("one", GeminiPreview(now * S, (
            GeminiSegment(frontier * S, now * S, preview, source_lane="system"),)))
        session = rt.snapshot("one").to_dict()["session"]
        shown = "".join(row["text"] for row in session["provisional"]["segments"])
    c, p, s = units(committed), units(preview), units(shown)
    fresh = len(p) - repeated(p, c)
    return {"case": name, "committed_join": "spaced (before 694212f8)" if spaced else "join_text (9a1ca171)",
            "committed_units": len(c), "preview_units": len(p), "preview_units_already_committed": repeated(p, c),
            "grey_units_shown": len(s), "grey_units_repeating_solid": repeated(s, c),
            "fresh_units_expected": fresh, "trimmed": len(p) - len(s)}


def main():
    rows = [run(name, words, preview, spaced=False) for name, (words, preview) in CASES.items()]
    rows += [run(name, words, preview, spaced=True) for name, (words, preview) in CASES.items() if name != "en control"]
    cols = list(rows[0])
    print(" | ".join(cols))
    for row in rows:
        print(" | ".join(str(row[c]) for c in cols))


main()
