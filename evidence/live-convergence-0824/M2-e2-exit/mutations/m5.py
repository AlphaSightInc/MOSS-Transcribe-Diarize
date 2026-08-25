import json, sys
from pathlib import Path
path = Path(sys.argv[1]) / "trio-B/lex_bill_ackman/live/run-001/trace.jsonl"
out, duplicated = [], False
for line in path.read_text().splitlines():
    if not line.strip():
        continue
    entry = json.loads(line)
    event = entry.get("event") or {}
    out.append(json.dumps(entry, ensure_ascii=False))
    if (
        not duplicated
        and entry.get("kind") == "service_event"
        and event.get("kind") == "rolling_decode_queued"
        and event["payload"].get("admitted")
    ):
        # a second admitted window in flight for the same session: depth 2
        out.append(json.dumps(entry, ensure_ascii=False))
        duplicated = True
path.write_text("\n".join(out) + "\n")
