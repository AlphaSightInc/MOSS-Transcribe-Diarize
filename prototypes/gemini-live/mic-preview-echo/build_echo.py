"""zh speakers-echo mic lane: v1 zh local speech + noise, plus the zh far end at -25 dB (40 ms + reflections)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
V1 = HERE.parent / "mic-hallucination" / "out" / "fixture"
RATE = 16000


def main():
    system = sf.read(str(V1 / "zh-system.wav"), dtype="float64")[0]
    local = sf.read(str(V1 / "zh-hp-mic.wav"), dtype="float64")[0]
    echo = np.zeros_like(system)
    for delay, gain in ((0.040, 1.0), (0.071, .22), (0.119, .10)):
        shift = round(delay * RATE)
        echo[shift:] += gain * system[:len(system) - shift]
    mic = local + echo * 10 ** (-25 / 20)
    (HERE / "out").mkdir(exist_ok=True)
    sf.write(str(HERE / "out" / "zh-echo-mic.wav"), np.clip(mic, -1, 1), RATE, subtype="PCM_16")
    print("ok", len(mic) / RATE)


if __name__ == "__main__":
    main()
