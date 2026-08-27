#!/usr/bin/env python3
"""Capture every valid persisted ProjectClerk session revision after a marker."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--marker-ns", required=True, type=int)
    parser.add_argument("--stop-file", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    index = 0
    events = args.output / "events.jsonl"
    while not args.stop_file.exists():
        for path in sorted(args.sessions.glob("*.json"), key=lambda item: item.stat().st_mtime_ns):
            try:
                if path.stat().st_mtime_ns < args.marker_ns:
                    continue
                data = path.read_bytes()
                payload = json.loads(data)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload.get("conversation"), list) or not payload["conversation"]:
                continue
            digest = hashlib.sha256(data).hexdigest()
            key = f"{path}:{digest}"
            if key in seen:
                continue
            seen.add(key)
            index += 1
            observed_ns = time.time_ns()
            target = args.output / f"{index:04d}-{observed_ns}-{digest}.json"
            shutil.copyfile(path, target)
            event = {
                "index": index,
                "observed_epoch_ns": observed_ns,
                "source": str(path),
                "sha256": digest,
                "bytes": len(data),
                "conversation_rows": len(payload["conversation"]),
                "speaker_count": payload.get("speakerCount"),
                "target": target.name,
            }
            with events.open("a", encoding="utf-8") as sink:
                sink.write(json.dumps(event, sort_keys=True) + "\n")
        time.sleep(0.05)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
