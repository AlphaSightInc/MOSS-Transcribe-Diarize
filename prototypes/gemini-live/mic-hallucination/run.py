"""Gemini calls for the fixture: mic rolling 30/15 s windows, whole-lane mic and system (cached)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), str(HERE.parent / "common")]
from gemini_common import diarize_window, read_wav, spend  # noqa: E402
from moss_transcribe_diarize.app.gemini_lane_engine import WebRtcSpeechDetector  # noqa: E402

RATE = 16000
LANE = "r4c-mic-halluc"
FIX = HERE / "out" / ("fixture2" if "--v2" in sys.argv else "fixture")


def words(result):
    return [{"text": w.text, "speaker": w.speaker, "start": w.start, "end": w.end} for w in result.words]


def main() -> None:
    manifest = json.loads((FIX / "reference.json").read_text())
    args = [a for a in sys.argv[1:] if a != "--v2"]
    names = args[0].split(",") if args else list(manifest["variants"])
    detector = WebRtcSpeechDetector()
    for name in names:
        v = manifest["variants"][name]
        mic = read_wav(FIX / v["microphone"])
        system = read_wav(FIX / v["system"])
        out = {"variant": name, "rolling": [], "whole_mic": None, "whole_system": None}
        last = 0
        for t in range(15, manifest["duration_s"] + 1, 15):
            start, end = max(0, t - 30) * RATE, t * RATE
            new = mic[max(start, last):end]
            last = end
            if not detector(new.tobytes()):
                out["rolling"].append({"start_s": start / RATE, "end_s": t, "skipped": True})
                continue
            r = diarize_window(mic[start:end], ledger_lane=LANE)
            out["rolling"].append({"start_s": start / RATE, "end_s": t, "words": words(r)})
        out["whole_mic"] = words(diarize_window(mic, ledger_lane=LANE))
        out["whole_system"] = words(diarize_window(system, ledger_lane=LANE))
        (FIX / f"{name}-gemini.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
        print(name, sum(len(w.get("words", [])) for w in out["rolling"]), len(out["whole_mic"]),
              len(out["whole_system"]), flush=True)
    print(json.dumps(spend(LANE)))


if __name__ == "__main__":
    main()
