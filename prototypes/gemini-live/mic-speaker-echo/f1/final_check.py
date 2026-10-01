"""R5-F1 ($0): the production-form code written in NOTES.md, verbatim, against arm C on every captured input.

    PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python \
        prototypes/gemini-live/mic-speaker-echo/f1/final_check.py
"""
import difflib
import json
import sys
import unicodedata
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import score  # noqa: E402
import trim as arms  # noqa: E402
from trim import _preview_units  # noqa: E402

_CJK = ("CJK", "HIRAGANA", "KATAKANA", "HANGUL")
GeminiSegment = arms.runtime.GeminiSegment


def _unit_weight(unit: str) -> int:
    return 3 if len(unit) == 1 and unicodedata.name(unit, "").startswith(_CJK) else 5


def _repeated_head(tail, words):
    def joined(previous, block):
        shown_gap = block.a - (previous.a + previous.size)
        preview_gap = block.b - (previous.b + previous.size)
        return ((shown_gap <= 8 and preview_gap <= 8)
                or (shown_gap <= 16 and preview_gap <= 1 and block.size >= 2))

    blocks = [block for block in difflib.SequenceMatcher(
        None, tail, words, autojunk=False).get_matching_blocks() if block.size]
    for index, head in enumerate(blocks):
        if head.b > 8:
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
        evidence = sum(_unit_weight(unit) for block in run for unit in words[block.b:block.b + block.size])
        if (evidence >= 25 and matched >= 0.6 * end
                and (run[-1].a + run[-1].size >= len(tail) - 8 or end >= len(words) - 1)):
            return end
    return 0


def _trim_committed_preview(segments, committed):
    spans_of = [_preview_units(segment.text) for segment in segments]
    lane_units: dict[str | None, int] = {}
    for segment, spans in zip(segments, spans_of):
        lane_units[segment.source_lane] = lane_units.get(segment.source_lane, 0) + len(spans)
    kept: list[tuple[GeminiSegment, list[str]]] = []
    for segment, spans in zip(segments, spans_of):
        lane = segment.source_lane
        limit = max(60, lane_units[lane] * 5 // 4 + 8)
        parts = [units for row, units in reversed(kept) if row.source_lane == lane]
        count = sum(len(part) for part in parts)
        for row in reversed(committed):
            if count >= limit:
                break
            if row.source_lane == lane:
                parts.append([unit for unit, _, _ in _preview_units(row.text)])
                count += len(parts[-1])
        tail = [unit for part in reversed(parts) for unit in part][-limit:]
        cut = _repeated_head(tail, [unit for unit, _, _ in spans])
        text = (segment.text[spans[cut - 1][2]:].lstrip(" \t\r\n,.;:!?，。；：！？、") if cut else segment.text)
        if text:
            kept.append((replace(segment, text=text), [unit for unit, _, _ in spans[cut:]]))
    return tuple(row for row, _ in kept)


EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72/f1"
files = sorted((EV / "runs").glob("*-base*/trim.jsonl")) + sorted((EV / "runs").glob("*-trim-base.jsonl"))
calls = same = english_same = 0
for path in files:
    for line in path.read_text().splitlines():
        call = json.loads(line)
        segments = tuple(score.seg(r) for r in call["segments"])
        committed = tuple(score.eff(r) for r in call["committed"])
        final = _trim_committed_preview(segments, committed)
        calls += 1
        same += final == arms.ARMS["C"](segments, committed)
        if not any(score.has_cjk(r[2]) for r in call["segments"] + call["committed"]):
            english_same += final == arms.BASE(segments, committed)
print(json.dumps({"capture_files": len(files), "calls": calls, "final_equals_arm_C": same,
                  "calls_without_any_cjk_where_final_equals_todays_rule": english_same}))
assert same == calls
