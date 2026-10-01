"""G7': local speech level against the tab, today's rule and the candidate ($0; throwaway).

    PYTHON f2/sweep.py ['{"min_weight": 20}' [tag]]      # tag names a variant; default "cand" -> runs/sweep.json
The tab is at -17 dBFS. Each cell is re-levelled from 4 to 24 dB under it and replayed through the product engine
with a recorded run's provider words (same words and times; only the product's gates respond to the level), as
R5-D's gate_sweep.py did. Two word sources where recorded: the provider's answer when the speech was 10 dB under
the tab (R5-D) and when it was 20 dB under (R5-F2), because "the provider hears the same words at every level" is
false at some level. Writes runs/sweep.json.
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

LEVELS = (-21.0, -24.0, -27.0, -30.0, -33.0, -37.0, -41.0)
# (kind, echo dB, donor run, what the donor heard)
SERIES = [("short", -40.0, "rp-short-aec40", "10 dB under"), ("short", -40.0, "f2-short-e40-L37", "20 dB under"),
          ("short", -25.0, "rp-short-echo25", "10 dB under"),
          ("zhshort", -40.0, "rp-zhshort-aec40", "10 dB under"), ("zhshort", -40.0, "f2-zhshort-e40-L37", "20 dB under"),
          ("long", -40.0, "rp-long-aec40", "10 dB under"), ("long", -25.0, "rp-long-echo25", "10 dB under"),
          ("zhlong", -40.0, "rp-zhlong-aec40", "10 dB under"),
          ("dlong", -40.0, "f2-dlong-e40-L37", "20 dB under")]


def one(job):
    out, mic, donor, params = job
    cells.run(out, mic, donor=donor, candidate=params, w3="donor" if donor.startswith("rp-") else "none",
              w3_system_from=None if donor.startswith("rp-") else "rp-short-aec40")


def main():
    params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    tag = sys.argv[2] if len(sys.argv) > 2 else "cand"
    jobs, index = [], []
    for kind, echo, donor, heard in SERIES:
        for level in LEVELS:
            mic = fixtures.d_cell(kind, echo, level)
            name = f"{mic.stem[4:]}--{donor}"
            jobs += [(f"sweep/today/{name}", mic, donor, None), (f"sweep/{tag}/{name}", mic, donor, params)]
            index.append((kind, echo, donor, heard, level, name))
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(one, jobs))
    table = []
    last = None
    for kind, echo, donor, heard, level, name in index:
        today, cand = cells.score(f"sweep/today/{name}"), cells.score(f"sweep/{tag}/{name}")
        row = {"kind": kind, "echo_db": echo, "provider_words_from": donor, "provider_heard_at": heard,
               "local_dbfs": level, "below_tab_db": round(fixtures.TAB_DBFS - level),
               **{f"{who}_{key}": s[src]["recall"] for who, s in (("today", today), ("cand", cand))
                  for key, src in (("live", "live_solid"), ("at_stop", "saved_at_stop"), ("saved", "saved"))},
               "cand_phrases_saved": cand["saved"]["phrases"], "today_phrases_saved": today["saved"]["phrases"],
               "cand_wrong_units": sum(cand[k]["outside_units"] + cand[k]["echo_inside_units"]
                                       for k in ("live_solid", "saved_at_stop", "saved")),
               "today_counters": today["counters"], "cand_counters": cand["counters"]}
        table.append(row)
        if (kind, echo, donor) != last:
            last = (kind, echo, donor)
            print(f"\n{kind}, echo {echo:.0f} dB, provider words as heard {heard} ({donor})")
            print("  under tab | today live  at Stop  saved | candidate live  at Stop  saved | wrong | saved per phrase (candidate)")
        print(f"  {row['below_tab_db']:>6d} dB | {row['today_live']:>9s} {row['today_at_stop']:>8s} {row['today_saved']:>6s} |"
              f" {row['cand_live']:>13s} {row['cand_at_stop']:>8s} {row['cand_saved']:>6s} | {row['cand_wrong_units']:>5d} | {row['cand_phrases_saved']}")
    (ledger.EV / "runs" / ("sweep.json" if tag == "cand" else f"sweep-{tag}.json")).write_text(json.dumps({"params": params, "rows": table}, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
