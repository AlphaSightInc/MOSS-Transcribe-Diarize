"""Fixtures that try to make the LIVE transcript commit words nobody said, to attack rule H (throwaway).

    PY f3/build_invented.py
A (system lane): the Chinese+English recording, then 20 s of music only (synthetic chord pad at speech level).
B (microphone lane): one real local sentence (so the lane has local speech context), echo-cancellation residue of
   the tab sound and room events (round 4's generators: creak, smack, throat, cough, breath, keys) for 60 s.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent), str(HERE.parents[1] / "mic-hallucination")]
import build  # noqa: E402
import noise  # noqa: E402
from build_repro import music  # noqa: E402
from f3lib import FIX, RD_FIX  # noqa: E402

RATE = 16000


def main():
    base = build.read(RD_FIX / "sys-zhlatin-en.wav")
    n = 60 * RATE
    a = np.zeros(n)
    a[:len(base)] = base
    pad = music(20 * RATE) * 10 ** (-20 / 20)
    a[int(37.5 * RATE):int(57.5 * RATE)] = pad
    system = np.zeros(n)
    system[:len(base)] = base
    rng = np.random.default_rng(53)
    local = build.local_speech(60.0, [(9.0, 140.0, 146.0)])
    events, placed = noise.scatter(n, rng, ["creak", "smack", "throat", "cough", "breath", "keys"],
                                   every=(1.0, 3.0), avoid=[(9.0, 15.0)])
    mic = (rng.normal(0, 10 ** (-63 / 20), n) + local + noise.aec_residual(system, rng, -38.0) + events)
    report = {"events": placed, "files": {}}
    for name, x in {"sys-speech-music": a, "sys-60": system, "mic-events": mic}.items():
        sf.write(str(FIX / f"{name}.wav"), np.clip(x, -1, 1), RATE, subtype="PCM_16")
        report["files"][f"{name}.wav"] = {"seconds": len(x) / RATE, "rms_dbfs": round(build.db(build.rms(x)), 1),
                                          "sha256": hashlib.sha256((FIX / f"{name}.wav").read_bytes()).hexdigest()}
    (FIX / "invented-fixtures.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({"events": len(placed), **report["files"]}, indent=1))


if __name__ == "__main__":
    main()
