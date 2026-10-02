"""R5-D spend ledger (P69 method): known + 1.25 x planned <= cap before every paid action.

    ledger.py --check <planned_usd> <label>     exit 1 if it would pass the cap
    ledger.py --total
Rows are appended by the probe scripts (with-output estimate: metered - metered_output + output estimate)
and by e2e_ledger() from each browser run's engine diagnostics.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72/mic-speaker-echo"
LEDGER = EV / "spend.jsonl"
CAP, SAFETY = 1.00, 1.25
BATCH_PER_S = 0.0000547 + 0.002 / 60     # measured metered input (P69/P71) + Google-rate output estimate
LIVE_PER_S = (0.005 + 0.004) / 60        # W3 list price + output estimate


def rows() -> list[dict]:
    return [json.loads(line) for line in LEDGER.read_text().splitlines()] if LEDGER.is_file() else []


def total() -> float:
    return sum(float(row["usd"]) for row in rows())


def check(planned: float, label: str) -> None:
    known = total()
    projected = known + SAFETY * planned
    print(json.dumps({"label": label, "known_usd": round(known, 4), "planned_usd": round(planned, 4),
                      "projected_usd": round(projected, 4), "cap": CAP}))
    if projected > CAP:
        raise SystemExit(f"spend cap: {projected:.4f} > {CAP}")


def add(label: str, usd: float, **detail) -> None:
    EV.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as out:
        out.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "label": label, "usd": round(usd, 6),
                              **detail}) + "\n")


if __name__ == "__main__":
    if sys.argv[1] == "--check":
        check(float(sys.argv[2]), sys.argv[3])
    else:
        print(json.dumps({"total_usd": round(total(), 4), "cap": CAP, "rows": len(rows())}))
