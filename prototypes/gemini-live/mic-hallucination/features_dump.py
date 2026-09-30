"""Dump per-word features for words the production chain keeps (rolling + terminal)."""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
from chain import Variant, RATE, FIX  # noqa: E402
from features import Frames  # noqa: E402


def script(text):
    for ch in text:
        n = unicodedata.name(ch, "")
        if not ch.isalpha():
            continue
        for s in ("CJK", "HIRAGANA", "KATAKANA", "HANGUL", "CYRILLIC", "LATIN", "DEVANAGARI", "ARABIC", "THAI"):
            if n.startswith(s):
                return {"HIRAGANA": "KANA", "KATAKANA": "KANA"}.get(s, s)
        return "OTHER"
    return "NONE"


def run_lengths(words, gap_s):
    words = sorted(words, key=lambda w: w.start_sample)
    out = {}
    i = 0
    while i < len(words):
        j = i
        while j + 1 < len(words) and words[j + 1].start_sample - words[j].end_sample <= gap_s * RATE:
            j += 1
        for k in range(i, j + 1):
            out[id(words[k])] = (j - i + 1, (words[j].end_sample - words[i].start_sample) / RATE)
        i = j + 1
    return out


def main():
    rows = []
    for name in [a for a in sys.argv[1:] if not a.startswith("--")]:
        v = Variant(name)
        gate, sysw = v.gate()
        mic_frames = Frames(v.mic)
        sys_frames = Frames(v.system)
        per_window = []
        def extra(words, pcm, start, kind):
            runs = run_lengths(list(words), 1.0)
            for w in words:
                per_window.append((kind, start, w, runs[id(w)]))
            return words
        v.rolling(gate, extra)
        v.terminal(gate, sysw, extra)
        frontier_owned = set()
        for kind, (start, end, frontier), w, (run_n, run_s) in per_window:
            if not frontier < w.end_sample <= end:
                continue
            f = mic_frames.word(w.start_sample / RATE, w.end_sample / RATE)
            sf_ = sys_frames.word(w.start_sample / RATE, w.end_sample / RATE, 0)
            rows.append({"variant": name, "kind": kind, "window": [start / RATE, end / RATE], "text": w.text,
                         "t": round(w.start_sample / RATE, 2), "dur": round((w.end_sample - w.start_sample) / RATE, 2),
                         "local": v.is_local(w), "script": script(w.text), "run_n": run_n, "run_s": round(run_s, 2),
                         **f, "sys_peak_db": sf_["peak_db"], "sys_m1_any": sf_["m1_any"]})
    (FIX / "features.json").write_text(json.dumps(rows, ensure_ascii=False))
    print(len(rows))


if __name__ == "__main__":
    main()
