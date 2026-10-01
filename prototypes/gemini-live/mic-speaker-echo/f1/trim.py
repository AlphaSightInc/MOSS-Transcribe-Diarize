"""R5-F1 candidate arms of the preview head trim (throwaway; patched in-process, product code untouched).

Every arm is the production `_trim_committed_preview` with its private whitespace tokenizer replaced
by a unit function; `head_rule()` is a parametrized copy of the production `_repeated_head`, used
only by the sweep arms and asserted equal to production at its default parameters (`selfcheck`).
"""
from __future__ import annotations

import difflib
import re
import sys
import unicodedata
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT)]
from moss_transcribe_diarize.app import gemini_live_runtime as runtime  # noqa: E402
from moss_transcribe_diarize.app.gemini_lane_engine import _preview_units  # noqa: E402

BASE = runtime._trim_committed_preview            # today's rule, captured before any patch
PROD_HEAD = runtime._repeated_head
NUMBERS = runtime._PREVIEW_NUMBERS
STRIP_BASE = " \t\r\n,.;:!?"
STRIP = STRIP_BASE + "，。；：！？、"
_CJK = ("CJK", "HIRAGANA", "KATAKANA", "HANGUL")
_UNSPACED = ("CJK", "HIRAGANA", "KATAKANA")      # join_text's notion: Korean has spaces


def units_hangul_whole(text: str) -> list[tuple[str, int, int]]:
    """`_preview_units` with a Hangul run kept as one unit (arm B)."""
    units = []
    for match in re.finditer(r"[^\W_\d]+|\d+", text):
        token, at, i = match.group(), match.start(), 0
        while i < len(token):
            j = i + 1
            if not unicodedata.name(token[i], "").startswith(_UNSPACED):
                while j < len(token) and not unicodedata.name(token[j], "").startswith(_UNSPACED):
                    j += 1
            unit = token[i:j].casefold()
            units.append((NUMBERS.get(unit, unit), at + i, at + j))
            i = j
    return units


# Traditional -> simplified for the characters that occur in the recorded answers (R5-D's fixture pairs plus
# the 41 variants in the zh-long rolling answers). PROTOTYPE ONLY: it measures what a script fold would buy;
# a product fold would need a full table (about 2,600 one-to-one pairs) or a dependency.
FOLD = dict(zip("這個問題學院計算機經網絡訓練會議頻道專訪從頭講為什麼開願術們視頻對實現時間後來說話還沒與業務數據長個發進"
                "來個們兩別劃動問單對廣後時會標沒測現發確組聯職蓋裡覺計訓試認調這週還間險項預題風體",
                "这个问题学院计算机经网络训练会议频道专访从头讲为什么开愿术们视频对实现时间后来说话还没与业务数据长个发进"
                "来个们两别划动问单对广后时会标没测现发确组联职盖里觉计训试认调这周还间险项预题风体"))


def units_folded(text: str) -> list[tuple[str, int, int]]:
    """`_preview_units` with traditional characters read as simplified (arm A+fold)."""
    return [(FOLD.get(unit, unit), start, end) for unit, start, end in _preview_units(text)]


def is_cjk(unit: str) -> bool:
    return len(unit) == 1 and unicodedata.name(unit, "").startswith(_CJK)


def head_rule(*, minimum=5, gap=8, skip=16, start=8, reach=8, share=0.6, weighted=False, probe=None):
    """`_repeated_head` with its constants as parameters. weighted: minimum evidence 5 * minimum where a
    word weighs 5 and a CJK character 3 (the echo rule's weights)."""
    def rule(tail, words):
        def joined(previous, block):
            shown_gap = block.a - (previous.a + previous.size)
            preview_gap = block.b - (previous.b + previous.size)
            return ((shown_gap <= gap and preview_gap <= gap)
                    or (shown_gap <= skip and preview_gap <= 1 and block.size >= 2))

        blocks = [block for block in difflib.SequenceMatcher(
            None, tail, words, autojunk=False).get_matching_blocks() if block.size]
        for index, head in enumerate(blocks):
            if head.b > start:
                break
            run = [head]
            for block in blocks[index + 1:]:
                if not joined(run[-1], block):
                    break
                run.append(block)
            while len(run) > 1 and run[-1].size == 1:
                run.pop()
            end = run[-1].b + run[-1].size
            matched = sum(block.size for block in run)
            if weighted:
                enough = sum(3 if is_cjk(u) else 5 for block in run
                             for u in words[block.b:block.b + block.size]) >= 5 * minimum
            else:
                enough = matched >= minimum
            if (enough and matched >= share * end
                    and (run[-1].a + run[-1].size >= len(tail) - reach or end >= len(words) - 1)):
                if probe is not None:
                    joins = [(b.a - (a.a + a.size), b.b - (a.b + a.size)) for a, b in zip(run, run[1:])]
                    probe.append({"matched": matched, "end": end, "share": matched / end, "start": head.b,
                                  "reach": len(tail) - (run[-1].a + run[-1].size), "covers_chunk": end >= len(words) - 1,
                                  "max_gap_both": max((max(g) for g in joins if g[0] <= gap and g[1] <= gap), default=0),
                                  "max_skip_shown": max((g[0] for g in joins if not (g[0] <= gap and g[1] <= gap)), default=0),
                                  "cjk": sum(is_cjk(u) for u in words[:end]) * 2 > end})
                return end
        return 0
    return rule


def make_trim(units=_preview_units, head=PROD_HEAD, strip=STRIP, log=None):
    """The production function body with tokens -> units. `log`, if given, receives one dict per row."""
    def trim(segments, committed):
        spans_of = [units(segment.text) for segment in segments]
        lane_units: dict = {}
        for segment, spans in zip(segments, spans_of):
            lane_units[segment.source_lane] = lane_units.get(segment.source_lane, 0) + len(spans)
        kept: list = []
        kept_units: list = []
        for segment, spans in zip(segments, spans_of):
            lane = segment.source_lane
            limit = max(60, lane_units[lane] * 5 // 4 + 8)
            parts = [us for row, us in zip(reversed(kept), reversed(kept_units)) if row.source_lane == lane]
            count = sum(len(part) for part in parts)
            for row in reversed(committed):
                if count >= limit:
                    break
                if row.source_lane == lane:
                    part = [unit for unit, _, _ in units(row.text)]
                    parts.append(part)
                    count += len(part)
            tail = [unit for part in reversed(parts) for unit in part][-limit:]
            cut = head(tail, [unit for unit, _, _ in spans])
            text = segment.text[spans[cut - 1][2]:].lstrip(strip) if cut else segment.text
            if log is not None:
                log({"lane": lane, "start": segment.start_sample, "units": len(spans), "cut": cut,
                     "raw": segment.text, "shown": text})
            if text:
                kept.append(replace(segment, text=text))
                kept_units.append([unit for unit, _, _ in units(text)])
        return tuple(kept)
    return trim


ARMS = {
    "base": BASE,
    "A": make_trim(),
    "B": make_trim(units=units_hangul_whole),
    "C": make_trim(head=head_rule(weighted=True)),
}
for _minimum in (6, 7, 8, 9, 10):
    ARMS[f"D-min{_minimum}"] = make_trim(head=head_rule(minimum=_minimum))
ARMS["D-min4"] = make_trim(head=head_rule(minimum=4))
ARMS["D-min3"] = make_trim(head=head_rule(minimum=3))
ARMS["D-scaled"] = make_trim(head=head_rule(gap=13, skip=27, start=13, reach=13))
ARMS["D-tight"] = make_trim(head=head_rule(gap=5, skip=10, start=5, reach=5))
ARMS["D-share50"] = make_trim(head=head_rule(share=0.5))
ARMS["D-share70"] = make_trim(head=head_rule(share=0.7))
ARMS["D-share80"] = make_trim(head=head_rule(share=0.8))
ARMS["A+fold"] = make_trim(units=units_folded)


def selfcheck(pairs) -> int:
    """The parametrized copy at default parameters must equal production `_repeated_head` on every input."""
    copy, n = head_rule(), 0
    for tail, words in pairs:
        assert copy(tail, words) == PROD_HEAD(tail, words), (tail, words)
        n += 1
    return n
