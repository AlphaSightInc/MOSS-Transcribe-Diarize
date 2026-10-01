"""R5-F2 spend ledger (R5-D / P69 method): known + 1.25 x planned <= cap before every paid action.

    ledger.py --total
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72/f2"
D_EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72/mic-speaker-echo"   # R5-D, read-only
LEDGER = EV / "spend.jsonl"
CAP, SAFETY = 0.25, 1.25
BATCH_PER_S = 0.0000547 + 0.002 / 60     # measured metered input (P69/P71) + Google-rate output estimate
LIVE_PER_S = (0.005 + 0.004) / 60        # instant words: list price + output estimate


def rows() -> list[dict]:
    return [json.loads(line) for line in LEDGER.read_text().splitlines()] if LEDGER.is_file() else []


def total() -> float:
    return sum(float(row["usd"]) for row in rows())


def check(planned: float, label: str) -> None:
    known = total()
    projected = known + SAFETY * planned
    print(json.dumps({"label": label, "known_usd": round(known, 4), "planned_usd": round(planned, 4),
                      "projected_usd": round(projected, 4), "cap": CAP}), flush=True)
    if projected > CAP:
        raise SystemExit(f"spend cap: {projected:.4f} > {CAP}")


def add(label: str, usd: float, **detail) -> None:
    EV.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as out:
        out.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "label": label, "usd": round(usd, 6),
                              **detail}) + "\n")


def summary() -> dict:
    data = rows()
    by_kind: dict[str, float] = {}
    for row in data:
        kind = row["label"].split(" ")[0]
        by_kind[kind] = round(by_kind.get(kind, 0) + float(row["usd"]), 4)
    out = {"cap_usd": CAP, "total_with_output_usd": round(total(), 4), "by_kind": by_kind, "rows": len(data),
           "method": "batch: measured metered input rate (P69/P71) + $0.002/min output estimate per audio second "
                     "sent; instant words: $0.005/min list + $0.004/min output estimate"}
    (EV / "spend.json").write_text(json.dumps(out, indent=1) + "\n")
    return out


if __name__ == "__main__":
    print(json.dumps(summary()))
