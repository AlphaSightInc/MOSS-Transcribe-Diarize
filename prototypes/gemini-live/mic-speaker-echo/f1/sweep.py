"""R5-F1 T5 ($0): margin of the minimum run, on the recorded Mandarin text cut at every position (throwaway).

    PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python \
        prototypes/gemini-live/mic-speaker-echo/f1/sweep.py

The recorded streams never produced a repeated head shorter than 12 units, so they cannot rank the minimum.
Here the provider's own committed text of the 188 s Mandarin stream (and W3's text of it) is cut at every
character position p:
- fresh trial:   solid = text[:p], preview = text[p:p+40]      -> any cut is fresh speech removed;
- repeat trial:  solid = text[:p], preview = text[p-k:p+30]    -> the cut should be k (k = 3..12).
The text holds what speakers do: 对对对, 好的好的, a name said twice, three sentences opening 我们的这个,
入职，入职以后, 之前 three times. English control: the same trials on the E1 committed words.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import score  # noqa: E402
import stream  # noqa: E402
import trim as arms  # noqa: E402
from trim import _preview_units, runtime  # noqa: E402
from moss_transcribe_diarize.app.live_session import EffectiveTranscriptSegment  # noqa: E402

G = runtime.GeminiSegment
NAMES = ["A", "D-min3", "D-min4", "D-min6", "D-min7", "D-min8", "D-min9", "D-min10", "C", "A+fold"]


def trials(text: str, step_units: bool):
    spans = _preview_units(text)
    for index in range(20, len(spans) - 12):
        yield spans, index


def run(label: str, solid_text: str, preview_text: str | None = None):
    """solid_text: what is committed; preview_text: the other model's text of the same speech (None = same text)."""
    spans = _preview_units(solid_text)
    out = {name: {"fresh_trials": 0, "fresh_cut": 0, "fresh_units_removed": 0, "examples": [],
                  "repeat": {k: [0, 0] for k in range(3, 13)}} for name in NAMES}
    for index in range(20, len(spans) - 12):
        p = spans[index][1]
        solid = (EffectiveTranscriptSegment(0, 1, solid_text[:p], None, "rolling", "system"),)
        fresh = solid_text[p:spans[min(len(spans) - 1, index + 40)][1]]
        for name in NAMES:
            stat = out[name]
            kept = arms.ARMS[name]((G(1, 2, fresh, None, "system"),), solid)
            shown = kept[0].text if kept else ""
            removed = len(_preview_units(fresh)) - len(_preview_units(shown))
            stat["fresh_trials"] += 1
            if removed:
                stat["fresh_cut"] += 1
                stat["fresh_units_removed"] += removed
                if len(stat["examples"]) < 12:
                    stat["examples"].append({"solid_end": solid_text[max(0, p - 16):p], "preview": fresh[:24], "removed": removed})
            for k in range(3, 13):
                start = spans[index - k][1]
                preview = solid_text[start:spans[min(len(spans) - 1, index + 30)][1]]
                kept = arms.ARMS[name]((G(1, 2, preview, None, "system"),), solid)
                shown = kept[0].text if kept else ""
                cut = len(_preview_units(preview)) - len(_preview_units(shown))
                stat["repeat"][k][0] += 1
                stat["repeat"][k][1] += cut >= k
    print(f"\n== {label}: {len(spans)} units, {out['A']['fresh_trials']} positions")
    print("arm       | fresh trials cut (false trims) | fresh units removed | repeated head of k units removed, % of positions: k=3 4 5 6 7 8 9 10 11 12")
    for name in NAMES:
        s = out[name]
        rates = " ".join(f"{100 * hit / max(1, n):3.0f}" for n, hit in s["repeat"].values())
        print(f"{name:9} | {s['fresh_cut']:4} of {s['fresh_trials']:4} ({100 * s['fresh_cut'] / s['fresh_trials']:.2f} %) | {s['fresh_units_removed']:4} | {rates}")
    for name in ("A", "D-min7", "C"):
        for example in out[name]["examples"]:
            print(f"   {name} false trim: {json.dumps(example, ensure_ascii=False)}")
    return out


def main():
    events, commits, _ = stream.load_zh()
    zh = "".join(row.text for _, _, rows in commits for row in rows)
    report = {"zh-long committed text (provider rolling answers)": run("zh-long committed text", zh)}
    w3 = "".join(e[0] for e in events if e[3])
    report["zh-long W3 final text"] = run("zh-long W3 finals text", w3)
    e_events, e_commits, _ = stream.load_e1()
    en = " ".join(row.text for _, _, rows in e_commits for row in rows)
    report["e1 English committed text"] = run("E1 English committed text (control: units are words)", en)
    (stream.EV / "sweep.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")


main()
