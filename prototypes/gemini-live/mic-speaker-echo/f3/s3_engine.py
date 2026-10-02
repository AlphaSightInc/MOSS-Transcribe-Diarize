"""Rule H inside the whole production engine: today vs rule on recorded meetings ($0, throwaway).

    PY f3/s3_engine.py [--rerun]

Cells:
 - R5-D's nine recorded meetings (both lanes, their own clean-up answer);
 - five live samples of the Chinese+names recording x the clean-up draws at the same leading silence (production
   request and the three accepted request variants) + the draw that lost 7 of 10 names, time-shifted.
For each cell the engine runs twice (as shipped / with rule H) and the saved transcripts are compared:
 kept words identical (text, time, speaker), rows sorted with one owner per interval, names, punctuation,
 repeated units, restored runs.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import f3lib  # noqa: E402
from f3lib import EV, RAW, RD_FIX, RD_RAW, S  # noqa: E402
from s2_witness import NAMES, ZH_END, fold  # noqa: E402

M = "0.15"
SYSTEM = RD_FIX / "sys-zhlatin-en.wav"
RERUN = "--rerun" in sys.argv
RERUN_RULE = "--rerun-rule" in sys.argv
MICS = ["short-aec40", "listen-aec40", "listen-echo25", "long-aec40", "long-echo25", "short-echo25", "short-noecho",
        "zhlong-aec40", "zhshort-aec40"]


def engine(run: str, *args: str) -> Path:
    out = EV / "runs" / run
    ruled = run.endswith("-rule") or run.startswith("rule-")
    if RERUN or (RERUN_RULE and ruled) or not (out / "terminal.json").is_file():
        subprocess.run([sys.executable, str(HERE / "engine.py"), run, str(SYSTEM), *args, "--quiet"], check=True,
                       stderr=subprocess.DEVNULL)
    return out


def answer(draw: str) -> Path:
    variant, prefix = draw.rsplit("-p", 1)
    rows = json.loads((EV / "runs" / f"request-sys-zhlatin-en-{variant}.json").read_text())
    name = next(r["answer"] for r in rows if r["draw"] == f"sys-zhlatin-en-{draw}")
    return next(f / name for f in (RAW, RD_RAW) if (f / name).is_file())


def rows_of(folder: Path, name="saved-meeting.json"):
    return json.loads((folder / name).read_text())["transcript"]["segments"]


def lane_stats(rows, lane: str, prefix: float) -> dict:
    mine = [r for r in rows if r["source_lane"] == lane]
    text = " ".join(r["text"] for r in mine)
    zh = " ".join(r["text"] for r in mine if r["start"] < prefix + ZH_END)
    units = f3lib.units(fold(zh))
    merged = []
    for u in units:
        if merged and merged[-1] == "computer" and u in ("file", "phile"):
            merged[-1] = "computerphile"
        else:
            merged.append(u)
    return {"rows": len(mine), "units": len(f3lib.units(text)), "names": f3lib.kept_of(NAMES, merged)[0],
            "punctuation": f3lib.punctuation(text), "repeated_units": f3lib.repeated_units(text),
            "stutters": sum(a == b and a != "i" for a, b in zip(f3lib.units(fold(text)), f3lib.units(fold(text))[1:])),
            "sorted": all(a["start"] <= b["start"] for a, b in zip(mine, mine[1:])),
            "one_owner": all(a["end"] <= b["start"] + 1e-9 for a, b in zip(mine, mine[1:])),
            "script": f3lib.script_of(text)}


def compare(cell: str, today: Path, ruled: Path, prefix: float) -> list[dict]:
    out = []
    t_log, r_log = json.loads((today / "terminal.json").read_text()), json.loads((ruled / "terminal.json").read_text())
    live = rows_of(today, "saved-meeting-live.json")
    for lane in ("system", "microphone"):
        if lane not in r_log:
            continue
        kept_today = [tuple(w) for w in t_log[lane].get("final_words", [])]
        final_rule = [tuple(w) for w in r_log[lane].get("final_words", [])]
        restored = r_log[lane].get("restored", [])
        inserted = {(t, int(round(r["start_s"] * S))) for r in restored for t in r["text"]}
        it = iter(final_rule)
        same = all(any(w == f for f in it) for w in kept_today)          # every kept word, same order, same label
        extra = len(final_rule) - len(kept_today)
        before, after = lane_stats(rows_of(today), lane, prefix), lane_stats(rows_of(ruled), lane, prefix)
        speakers_today = [(r["start"], r["speaker"]) for r in rows_of(today) if r["source_lane"] == lane]
        speakers_rule = {r["start"]: r["speaker"] for r in rows_of(ruled) if r["source_lane"] == lane}
        out.append({"cell": cell, "lane": lane, "live": lane_stats(live, lane, prefix), "today": before, "rule": after,
                    "kept_words_identical": same, "words_added": extra,
                    "restored_words": sum(len(r["text"]) for r in restored),
                    "restored": [(" ".join(r["text"]), r["uncovered_s"], r["speaker"]) for r in restored],
                    "row_speakers_unchanged": all(speakers_rule.get(start, who) == who for start, who in speakers_today),
                    "cleanup_wall_s": [json.loads((today / "receipt.json").read_text())["cleanup_wall_s"],
                                       json.loads((ruled / "receipt.json").read_text())["cleanup_wall_s"]]})
        del inserted
    return out


def main():
    table: list[dict] = []
    for mic in MICS:
        args = [str(RD_FIX / f"mic-{mic}.wav"), "--donor", f"rp-{mic}"]
        table += compare(f"recorded {mic}", engine(f"base-{mic}", *args), engine(f"rule-{mic}", *args, "--rule", M), 3.0)
    for prefix in (0.0, 1.5, 3.0, 5.0, 8.0):
        draws = [f"{v}-p{prefix:g}" for v in ("base", "lang", "lang2", "text")]
        if prefix != 3.0:
            draws.append("lang2-p3")
        for draw in draws:
            shift = prefix - float(draw.rsplit("-p", 1)[1])
            args = ["--silent-mic", "--prefix", str(prefix), "--terminal-from", str(answer(draw)), "--shift", str(shift)]
            if prefix == 3.0:
                args += ["--donor", "rp-short-aec40"]
            table += compare(f"live p{prefix:g} x {draw}", engine(f"pair-p{prefix:g}-{draw}-today", *args),
                             engine(f"pair-p{prefix:g}-{draw}-rule", *args, "--rule", M), prefix)
    (EV / "runs" / "engine-pairs.json").write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n")
    for row in table:
        print(f"{row['cell']:28s} {row['lane']:10s} names live/today/rule {row['live']['names']:2d}/{row['today']['names']:2d}/"
              f"{row['rule']['names']:2d}  punct {row['live']['punctuation']:2d}/{row['today']['punctuation']:2d}/"
              f"{row['rule']['punctuation']:2d}  repeated {row['today']['repeated_units']}/{row['rule']['repeated_units']}"
              f"  stutter {row['live']['stutters']}/{row['today']['stutters']}/{row['rule']['stutters']}"
              f"  kept-identical {row['kept_words_identical']}  speakers-same {row['row_speakers_unchanged']}"
              f"  sorted/one-owner {row['rule']['sorted']}/{row['rule']['one_owner']}  restored {row['restored']}")
    sys_rows = [r for r in table if r["lane"] == "system"]
    print(json.dumps({
        "cells": len(table), "system_cells": len(sys_rows),
        "kept_words_identical": sum(r["kept_words_identical"] for r in table),
        "row_speakers_unchanged": sum(r["row_speakers_unchanged"] for r in table),
        "rows_sorted_one_owner": sum(r["rule"]["sorted"] and r["rule"]["one_owner"] for r in table),
        "names_mean_live_today_rule": [round(sum(r[k]["names"] for r in sys_rows) / len(sys_rows), 2)
                                       for k in ("live", "today", "rule")],
        "cells_where_rule_has_fewer_names_than_live_or_today": sum(
            r["rule"]["names"] < r["today"]["names"] for r in sys_rows),
        "repeated_units_today_rule": [sum(r["today"]["repeated_units"] for r in table),
                                      sum(r["rule"]["repeated_units"] for r in table)],
        "stutters_live_today_rule": [sum(r[k]["stutters"] for r in table) for k in ("live", "today", "rule")],
        "restored_words": sum(r["restored_words"] for r in table),
        "cleanup_wall_s_mean_today_rule": [round(sum(r["cleanup_wall_s"][i] for r in table) / len(table), 2) for i in (0, 1)],
    }))


if __name__ == "__main__":
    main()
