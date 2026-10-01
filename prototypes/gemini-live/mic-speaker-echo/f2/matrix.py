"""Every recorded cell through the product engine, today's rule and the candidate, one line each (throwaway, $0).

    PYTHON f2/matrix.py [tag] ['{"min_weight": 20}']      # tag names the candidate variant (default "cand")
Writes runs/matrix-<tag>.json. Today's rule is run once as `base/<cell>` and reused.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import cells  # noqa: E402
import fixtures  # noqa: E402
import ledger  # noqa: E402

# (cell name, microphone wav, recorded answers, what the cell is)
R5D = [(name, fixtures.D_FIX / f"mic-{name}.wav", f"rp-{name}", what) for name, what in (
    ("listen-aec40", "no local speech, echo -40 dB"), ("listen-echo25", "no local speech, echo -25 dB"),
    ("short-aec40", "3 short EN phrases, echo -40 dB"), ("short-echo25", "3 short EN phrases, echo -25 dB"),
    ("short-noecho", "3 short EN phrases, no echo"), ("zhshort-aec40", "3 short ZH phrases, echo -40 dB"),
    ("long-aec40", "long EN turns, echo -40 dB"), ("long-echo25", "long EN turns, echo -25 dB"),
    ("zhlong-aec40", "long ZH turns, echo -40 dB"))]
F2 = [(name, fixtures.FIX / f"mic-{name}.wav", f"f2-{name}", what) for name, what in (
    ("dlong-e40-L37", "long EN turns under the tab, 20 dB under it"),
    ("short-e40-L37", "3 short EN phrases, 20 dB under the tab"),
    ("zhshort-e40-L37", "3 short ZH phrases, 20 dB under the tab"),
    ("varied-en-e40-L27", "8 EN replies of 1-8 words"), ("varied-zh-e40-L27", "8 ZH replies of 2-11 characters"),
    ("mixed-e40-L27", "a long turn and 4 short replies"),
    ("short-e15-L27", "3 short EN phrases, echo -15 dB"), ("listen-e15-L27", "no local speech, echo -15 dB"),
    ("listen-e40-L27-n3", "no local speech, room-noise events, echo -40 dB"))]
CELLS = R5D + F2


def one(job):
    out, mic, answers, params = job
    folder = ledger.EV / "runs" / out
    if params is None and (folder / "receipt.json").is_file():       # today's rule: run once
        return
    cells.run(out, mic, answers=answers, candidate=params, w3=None if answers.startswith("rp-") else "none",
              w3_system_from=None if answers.startswith("rp-") else "rp-short-aec40")


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "cand"
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    jobs = [(f"base/{name}", mic, answers, None) for name, mic, answers, _ in CELLS] + \
           [(f"{tag}/{name}", mic, answers, params) for name, mic, answers, _ in CELLS]
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(one, jobs))
    rows = []
    for name, _mic, _answers, what in CELLS:
        base, cand = cells.score(f"base/{name}"), cells.score(f"{tag}/{name}")
        rows.append({"cell": name, "what": what, "today": base, "candidate": cand})
        print(f"{name:20s} {what}")
        for label, s in (("today", base), ("cand ", cand)):
            print(f"   {label} live {s['live_solid']['recall']:>6s} extra {s['live_solid']['extra_units']:<2d} | at Stop "
                  f"{s['saved_at_stop']['recall']:>6s} extra {s['saved_at_stop']['extra_units']:<2d} | saved "
                  f"{s['saved']['recall']:>6s} extra {s['saved']['extra_units']:<2d} | {s['saved']['phrases']} {s['counters']}")
        if cand["saved"]["extra_units"] or cand["saved_at_stop"]["extra_units"] or cand["live_solid"]["extra_units"]:
            print("      cand live :", cand["live_solid"]["text"], "\n      cand stop :", cand["saved_at_stop"]["text"],
                  "\n      cand saved:", cand["saved"]["text"])
    (ledger.EV / "runs" / f"matrix-{tag}.json").write_text(json.dumps({"params": params, "rows": rows}, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
