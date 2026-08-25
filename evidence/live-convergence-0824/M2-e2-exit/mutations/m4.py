import json, sys
from pathlib import Path
# Every session the pooled distribution is drawn from: p95 over 160 latencies barely moves if
# only one session's 24 are shifted, so a one-file probe would report nothing either way.
for run in ("A", "B"):
    for case in ("lex_bill_ackman", "lex_javier_milei", "lex_keyu_jin"):
        path = Path(sys.argv[1]) / f"trio-{run}/{case}/live/run-001/trace.jsonl"
        out = []
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            event = entry.get("event") or {}
            if entry.get("kind") == "service_event" and event.get("kind") == "rolling_decode_completed":
                event["payload"]["runtime_monotonic_ns"] -= 5_000_000_000
            out.append(json.dumps(entry, ensure_ascii=False))
        path.write_text("\n".join(out) + "\n")
