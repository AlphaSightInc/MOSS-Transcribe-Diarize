"""Fixtures for the reproduction attempts (public/synthetic audio only; throwaway).

    PY f3/build_repro.py
What the real meeting had that R5-D's fixtures may not: names at the very start, another Mandarin voice,
sound under the speech (noise or music), a quieter lane.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import build  # noqa: E402  (R5-D's fixture builder: say(), speech_level(), system_lane())
from f3lib import FIX, RD_FIX  # noqa: E402

RATE = 16000
ZH_START = ("Media Lab 的 Alan Turing 教授一直在研究这个问题。Grace Hopper 是他的合作者，在 Microsoft 上班。"
            "Google 宣布之前，他跟 Google 的人开了一次视频会议。Computerphile 频道十月初上架了专访，"
            "他从头讲那次会议，也讲学术界为什么开始不愿公开自己的研究问题。")


def pink(n: int, seed: int) -> np.ndarray:
    white = np.fft.rfft(np.random.default_rng(seed).normal(0, 1, n))
    shaped = np.fft.irfft(white / np.sqrt(np.maximum(np.arange(len(white)), 1)), n)
    return shaped / build.rms(shaped)


def music(n: int) -> np.ndarray:
    """A slow synthetic chord pad (four triads, two seconds each, soft attack)."""
    t = np.arange(n) / RATE
    out = np.zeros(n)
    chords = [(220.0, 277.2, 329.6), (196.0, 246.9, 293.7), (174.6, 220.0, 261.6), (196.0, 246.9, 293.7)]
    for i, chord in enumerate(chords * (n // (8 * RATE) + 1)):
        lo, hi = i * 2 * RATE, min(n, (i + 1) * 2 * RATE)
        if lo >= n:
            break
        env = np.minimum(1, np.minimum(np.arange(hi - lo), np.arange(hi - lo)[::-1]) / (0.2 * RATE))
        for f in chord:
            out[lo:hi] += env * (np.sin(2 * np.pi * f * t[lo:hi]) + 0.4 * np.sin(2 * np.pi * 2 * f * t[lo:hi]))
    return out / build.rms(out)


def main():
    FIX.mkdir(parents=True, exist_ok=True)
    base = build.read(RD_FIX / "sys-zhlatin-en.wav")
    speech_rms = 10 ** (-17 / 20)
    made = {}
    zh, rate = build.say_within(ZH_START, "Tingting", 19.9)
    made["sys-zhstart-en"] = build.system_lane(zh)
    zh_tw, rate_tw = build.say_within(build.ZH, "Meijia", 19.9)
    made["sys-zhlatin-tw-en"] = build.system_lane(zh_tw)
    made["sys-zhlatin-en-noise10"] = base + pink(len(base), 5) * speech_rms * 10 ** (-10 / 20)
    made["sys-zhlatin-en-noise5"] = base + pink(len(base), 6) * speech_rms * 10 ** (-5 / 20)
    made["sys-zhlatin-en-music10"] = base + music(len(base)) * speech_rms * 10 ** (-10 / 20)
    made["sys-zhlatin-en-quiet25"] = base * 10 ** (-25 / 20)
    report = {"say_rate": {"zhstart": rate, "zh_tw": rate_tw}, "text": {"zhstart": ZH_START}, "files": {}}
    for name, x in made.items():
        sf.write(str(FIX / f"{name}.wav"), np.clip(x, -1, 1), RATE, subtype="PCM_16")
        report["files"][f"{name}.wav"] = {"seconds": len(x) / RATE, "rms_dbfs": round(build.db(build.rms(x)), 1),
                                          "sha256": hashlib.sha256((FIX / f"{name}.wav").read_bytes()).hexdigest()}
    (FIX / "repro-fixtures.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report["files"], indent=1))


if __name__ == "__main__":
    main()
