"""Exploration ($0): longest unexplained voiced stretch, negatives (whole lane) vs positives (per phrase)."""
import json, sys
from pathlib import Path
import numpy as np, soundfile as sf
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import evidence, fixtures

Q, MARGINS, GAPS = float(sys.argv[1]) if len(sys.argv) > 1 else .5, (6, 9, 12), (0, 5, 10)
def rd(p): return sf.read(str(p), dtype="int16")[0]

def stretches(flags, gap):
    out, start, last = [], None, None
    for i, f in enumerate(flags):
        if f:
            if start is None: start = i
            elif i - last - 1 > gap:
                out.append((start, last + 1)); start = i
            last = i
    if start is not None: out.append((start, last + 1))
    return out

def analyse(name, mic, tab, truth, verbose=True):
    f = evidence.Facts(mic, tab)
    er = evidence.echo_return_db(f, Q)
    loc = np.zeros(f.n, dtype=bool)
    for row in truth:
        loc[max(0, int(row["start"] * 100) - 30):int(row["end"] * 100) + 30] = True
    res = {"name": name, "echo_return_db": None if er is None else round(er, 1)}
    for m in MARGINS:
        u = evidence.unexplained(f, er, m)
        for g in GAPS:
            neg = [b - a for a, b in stretches(u & ~loc, g)]
            pos = [evidence.longest(u, int(r["start"] * 100) - 20, int(r["end"] * 100) + 20, g) for r in truth]
            res[f"m{m}g{g}"] = {"neg_max": max(neg, default=0), "neg_n>=30": sum(v >= 30 for v in neg),
                                "neg_top": sorted(neg)[-4:], "pos": pos}
    u0 = evidence.fixed_level(f)
    res["fixed-15,g5"] = {"neg_max": max([b - a for a, b in stretches(u0 & ~loc, 5)], default=0),
                          "pos": [evidence.longest(u0, int(r["start"] * 100) - 20, int(r["end"] * 100) + 20, 5) for r in truth]}
    if verbose:
        print(json.dumps(res, ensure_ascii=False))
    return res

if __name__ == "__main__":
    tab = rd(fixtures.D_FIX / "sys-zhlatin-en.wav")
    for kind in ("listen", "short", "zhshort", "long", "dlong"):
        for echo in (None, -40.0, -25.0, -15.0):
            for level in ((-27.0,) if kind == "listen" else (-21.0, -27.0, -33.0, -37.0, -41.0)):
                p = fixtures.d_cell(kind, echo, level)
                analyse(p.stem, rd(p), tab, json.loads(p.with_suffix(".json").read_text())["truth"])
    for name, (mic, tabp, truth) in fixtures.r4_lanes().items():
        analyse(name, rd(mic), rd(tabp), truth)
    worst = {}
    for name, (mic, tabx, truth) in fixtures.r4_pilot().items():
        r = analyse(name, mic, tabx, truth, verbose=False)
        kind = name.split("-")[1]
        for k, v in r.items():
            if isinstance(v, dict):
                worst.setdefault(kind, {})[k] = max(worst.get(kind, {}).get(k, 0), v["neg_max"])
    for kind, v in worst.items():
        print("pilot", kind, v)
