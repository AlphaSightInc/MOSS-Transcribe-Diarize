"""Exploration ($0): microphone/tab level ratio per frame, echo-only vs local speech (throwaway)."""
import json, sys
from pathlib import Path
import numpy as np, soundfile as sf
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import evidence, fixtures

def rd(p): return sf.read(str(p), dtype="int16")[0]
def q(x): return [round(float(v), 1) for v in np.quantile(x, [.05, .2, .5, .8, .95, .99])] if len(x) else None

def report(name, mic, tab, truth):
    f = evidence.Facts(mic, tab)
    r = f.ratio_db()
    loc = np.zeros(f.n, dtype=bool)
    for row in truth:
        loc[int(row["start"] * 100):int(row["end"] * 100) + 1] = True
    tabv = ~np.isnan(r)
    print(f"{name:28s} tab-voiced {tabv.mean():.2f}  ratio echo-only q05/20/50/80/95/99 {q(r[tabv & ~loc])}  "
          f"local {q(r[tabv & loc])}  micVAD: outside-local {f.mic_voiced[~loc].mean():.2f} local {f.mic_voiced[loc].mean() if loc.any() else None}")

tab = rd(fixtures.D_FIX / "sys-zhlatin-en.wav")
for kind in ("listen", "short", "long", "zhshort", "dlong"):
    for echo in (None, -40.0, -25.0, -15.0):
        for level in ((-27.0,) if kind == "listen" else (-21.0, -27.0, -33.0, -37.0, -41.0)):
            p = fixtures.d_cell(kind, echo, level)
            report(p.stem, rd(p), tab, json.loads(p.with_suffix(".json").read_text())["truth"])
for name, (mic, tabp, truth) in fixtures.r4_lanes().items():
    report(name, rd(mic), rd(tabp), truth)
