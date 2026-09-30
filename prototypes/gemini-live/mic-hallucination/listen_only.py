"""Listen-only mic lanes (no local speech at all): does the whole-lane terminal call invent words?"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parent / "common")]
import build2  # noqa: E402
import noise  # noqa: E402
from gemini_common import diarize_window, spend  # noqa: E402

OUT = HERE / "out" / "fixture2"


def main():
    rows = {}
    for case, system_fn in (("A", build2.en_system), ("B", build2.zh_system)):
        rng = np.random.default_rng({"A": 31, "B": 32}[case])
        system, _ = system_fn()
        events, _ = noise.scatter(build2.N, rng, list(noise.EVENTS), every=(1.5, 5.0))
        mic = events + noise.room_tone(build2.N, rng) + noise.aec_residual(system, rng)
        pcm = np.clip(np.rint(np.clip(mic, -1, 1) * 32767), -32768, 32767).astype(np.int16)
        sf.write(str(OUT / f"{case}-listen-mic.wav"), pcm, build2.RATE, subtype="PCM_16")
        r = diarize_window(pcm, ledger_lane="r4c-mic-halluc")
        rows[case] = [(w.text, round(w.start, 1)) for w in r.words]
        print(case, len(rows[case]), rows[case][:80], flush=True)
    (OUT / "listen-only-terminal.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print(json.dumps(spend("r4c-mic-halluc")))


if __name__ == "__main__":
    main()
