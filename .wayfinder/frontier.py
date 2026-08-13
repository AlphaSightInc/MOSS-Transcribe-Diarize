#!/usr/bin/env python3
"""Frontier query for the local-markdown wayfinder tracker.

Frontier = open, unblocked, unclaimed tickets — the edge of the known.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TICKETS = Path(__file__).resolve().parent / "tickets"


def parse(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise SystemExit(f"{path.name}: missing frontmatter")
    _, front, _ = text.split("---", 2)
    meta: dict[str, object] = {"path": path}
    for line in front.strip().splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key == "blocked_by":
            meta[key] = re.findall(r"T-\d+", value)
        else:
            meta[key] = value
    meta.setdefault("blocked_by", [])
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="list every ticket with state")
    args = ap.parse_args()

    if not TICKETS.is_dir():
        raise SystemExit(f"no tickets directory at {TICKETS}")

    tickets = sorted((parse(p) for p in TICKETS.glob("*.md")), key=lambda m: str(m["id"]))
    closed = {str(t["id"]) for t in tickets if t.get("status") == "closed"}

    for t in tickets:
        blockers = [b for b in t["blocked_by"] if b not in closed]
        claimed = bool(str(t.get("assignee", "")).strip())
        is_open = t.get("status") == "open"
        on_frontier = is_open and not blockers and not claimed

        if not args.all and not on_frontier:
            continue

        if on_frontier:
            state = "FRONTIER"
        elif not is_open:
            state = "closed  "
        elif claimed:
            state = "claimed "
        else:
            state = f"blocked({','.join(blockers)})"

        print(f"{state:<22} {t['id']:<5} [{t.get('type','?'):<9}] {t.get('title','')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
