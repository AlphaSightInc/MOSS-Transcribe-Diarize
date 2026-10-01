"""G2, the part that does not depend on what the provider returns ($0; throwaway).

    PYTHON f2/scan.py
On every lane with no local speech (and on the listening stretches of the round-4 lanes that have some), list every
sustained stretch of unexplained voiced audio - the only places where ANY provider answer could be admitted by the
candidate, and there only a run that weighs at least MIN_WEIGHT with COVERAGE of its words on that audio. Under
every real phrase, the longest such stretch. Writes runs/scan.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE)]
import candidate  # noqa: E402
import evidence  # noqa: E402
import fixtures  # noqa: E402
import ledger  # noqa: E402

P = candidate.PARAMS


def rd(path):
    return sf.read(str(path), dtype="int16")[0]


def flags_of(mic, tab):
    return candidate.local_audio(mic.tobytes(), tab.tobytes(), whole_lane=True)


def negative(name, mic, tab, truth=()):
    flags = flags_of(mic, tab)
    local = np.zeros(len(flags), dtype=bool)
    for row in truth:
        local[max(0, int(row["start"] * 100) - 50):int(row["end"] * 100) + 50] = True
    listening = flags & ~local
    all_stretches = [b - a for a, b in candidate.stretches_of(listening, P["gap_frames"], 1)]
    sustained = [n for n in all_stretches if n >= P["min_frames"]]
    return {"lane": name, "listening_seconds": round(float((~local).sum()) / 100, 1),
            "unexplained_voiced_seconds": round(float(listening.sum()) / 100, 1),
            "longest_stretch_s": max(all_stretches, default=0) / 100,
            "sustained_stretches": len(sustained), "sustained_seconds": round(sum(sustained) / 100, 1),
            "sustained_lengths_s": sorted(n / 100 for n in sustained)[-6:]}


def positive(name, mic, tab, truth):
    flags = flags_of(mic, tab)
    rows = []
    for phrase in truth:
        lo, hi = int(phrase["start"] * 100) - 20, int(phrase["end"] * 100) + 20
        rows.append({"text": phrase["text"][:40], "seconds": round(phrase["end"] - phrase["start"], 2),
                     "longest_stretch_s": evidence.longest(flags, lo, hi, P["gap_frames"]) / 100,
                     "unexplained_share": round(float(flags[max(0, lo + 20):hi - 20].mean()), 2)})
    return {"lane": name, "phrases": rows}


def main():
    out = {"params": dict(P), "negatives": [], "positives": []}
    tab = rd(fixtures.D_FIX / "sys-zhlatin-en.wav")
    for echo, seed in ((None, None), (-40.0, None), (-25.0, None), (-15.0, None), (-40.0, 3)):
        path = fixtures.d_cell("listen", echo, -27.0, seed)
        out["negatives"].append(negative(path.stem, rd(path), tab))
    for name, (mic, tab_path, truth) in fixtures.r4_lanes().items():
        out["negatives"].append(negative(name, rd(mic), rd(tab_path), truth))
    by_kind: dict[str, dict] = {}
    for name, (mic, tab_x, truth) in fixtures.r4_pilot().items():
        row = negative(name, mic, tab_x)
        kind = "r4:pilot-" + name.split("-")[1]
        agg = by_kind.setdefault(kind, {"lane": kind + " (4 x 30 s)", "listening_seconds": 0, "unexplained_voiced_seconds": 0,
                                        "longest_stretch_s": 0, "sustained_stretches": 0, "sustained_seconds": 0})
        for key in ("listening_seconds", "unexplained_voiced_seconds", "sustained_stretches", "sustained_seconds"):
            agg[key] = round(agg[key] + row[key], 1)
        agg["longest_stretch_s"] = max(agg["longest_stretch_s"], row["longest_stretch_s"])
    out["negatives"] += list(by_kind.values())
    for kind in ("short", "zhshort", "varied-en", "varied-zh", "long", "zhlong", "dlong"):
        for echo in (None, -40.0, -25.0):
            for level in (-27.0, -37.0):
                path = fixtures.d_cell(kind, echo, level)
                truth = json.loads(path.with_suffix(".json").read_text())["truth"]
                out["positives"].append(positive(path.stem, rd(path), tab, truth))
    (ledger.EV / "runs" / "scan.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(f"params {P}")
    print("NEGATIVE lanes: seconds listened | unexplained voiced s | longest stretch s | sustained stretches (>= "
          f"{P['min_frames'] / 100:.1f} s): count, seconds")
    for row in out["negatives"]:
        print(f"  {row['lane']:32s} {row['listening_seconds']:7.1f} | {row['unexplained_voiced_seconds']:6.1f} | "
              f"{row['longest_stretch_s']:5.2f} | {row['sustained_stretches']:3d}, {row['sustained_seconds']:5.1f}")
    print("REAL phrases: longest stretch under each phrase (s); phrases of >= 0.6 s")
    for row in out["positives"]:
        print(f"  {row['lane']:28s} " + " ".join(f"{p['longest_stretch_s']:.2f}" for p in row["phrases"]))
    worst = min(p["longest_stretch_s"] for row in out["positives"] for p in row["phrases"] if p["seconds"] >= .6)
    print("shortest stretch under a real phrase of >= 0.6 s:", worst)


main()
