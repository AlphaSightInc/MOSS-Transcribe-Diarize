"""One line per candidate variant from the files variant.py wrote ($0).   PYTHON f2/summary.py [tag ...]"""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import ledger
RUNS = ledger.EV / "runs"
tags = sys.argv[1:] or [p.stem[7:] for p in sorted(RUNS.glob("matrix-*.json"), key=lambda p: p.stat().st_mtime)]
KEYS = ("live_solid", "saved_at_stop", "saved")
out = []
for tag in tags:
    m = json.loads((RUNS / f"matrix-{tag}.json").read_text())
    r4_path = RUNS / f"r4-{tag}" / "summary.json"
    r4 = json.loads(r4_path.read_text()) if r4_path.is_file() else None
    rows = m["rows"]
    got = lambda who, key: sum(int(r[who][key]["recall"].split("/")[0]) for r in rows)
    spoken = sum(int(r["today"]["saved"]["recall"].split("/")[1]) for r in rows)
    wrong = lambda who: sum(r[who][k]["outside_units"] + r[who][k]["echo_inside_units"] for r in rows for k in KEYS)
    listen = sum(r["candidate"][k]["extra_units"] for r in rows if r["cell"].startswith("listen") for k in KEYS)
    worse = [r["cell"] for r in rows if any(int(r["candidate"][k]["recall"].split("/")[0]) < int(r["today"][k]["recall"].split("/")[0]) for k in KEYS)]
    row = {"variant": tag, "params": m["params"], "units_spoken": spoken,
           "today_live_stop_saved": [got("today", k) for k in KEYS], "candidate_live_stop_saved": [got("candidate", k) for k in KEYS],
           "listen_cells_committed_or_saved": listen, "wrong_units_today": wrong("today"), "wrong_units_candidate": wrong("candidate"),
           "round4_admitted": None if r4 is None else r4["candidate"],
           "round4_words": None if r4 is None else [w[1] for w in r4["candidate_words"]][:12],
           "cells_below_today": worse}
    out.append(row)
    print(f"{tag:8s} {json.dumps(m['params']):34s} live/stop/saved {row['candidate_live_stop_saved']} of {spoken} (today {row['today_live_stop_saved']}) | "
          f"listen cells {listen} | round-4 {row['round4_admitted']} {row['round4_words'] or ''} | wrong units {row['wrong_units_candidate']} (today {row['wrong_units_today']}) | below today: {worse or 'none'}")
(RUNS / "variants.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
