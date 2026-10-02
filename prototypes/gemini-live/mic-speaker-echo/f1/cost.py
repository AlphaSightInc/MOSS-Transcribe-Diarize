"""R5-F1 G6 ($0): time per trim call, today's rule vs arm C, by preview size (throwaway).

    PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python \
        prototypes/gemini-live/mic-speaker-echo/f1/cost.py

One open turn of n units whose first 80 % is already solid (the worst shape: the whole tail is compared).
Text: the recorded Mandarin committed text / the recorded English committed words, repeated to length.
The longest recorded turns are 230 units (Mandarin, 50 s) and 406 words (English microphone echo, round 4).
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import stream  # noqa: E402
import trim as arms  # noqa: E402
from trim import _preview_units, runtime  # noqa: E402
from moss_transcribe_diarize.app.live_session import EffectiveTranscriptSegment  # noqa: E402

G = runtime.GeminiSegment


def best(arm, segments, committed, reps=7):
    out = []
    for _ in range(reps):
        started = time.perf_counter()
        arm(segments, committed)
        out.append(time.perf_counter() - started)
    return round(min(out) * 1e6)


def main():
    _, zh_commits, _ = stream.load_zh()
    _, en_commits, _ = stream.load_e1()
    zh = "".join(row.text for _, _, rows in zh_commits for row in rows)
    en = " ".join(row.text for _, _, rows in en_commits for row in rows)
    rows = []
    for label, text in (("zh", zh), ("en", en)):
        spans = _preview_units(text * 3)
        for n in (30, 100, 230, 400, 800, 1200):
            cut = int(n * .8)
            base = spans[400][1]
            solid_end = spans[400 + cut][1]
            preview_end = spans[400 + n][1]
            source = text * 3
            committed = tuple(EffectiveTranscriptSegment(i, i + 1, source[spans[max(0, 400 + cut - 70 * (k + 1))][1]:
                                                                           spans[400 + cut - 70 * k][1]], None, "rolling", "system")
                              for i, k in enumerate(reversed(range(20))) if 400 + cut - 70 * (k + 1) >= 0)
            segments = (G(100, 200, source[base:preview_end], None, "system"),)
            kept = arms.ARMS["C"](segments, committed)
            removed = n - len(_preview_units(kept[0].text if kept else ""))
            rows.append({"script": label, "preview_units": n, "already_solid": cut, "units_removed_by_C": removed,
                         "base_us": best(arms.BASE, segments, committed), "C_us": best(arms.ARMS["C"], segments, committed)})
            rows[-1]["added_us"] = rows[-1]["C_us"] - rows[-1]["base_us"]
    for row in rows:
        print(json.dumps(row))
    (stream.EV / "cost.json").write_text(json.dumps(rows, indent=1) + "\n")


main()
