"""Step 0 ($0): the unpatched harness must reproduce R5-D's matrix before anything is changed (throwaway).

    PYTHON f2/baseline.py
Replays R5-D's 9 recorded cells through the unpatched product engine and compares, per cell, the microphone rows
at Stop and after clean-up and the five gate counters with R5-D's `runs/matrix.json`.
"""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import cells, fixtures, ledger

CELLS = ["listen-aec40", "listen-echo25", "long-aec40", "long-echo25", "short-aec40", "short-echo25", "short-noecho",
         "zhlong-aec40", "zhshort-aec40"]

def main():
    matrix = {row["run"]: row for row in json.loads((ledger.D_EV / "runs" / "matrix.json").read_text())}
    ok = True
    for cell in CELLS:
        cells.run(f"base/{cell}", fixtures.D_FIX / f"mic-{cell}.wav", answers=f"rp-{cell}")
        mine, theirs = cells.score(f"base/{cell}"), matrix[f"rp-{cell}-recorded"]
        same = {"saved_at_stop": mine["saved_at_stop"]["text"] == theirs["mic_saved_at_stop"],
                "after_cleanup": mine["saved"]["text"] == theirs["mic_after_cleanup"],
                "level": mine["counters"]["level"] == theirs["gate_level"],
                "voice": mine["counters"]["voice"] == theirs["gate_voice"],
                "text": mine["counters"]["text"] == theirs["gate_text"],
                "unanchored": mine["counters"]["unanchored"] == theirs["gate_unanchored"],
                "lane_withheld": mine["counters"]["lane_withheld"] == theirs["gate_lane_withheld"]}
        ok &= all(same.values())
        print(f"{cell:16s} {'REPRODUCED' if all(same.values()) else 'DIFFERS ' + str([k for k, v in same.items() if not v])}  "
              f"{mine['counters']}  r5d: level {theirs['gate_level']} text {theirs['gate_text']} unanchored "
              f"{theirs['gate_unanchored']} withheld {theirs['gate_lane_withheld']}", flush=True)
    print("BASELINE", "REPRODUCED 9/9" if ok else "DIFFERS")
    (ledger.EV / "runs" / "baseline.json").write_text(json.dumps({"reproduced": ok}, indent=1))

main()
