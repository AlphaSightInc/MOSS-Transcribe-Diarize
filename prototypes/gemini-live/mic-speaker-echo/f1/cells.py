"""R5-F1 T2 ($0): every recorded cell through the production engine, base vs arms (throwaway).

    PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python \
        prototypes/gemini-live/mic-speaker-echo/f1/cells.py [--force]

Runs capture.py for the 9 recorded cells + the silent-microphone case (base and arm A, answer lag 0 s
and 3.5 s), asserts the unpatched lag-0 replay reproduces R5-D's snapshots, then prints G1/G2/G3 per
cell, the offline score of every arm on the captured inputs, and the real-Chrome run re-trimmed offline.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import score  # noqa: E402
import trim as arms  # noqa: E402

D = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72/mic-speaker-echo"
EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72/f1"
CELLS = ["rp-listen-aec40", "rp-listen-echo25", "rp-long-aec40", "rp-long-echo25", "rp-short-aec40",
         "rp-short-echo25", "rp-short-noecho", "rp-zhlong-aec40", "rp-zhshort-aec40"]
SILENT = ("rp-short-aec40", ["--silent-mic", "--mic", "mic-listen-aec40.wav", "--tag", "+silentmic"])  # R5-D rp-silent-mic
CANDIDATES = ["A", "C"]
OFFLINE = ["base", "A", "B", "C", "D-min3", "D-min4", "D-min6", "D-min7", "D-min8", "D-min9", "D-min10",
           "D-scaled", "D-tight", "D-share50", "D-share70", "D-share80", "A+fold"]


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def capture(cell: str, arm: str, lag: float, extra=()) -> Path:
    tag = extra[extra.index("--tag") + 1] if "--tag" in extra else ""
    out = EV / "runs" / (f"{cell}{tag}-{arm}" + (f"-lag{lag:g}" if lag else ""))
    if "--force" in sys.argv or not (out / "receipt.json").is_file():
        subprocess.run([sys.executable, str(HERE / "capture.py"), cell, arm, "--lag", str(lag), *extra],
                       check=True, capture_output=True, text=True)
    receipt = json.loads((out / "receipt.json").read_text())
    assert receipt["paid_seconds"] == 0 and receipt["replayed_calls"] == receipt["batch_calls"]
    return out


def final_rows(snaps: list[dict]) -> list[list]:
    live = next(s for s in snaps if s["note"] and s["note"].startswith("completed"))
    return [[r["start_sample"], r["end_sample"], r["text"], r.get("source_lane")] for r in live["effective"]]


def main():
    report: dict = {"cells": {}, "offline": {}, "reproduction": {}}
    runs = [(cell, ()) for cell in CELLS] + [(SILENT[0], tuple(SILENT[1]))]
    pooled = {name: {} for name in OFFLINE}
    selfcheck_pairs = 0
    for cell, extra in runs:
        label = cell + ("+silentmic" if extra else "")
        row = report["cells"][label] = {}
        for lag in (0.0, 3.5):
            base = capture(cell, "base", lag, extra)
            b_snaps = jsonl(base / "snapshots.jsonl")
            b_calls = jsonl(base / "trim.jsonl")
            row[f"lag{lag:g}"] = {"base": score.snapshot_score(b_snaps)}
            for name in CANDIDATES:
                cand = capture(cell, name, lag, extra)
                row[f"lag{lag:g}"][name] = score.snapshot_score(jsonl(cand / "snapshots.jsonl"))
                a_calls = jsonl(cand / "trim.jsonl")
                # the trim does not feed back into the engine: every run saw identical inputs
                assert [(c["segments"], c["committed"]) for c in b_calls] == [(c["segments"], c["committed"]) for c in a_calls]
                # the end-to-end run kept exactly what the offline arm keeps on the same inputs
                kept = [[r.text for r in arms.ARMS[name](tuple(score.seg(x) for x in c["segments"]),
                                                        tuple(score.eff(x) for x in c["committed"]))] for c in b_calls]
                assert kept == [[r[2] for r in c["kept"]] for c in a_calls]
            if lag:
                off = score.offline(b_calls, OFFLINE, final_rows(b_snaps))
                report["offline"][label] = off
                for name, stat in off.items():
                    for key, value in stat.items():
                        if isinstance(value, (int, float)) and not key.startswith("us_"):
                            pooled[name][key] = pooled[name].get(key, 0) + value
                        elif isinstance(value, list):
                            pooled[name].setdefault(key, []).extend(dict(item, cell=label) for item in value)
                # parametrized head rule == production at default parameters, on every real (tail, head) pair
                pairs = []
                orig = arms.PROD_HEAD
                arms.runtime._repeated_head = lambda t, w: (pairs.append((list(t), list(w))), orig(t, w))[1]
                for c in b_calls:
                    arms.BASE(tuple(score.seg(s) for s in c["segments"]), tuple(score.eff(s) for s in c["committed"]))
                arms.runtime._repeated_head = orig
                unit_pairs = []
                probe = arms.make_trim(head=lambda t, w: (unit_pairs.append((list(t), list(w))), orig(t, w))[1])
                for c in b_calls:
                    probe(tuple(score.seg(s) for s in c["segments"]), tuple(score.eff(s) for s in c["committed"]))
                selfcheck_pairs += arms.selfcheck(pairs + unit_pairs)
        # reproduction: the unpatched lag-0 replay against R5-D's own snapshots of the same cell
        theirs = D / "runs" / ("rp-silent-mic" if extra else cell) / "snapshots.jsonl"
        receipt = json.loads((theirs.parent / "receipt.json").read_text())
        mine = row["lag0"]["base"]
        ref = score.snapshot_score(jsonl(theirs))
        same = all(mine[lane] == ref[lane] for lane in ("system", "microphone"))
        report["reproduction"][label] = {"r5d_run_mode": receipt["mode"], "identical_to_r5d": same,
                                         "mine_system": mine["system"], "r5d_system": ref["system"]}

    print("== reproduction of R5-D (unpatched, lag 0): my replay vs R5-D's saved snapshots of the same cell")
    for label, r in report["reproduction"].items():
        print(f"{label:28} r5d mode {r['r5d_run_mode']:7} identical {str(r['identical_to_r5d']):5} "
              f"repeated unit-polls mine {r['mine_system']['repeated_unit_polls']} r5d {r['r5d_system']['repeated_unit_polls']}"
              f" | fresh mine {r['mine_system']['fresh_unit_polls']} r5d {r['r5d_system']['fresh_unit_polls']}"
              f" | s>=10 mine {r['mine_system']['seconds_ge10_repeated']} r5d {r['r5d_system']['seconds_ge10_repeated']}")
    replays = [r for r in report["reproduction"].values() if r["r5d_run_mode"] == "replay"]
    assert replays and all(r["identical_to_r5d"] for r in replays), "unpatched harness does not reproduce R5-D"
    print(f"parametrized head rule == production _repeated_head on {selfcheck_pairs} real (tail, head) pairs")

    for lag in ("lag0", "lag3.5"):
        for name in CANDIDATES:
            print(f"\n== G1/G3 per cell, production engine end to end, answer {lag}, base -> {name}")
            print("cell | sys repeated unit-polls | sys seconds >=10 repeated | sys worst | sys fresh unit-polls (block metric) | "
                  "mic repeated | mic fresh | frontier published at e (base)")
            for label, row in report["cells"].items():
                b, a = row[lag]["base"], row[lag][name]
                print(f"{label:28} | {b['system']['repeated_unit_polls']:5} -> {a['system']['repeated_unit_polls']:3} | "
                      f"{b['system']['seconds_ge10_repeated']:5} -> {a['system']['seconds_ge10_repeated']:3} | "
                      f"{b['system']['worst_repeated']:3} -> {a['system']['worst_repeated']:2} | "
                      f"{b['system']['fresh_unit_polls']:5} -> {a['system']['fresh_unit_polls']:5} | "
                      f"{b['microphone']['repeated_unit_polls']:4} -> {a['microphone']['repeated_unit_polls']:3} | "
                      f"{b['microphone']['fresh_unit_polls']:4} -> {a['microphone']['fresh_unit_polls']:4} | "
                      f"{[(e, f) for e, f in b['frontier_published_at_e']][1:3]}")

    keys = ["rows", "removed_unit_polls", "repeated_unit_polls", "truth_rows", "fresh_shown_units", "over_trim_units",
            "over_trim_rows", "under_trim_units", "under_trim_rows_ge5", "reshown_units", "reshow_events",
            "later_rows", "later_removed_restating_kept_rows", "later_removed_other", "later_shown_restating_kept_rows",
            "noncjk_rows", "noncjk_rows_differ_from_base", "noncjk_calls", "noncjk_calls_differ_from_base", "calls_differ_from_base"]
    print("\n== offline, all arms on the captured inputs of the 10 lag-3.5 runs (pooled)")
    print("arm | " + " | ".join(keys))
    for name in OFFLINE:
        print(f"{name:10} | " + " | ".join(str(pooled[name].get(k, 0)) for k in keys))
    for name in ("base", "A", "C"):
        print(f"\n-- {name}: over-trims (fresh removed, by the later-committed text)")
        for item in pooled[name].get("over_trims", [])[:12]:
            print("  ", json.dumps(item, ensure_ascii=False))
        print(f"-- {name}: under-trims >= 5 units (repeat left on screen)")
        seen = set()
        for item in pooled[name].get("under_trims", []):
            key = (item["cell"], item["lane"], item["repeat_left"])
            if key not in seen and len(seen) < 12:
                seen.add(key)
                print("  ", json.dumps(item, ensure_ascii=False))
        print(f"-- {name}: re-shown")
        for item in pooled[name].get("reshows", [])[:12]:
            print("  ", json.dumps(item, ensure_ascii=False))
        print(f"-- {name}: rows without CJK that differ from base: {len(pooled[name].get('differences', []))}")
        for item in pooled[name].get("differences", [])[:6]:
            print("  ", json.dumps(item, ensure_ascii=False))
    report["offline_pooled"] = pooled
    all_calls = [c for cell, extra in runs for c in jsonl(capture(cell, "base", 3.5, extra) / "trim.jsonl")]
    report["margins_A"] = score.margins(all_calls)
    print("\nmargins of arm A's accepted cuts (10 lag-3.5 runs):", json.dumps(report["margins_A"]))

    # the real-Chrome run: R5-D saved only snapshots (rows already passed through today's rule); every arm
    # is applied on top of them. For Chinese rows today's rule removed nothing, so the rows are the raw input.
    snaps = jsonl(D / "runs/short-aec40/snapshots.jsonl")
    chrome = {"base": score.snapshot_score(snaps, prefix=0)}
    for name in ("A", "B", "C"):
        again = copy.deepcopy(snaps)
        for snap in again:
            if snap["status"] != "active" or not snap["provisional"]:
                continue
            rows = snap["provisional"]["segments"]
            kept = arms.ARMS[name](
                tuple(arms.runtime.GeminiSegment(r["start_sample"], r["end_sample"], r["text"], None, r["source_lane"]) for r in rows),
                tuple(score.eff([r["start_sample"], r["end_sample"], r["text"], r.get("source_lane")]) for r in snap["effective"]))
            snap["provisional"]["segments"] = [{"start_sample": r.start_sample, "end_sample": r.end_sample, "text": r.text,
                                                "source_lane": r.source_lane} for r in kept]
        chrome[name] = score.snapshot_score(again, prefix=0)
    report["chrome_short_aec40"] = chrome
    print("\n== real-Chrome run short-aec40 (R5-D's saved page-poll snapshots; arms applied on top of today's output)")
    for name, s in chrome.items():
        print(f"{name:5} system: repeated unit-polls {s['system']['repeated_unit_polls']:5} seconds>=10 {s['system']['seconds_ge10_repeated']:5} "
              f"worst {s['system']['worst_repeated']:3} fresh {s['system']['fresh_unit_polls']:5} | microphone: repeated "
              f"{s['microphone']['repeated_unit_polls']} fresh {s['microphone']['fresh_unit_polls']}")
    live = json.loads((D / "runs/short-aec40/saved-meeting-live.json").read_text())["transcript"]["segments"]
    live_rows = [[round(r["start"] * score.S), round(r["end"] * score.S), r["text"], r.get("source_lane")] for r in live]
    pseudo = [{"at": s["accepted"], "segments": [[r["start_sample"], r["end_sample"], r["text"], r["source_lane"]]
                                                   for r in s["provisional"]["segments"]],
               "committed": [[r["start_sample"], r["end_sample"], r["text"], r.get("source_lane")] for r in s["effective"]]}
              for s in snaps if s["status"] == "active" and s["provisional"]]
    truth = score.offline(pseudo, ["base", "A", "C"], live_rows)
    report["chrome_short_aec40_truth"] = truth
    for name, t in truth.items():
        print(f"{name:5} by the later-committed text: fresh units shown {t['fresh_shown_units']}, fresh removed {t['over_trim_units']} "
              f"in {t['over_trim_rows']} rows, repeat left {t['under_trim_units']} units, rows with >= 5 repeated units left "
              f"{t['under_trim_rows_ge5']} of {t['truth_rows']}")
    (EV / "cells.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")


main()
