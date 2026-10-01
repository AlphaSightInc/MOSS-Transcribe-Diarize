"""H2c ($0): at which speaking level do the product's microphone gates lose a real local sentence?  (throwaway)

    PYTHON prototypes/gemini-live/mic-speaker-echo/gate_sweep.py

Replays the recorded `rp-long-aec40` meeting through the production engine with the local speech
re-levelled (tab sound fixed at -17 dBFS, echo residue -40 dB). The provider's recorded words and
times are reused for every level, so only the product's gates respond to the level: voice-activity
word gate, level gate (-15 dB under the tab), voice and text echo guards, 2 s anchor.
Assumption: the provider hears the same words at every level (false below some level; unmeasured).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import build  # noqa: E402
import ledger  # noqa: E402

FIX = ledger.EV / "fixtures"
LONG = [(9.0, 140.0, 146.0), (34.3, 221.0, 223.6)]   # 6 s under the tab sound, 2.6 s after it


def local(level_dbfs: float) -> np.ndarray:
    src = build.read(build.B5 / "lex_keyu_jin" / "audio.wav")
    out = np.zeros(build.n(37.0))
    for at, lo, hi in LONG:
        cut = build.speech_level(build.fade(src[build.n(lo):build.n(hi)]), level_dbfs)
        out[build.n(at):build.n(at) + len(cut)] += cut[:len(out) - build.n(at)]
    return out


def main():
    system = build.read(FIX / "sys-zhlatin-en.wav")
    floor = np.random.default_rng(72).normal(0, 10 ** (-63 / 20), build.n(37.0))
    (FIX / "sweep").mkdir(exist_ok=True)
    table = []
    for level in (-21, -24, -27, -30, -33, -36, -39, -42):
        wav = FIX / "sweep" / f"mic-long-aec40-L{-level}.wav"
        sf.write(str(wav), np.clip(floor + build.echo_of(system, -40) + local(level), -1, 1), 16000, subtype="PCM_16")
        run = f"sweep-long-L{-level}"
        subprocess.run([sys.executable, str(HERE / "replay.py"), run, str(FIX / "sys-zhlatin-en.wav"), str(wav),
                        "--provider-words-from", "rp-long-aec40"], check=True, capture_output=True)
        out = ledger.EV / "runs" / run
        gates = [json.loads(line) for line in (out / "gates.jsonl").read_text().splitlines()]
        summaries = [g for g in gates if g["stage"] == "window_summary"]
        live = json.loads((out / "saved-meeting-live.json").read_text())["transcript"]["segments"]
        final = json.loads((out / "saved-meeting.json").read_text())["transcript"]["segments"]
        words = lambda rows: sum(len(r["text"].split()) for r in rows if r["source_lane"] == "microphone")
        diag = json.loads((out / "engine.json").read_text())
        table.append({"local_speech_dbfs": level, "below_tab_db": level + 17,
                      "live_windows(after_vad,after_level,after_text,unanchored)": [
                          (s["after_voice_activity_gate"], s["after_acoustic"], s["after_text_guard"], s["dropped_unanchored"])
                          for s in summaries[:-1]],
                      "cleanup(after_vad,after_level,after_text,withheld)": (
                          summaries[-1]["after_voice_activity_gate"], summaries[-1]["after_acoustic"],
                          summaries[-1]["after_text_guard"], summaries[-1]["withheld_lane"]),
                      "mic_words_live_at_stop": words(live), "mic_words_saved": words(final),
                      "level_gate_drops": diag["mic_words_dropped_by_acoustic_gate"],
                      "unanchored_drops": diag["mic_words_dropped_unanchored"],
                      "lane_withheld": diag["mic_words_withheld_unanchored_lane"]})
        print(json.dumps(table[-1]), flush=True)
    (ledger.EV / "runs" / "gate-sweep.json").write_text(json.dumps(table, indent=1) + "\n")


main()
