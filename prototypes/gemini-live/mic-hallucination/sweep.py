"""Sweep candidate rules on both fixtures; rolling (live) and terminal (saved) paths."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import chain  # noqa: E402
import rules  # noqa: E402

FIXTURES = {"fixture": ["en-hp", "en-sp", "zh-hp", "zh-sp"], "fixture2": ["A-hp", "A-sp", "B-hp", "B-sp"]}


def main():
    arms = {"baseline": None}
    for a in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0):
        for n in (1, 3, 4, 5):
            arms[f"anchor_{a}s_{n}w"] = rules.anchored(a, n)
    table = {}
    for fixture, names in FIXTURES.items():
        chain.FIX = HERE / "out" / fixture
        for name in names:
            if fixture == "fixture" and name.startswith("zh"):
                continue  # TTS local and far-end voices share one WeSpeaker voice: voice guard drops all local words
            v = chain.Variant(name)
            gate, sysw = v.gate() if not (chain.FIX / f"{name}-gated.json").exists() else (None, None)
            for arm, rule in arms.items():
                for path in ("rolling", "terminal"):
                    words = v.rolling(gate, rule) if path == "rolling" else v.terminal(gate, sysw, rule)
                    s = v.score(words)
                    table.setdefault(arm, {}).setdefault(path, []).append(
                        {"variant": f"{fixture}:{name}", "retained": s["retained"], "reference": s["reference"],
                         "bc": s["backchannel_units_kept"], "bc_total": s["backchannel_units"],
                         "stray": s["stray_words"], "stray_text": [x[0] for x in s["stray"]]})
            v.save_memo()
    (HERE / "out" / "sweep.json").write_text(json.dumps(table, ensure_ascii=False, indent=1))
    for arm, paths in table.items():
        for path, rows in paths.items():
            ret = sum(r["retained"] for r in rows) / sum(r["reference"] for r in rows)
            print(f"{arm:22} {path:8} retained {sum(r['retained'] for r in rows)}/{sum(r['reference'] for r in rows)}={ret:.3f}"
                  f" bc {sum(r['bc'] for r in rows)}/{sum(r['bc_total'] for r in rows)} stray {sum(r['stray'] for r in rows)} | "
                  + " ".join(f"{r['variant'].split(':')[1]}:{r['retained']}/{r['stray']}" for r in rows))


if __name__ == "__main__":
    main()
